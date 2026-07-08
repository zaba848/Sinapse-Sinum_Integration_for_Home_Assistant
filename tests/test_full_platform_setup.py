"""Full-stack platform setup harness: real hass boot -> entity_registry.

Unlike test_init_setup.py (which patches async_forward_entry_setups away),
this harness runs the real config-entry pipeline so every platform's
async_setup_entry actually executes and registers entities in HA's real
entity_registry/device_registry. It exists to catch integration-level bugs
(duplicate unique_id, missing device_info, cross-platform entity_id
collisions, broken unload/reload) that per-platform unit tests can't see
because they never wire the platforms together through HA itself.

Note: entities with should_poll=True (most sensors here) trigger a real
async_update() during setup, which awaits the autospec'd mock_client. Under
this environment's asyncio eager-task scheduling that produces a harmless
"coroutine was never awaited" RuntimeWarning from AsyncMock's internal
call-signature validation (reproducible without any Sinum code involved);
it is suppressed below rather than chased as a product bug.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sinum.const import (
    AUTH_MODE_TOKEN,
    CONF_API_TOKEN,
    CONF_AUTH_MODE,
    CONF_MQTT_ENABLED,
    CONF_WS_ENABLED,
    DOMAIN,
)

pytestmark = [
    pytest.mark.slow,
    pytest.mark.filterwarnings(
        "ignore:coroutine 'AsyncMockMixin._execute_mock_call' was never awaited:RuntimeWarning"
    ),
]


def _build_entry(entry_id: str = "full_setup_entry", host: str = "10.0.0.1") -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        entry_id=entry_id,
        title="Sinum",
        data={
            "host": host,
            CONF_AUTH_MODE: AUTH_MODE_TOKEN,
            CONF_API_TOKEN: "test-token",
            # Disabled so the real-time bridge does not attempt a live
            # websocket/MQTT connection during the test.
            CONF_WS_ENABLED: False,
            CONF_MQTT_ENABLED: False,
        },
    )


async def _setup(hass, entry, client) -> None:
    entry.add_to_hass(hass)
    with patch("custom_components.sinum.SinumClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


class TestFullPlatformSetup:
    """Boot the integration for real and inspect the resulting entity_registry."""

    async def test_setup_registers_entities_via_real_platforms(
        self, hass, enable_custom_integrations, mock_client
    ):
        entry = _build_entry()
        await _setup(hass, entry, mock_client)

        assert entry.state is ConfigEntryState.LOADED

        registry = er.async_get(hass)
        entities = er.async_entries_for_config_entry(registry, entry.entry_id)
        assert len(entities) > 0

        unique_ids = [e.unique_id for e in entities]
        assert len(unique_ids) == len(set(unique_ids)), "duplicate unique_id across platforms"

        for entity in entities:
            assert entity.platform == DOMAIN
            assert entity.config_entry_id == entry.entry_id

    async def test_devices_registered_with_domain_identifiers(
        self, hass, enable_custom_integrations, mock_client
    ):
        entry = _build_entry()
        await _setup(hass, entry, mock_client)

        registry = dr.async_get(hass)
        devices = dr.async_entries_for_config_entry(registry, entry.entry_id)
        assert len(devices) > 0

        for device in devices:
            assert device.identifiers, f"device {device.id} has no identifiers"
            for domain, identifier in device.identifiers:
                assert domain == DOMAIN
                assert identifier.startswith(entry.entry_id)

    async def test_enabled_entities_have_a_state(self, hass, enable_custom_integrations, mock_client):
        entry = _build_entry()
        await _setup(hass, entry, mock_client)

        registry = er.async_get(hass)
        entities = er.async_entries_for_config_entry(registry, entry.entry_id)
        enabled = [e for e in entities if not e.disabled]
        assert enabled, "expected at least one enabled entity"

        missing_state = [e.entity_id for e in enabled if hass.states.get(e.entity_id) is None]
        assert not missing_state, f"enabled entities missing a state: {missing_state}"


class TestPlatformSetupLifecycle:
    """Setup is only half the contract: reload/unload/remove must stay consistent."""

    async def test_reload_does_not_duplicate_or_change_unique_ids(
        self, hass, enable_custom_integrations, mock_client
    ):
        entry = _build_entry()
        await _setup(hass, entry, mock_client)

        registry = er.async_get(hass)
        before = {e.unique_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)}

        with patch("custom_components.sinum.SinumClient", return_value=mock_client):
            assert await hass.config_entries.async_reload(entry.entry_id)
            await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        after = {e.unique_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)}
        assert before == after

    async def test_unload_removes_states_but_keeps_registry_entries(
        self, hass, enable_custom_integrations, mock_client
    ):
        entry = _build_entry()
        await _setup(hass, entry, mock_client)

        registry = er.async_get(hass)
        entities_before = er.async_entries_for_config_entry(registry, entry.entry_id)
        entity_ids = [e.entity_id for e in entities_before]
        # Disabled-by-default entities never get a live state at all, so the
        # "unavailable after unload" contract only applies to enabled ones.
        enabled_entity_ids = [e.entity_id for e in entities_before if not e.disabled]
        assert entity_ids and enabled_entity_ids

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.NOT_LOADED
        # HA does not remove states for registered entities on unload — it
        # marks them "unavailable" (full removal only happens on
        # async_remove) so history/automations referencing them survive a
        # hub reboot or a config-entry reload.
        states = [hass.states.get(eid) for eid in enabled_entity_ids]
        assert all(s is not None and s.state == "unavailable" for s in states)
        entities_after = er.async_entries_for_config_entry(registry, entry.entry_id)
        assert {e.entity_id for e in entities_after} == set(entity_ids)

    async def test_remove_entry_clears_registry(self, hass, enable_custom_integrations, mock_client):
        entry = _build_entry()
        await _setup(hass, entry, mock_client)

        registry = er.async_get(hass)
        assert er.async_entries_for_config_entry(registry, entry.entry_id)

        await hass.config_entries.async_remove(entry.entry_id)
        await hass.async_block_till_done()

        assert er.async_entries_for_config_entry(registry, entry.entry_id) == []


class TestMultiHubPlatformSetup:
    """Two config entries loaded together must not collide on entity_id."""

    async def test_two_hubs_do_not_collide_on_entity_id(
        self, hass, enable_custom_integrations, mock_client
    ):
        entry_a = _build_entry(entry_id="hub_a_entry", host="10.0.0.1")
        entry_b = _build_entry(entry_id="hub_b_entry", host="10.0.0.2")

        await _setup(hass, entry_a, mock_client)
        await _setup(hass, entry_b, mock_client)

        assert entry_a.state is ConfigEntryState.LOADED
        assert entry_b.state is ConfigEntryState.LOADED

        registry = er.async_get(hass)
        entities_a = er.async_entries_for_config_entry(registry, entry_a.entry_id)
        entities_b = er.async_entries_for_config_entry(registry, entry_b.entry_id)

        ids_a = {e.entity_id for e in entities_a}
        ids_b = {e.entity_id for e in entities_b}
        assert not (ids_a & ids_b), f"entity_id collision across hubs: {ids_a & ids_b}"

        uids_a = {e.unique_id for e in entities_a}
        uids_b = {e.unique_id for e in entities_b}
        assert not (uids_a & uids_b), f"unique_id collision across hubs: {uids_a & uids_b}"


class TestUnloadReloadLifecycle:
    """Unload then reload must restore entity states to available."""

    async def test_unload_then_reload_restores_available_states(
        self, hass, enable_custom_integrations, mock_client
    ):
        entry = _build_entry()
        await _setup(hass, entry, mock_client)

        registry = er.async_get(hass)
        entities_before = [
            e for e in er.async_entries_for_config_entry(registry, entry.entry_id) if not e.disabled
        ]
        assert entities_before

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.NOT_LOADED

        with patch("custom_components.sinum.SinumClient", return_value=mock_client):
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        for entity in entities_before:
            state = hass.states.get(entity.entity_id)
            assert state is not None
            assert state.state != "unavailable"


class TestMultiHubLifecycle:
    """Multi-hub unload/reload/remove must keep sibling hubs intact."""

    async def test_multi_hub_unload_one_hub_leaves_other_loaded(
        self, hass, enable_custom_integrations, mock_client
    ):
        entry_a = _build_entry(entry_id="hub_a_lifecycle", host="10.0.0.1")
        entry_b = _build_entry(entry_id="hub_b_lifecycle", host="10.0.0.2")
        await _setup(hass, entry_a, mock_client)
        await _setup(hass, entry_b, mock_client)

        assert await hass.config_entries.async_unload(entry_a.entry_id)
        await hass.async_block_till_done()

        assert entry_a.state is ConfigEntryState.NOT_LOADED
        assert entry_b.state is ConfigEntryState.LOADED

    async def test_multi_hub_reload_one_while_other_loaded(
        self, hass, enable_custom_integrations, mock_client
    ):
        entry_a = _build_entry(entry_id="hub_a_reload", host="10.0.0.1")
        entry_b = _build_entry(entry_id="hub_b_reload", host="10.0.0.2")
        await _setup(hass, entry_a, mock_client)
        await _setup(hass, entry_b, mock_client)

        with patch("custom_components.sinum.SinumClient", return_value=mock_client):
            assert await hass.config_entries.async_reload(entry_a.entry_id)
            await hass.async_block_till_done()

        assert entry_a.state is ConfigEntryState.LOADED
        assert entry_b.state is ConfigEntryState.LOADED

    async def test_remove_one_hub_in_multi_hub_setup(
        self, hass, enable_custom_integrations, mock_client
    ):
        entry_a = _build_entry(entry_id="hub_a_remove", host="10.0.0.1")
        entry_b = _build_entry(entry_id="hub_b_remove", host="10.0.0.2")
        await _setup(hass, entry_a, mock_client)
        await _setup(hass, entry_b, mock_client)

        registry = er.async_get(hass)
        ids_b_before = {
            e.entity_id for e in er.async_entries_for_config_entry(registry, entry_b.entry_id)
        }
        assert ids_b_before

        await hass.config_entries.async_remove(entry_a.entry_id)
        await hass.async_block_till_done()

        assert entry_b.state is ConfigEntryState.LOADED
        ids_b_after = {
            e.entity_id for e in er.async_entries_for_config_entry(registry, entry_b.entry_id)
        }
        assert ids_b_before == ids_b_after
        assert er.async_entries_for_config_entry(registry, entry_a.entry_id) == []


class TestDegradedDataPlatformSetup:
    """An empty/degraded hub must still load cleanly with zero entities."""

    async def test_setup_succeeds_with_no_devices(self, hass, enable_custom_integrations, mock_client):
        mock_client.get_rooms.return_value = []
        mock_client.get_virtual_devices.return_value = []
        mock_client.get_wtp_devices.return_value = []
        mock_client.get_scenes.return_value = []
        mock_client.get_variables.return_value = []
        mock_client.get_alarm_devices.return_value = []

        entry = _build_entry()
        await _setup(hass, entry, mock_client)

        assert entry.state is ConfigEntryState.LOADED
