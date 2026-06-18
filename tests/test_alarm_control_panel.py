"""Tests for Sinum alarm control panel."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.alarm_control_panel import AlarmControlPanelState

from custom_components.sinum.alarm_control_panel import SinumAlarmZone, async_setup_entry
from custom_components.sinum.api import SinumConnectionError


def _make_zone(zone_id=1, zone_status="disarmed", violated=False, armed=False, **kwargs):
    return {
        "id": zone_id,
        "name": f"Zone {zone_id}",
        "type": "alarm_zone",
        "zone_status": zone_status,
        "armed": armed,
        "violated": violated,
        "enter_time_delay": 15,
        "exit_time_delay": 15,
        "associations": {"inputs": [{"class": "sbus", "id": 10}]},
        **kwargs,
    }


def _make_entity(zone_data, alarm_zones=None):
    coordinator = MagicMock()
    zones = alarm_zones if alarm_zones is not None else {zone_data["id"]: zone_data}
    coordinator.alarm_zones = zones
    entity = SinumAlarmZone(coordinator, zone_data, "test_entry")
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    return entity


class TestAlarmSetup:
    @pytest.mark.asyncio
    async def test_empty_endpoint_adds_no_entities(self):
        coordinator = MagicMock()
        coordinator.client.get_alarm_devices = AsyncMock(return_value=[])
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "test_entry"
        async_add_entities = MagicMock()

        await async_setup_entry(MagicMock(), entry, async_add_entities)

        async_add_entities.assert_called_once_with([])

    @pytest.mark.asyncio
    async def test_connection_error_adds_no_entities(self):
        coordinator = MagicMock()
        coordinator.client.get_alarm_devices = AsyncMock(side_effect=SinumConnectionError("err"))
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "test_entry"
        async_add_entities = MagicMock()

        await async_setup_entry(MagicMock(), entry, async_add_entities)

        async_add_entities.assert_not_called()

    @pytest.mark.asyncio
    async def test_two_zones_create_two_entities(self):
        coordinator = MagicMock()
        coordinator.client.get_alarm_devices = AsyncMock(
            return_value=[_make_zone(1), _make_zone(2, zone_status="armed", armed=True)]
        )
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "test_entry"
        added = []
        async_add_entities = MagicMock(side_effect=lambda e: added.extend(e))

        await async_setup_entry(MagicMock(), entry, async_add_entities)

        assert len(added) == 2


class TestAlarmZoneState:
    def test_disarmed_state(self):
        zone = _make_zone(zone_status="disarmed", violated=False)
        entity = _make_entity(zone)
        assert entity.alarm_state == AlarmControlPanelState.DISARMED

    def test_armed_state_maps_to_armed_away(self):
        zone = _make_zone(zone_status="armed", armed=True)
        entity = _make_entity(zone)
        assert entity.alarm_state == AlarmControlPanelState.ARMED_AWAY

    def test_violated_state_maps_to_triggered(self):
        zone = _make_zone(zone_status="armed", armed=True, violated=True)
        entity = _make_entity(zone)
        assert entity.alarm_state == AlarmControlPanelState.TRIGGERED

    def test_violated_overrides_armed_status(self):
        # Even if zone_status is "disarmed" but violated, show TRIGGERED
        zone = _make_zone(zone_status="disarmed", violated=True)
        entity = _make_entity(zone)
        assert entity.alarm_state == AlarmControlPanelState.TRIGGERED

    def test_missing_zone_returns_disarmed(self):
        zone = _make_zone(zone_id=99)
        entity = _make_entity(zone, alarm_zones={})  # zone not in coordinator
        assert entity.alarm_state == AlarmControlPanelState.DISARMED

    def test_unknown_zone_status_returns_disarmed(self):
        zone = _make_zone(zone_status="unknown_future_state")
        entity = _make_entity(zone)
        assert entity.alarm_state == AlarmControlPanelState.DISARMED


class TestAlarmZoneAttributes:
    def test_extra_attributes_contain_delays(self):
        zone = _make_zone(zone_status="disarmed")
        entity = _make_entity(zone)
        attrs = entity.extra_state_attributes
        assert attrs["entry_delay_s"] == 15
        assert attrs["exit_delay_s"] == 15

    def test_extra_attributes_contain_inputs(self):
        zone = _make_zone()
        entity = _make_entity(zone)
        attrs = entity.extra_state_attributes
        assert "inputs" in attrs
        assert attrs["inputs"] == ["sbus/10"]

    def test_no_inputs_omits_key(self):
        zone = _make_zone()
        zone["associations"] = {"inputs": []}
        entity = _make_entity(zone)
        assert "inputs" not in entity.extra_state_attributes

    def test_missing_delays_omit_keys(self):
        zone = _make_zone()
        zone.pop("enter_time_delay")
        zone.pop("exit_time_delay")
        entity = _make_entity(zone)
        attrs = entity.extra_state_attributes
        assert "entry_delay_s" not in attrs
        assert "exit_delay_s" not in attrs


class TestAlarmZoneIdentity:
    def test_unique_id(self):
        zone = _make_zone(zone_id=5)
        entity = _make_entity(zone)
        assert entity.unique_id == "test_entry_alarm_5"

    def test_no_supported_features(self):
        from homeassistant.components.alarm_control_panel import AlarmControlPanelEntityFeature
        zone = _make_zone()
        entity = _make_entity(zone)
        assert entity.supported_features == AlarmControlPanelEntityFeature.ARM_AWAY

    def test_coordinator_update_writes_state(self):
        zone = _make_zone()
        entity = _make_entity(zone)
        entity._handle_coordinator_update()
        entity.async_write_ha_state.assert_called_once()

    def test_icon(self):
        zone = _make_zone()
        entity = _make_entity(zone)
        assert entity.icon == "mdi:shield-home"
