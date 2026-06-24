"""Tests for device_trigger.py — Sinum button device triggers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sinum.device_trigger import (
    TRIGGER_TYPE_PRESSED,
    async_attach_trigger,
    async_get_triggers,
    async_validate_trigger_config,
)
from custom_components.sinum.const import DOMAIN


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_entry(entity_id: str, domain: str = "event", platform: str = DOMAIN) -> MagicMock:
    entry = MagicMock()
    entry.entity_id = entity_id
    entry.domain = domain
    entry.platform = platform
    return entry


def _make_state_changed_event(
    entity_id: str,
    action: str | None = "single",
    old_state_is_none: bool = False,
) -> MagicMock:
    new_state = MagicMock()
    new_state.entity_id = entity_id
    new_state.attributes = {"action": action}
    event = MagicMock()
    event.data = {
        "new_state": new_state,
        "old_state": None if old_state_is_none else MagicMock(),
    }
    return event


def _make_hass() -> MagicMock:
    hass = MagicMock()
    hass.async_run_hass_job = MagicMock()
    return hass


def _standard_config(device_id: str = "dev-abc") -> dict:
    return {
        "platform": "device",
        "domain": DOMAIN,
        "device_id": device_id,
        "type": TRIGGER_TYPE_PRESSED,
    }


# ── async_validate_trigger_config ─────────────────────────────────────────────


class TestValidateTriggerConfig:
    async def test_valid_config_passes(self):
        config = _standard_config()
        result = await async_validate_trigger_config(MagicMock(), config)
        assert result["type"] == TRIGGER_TYPE_PRESSED

    async def test_invalid_type_raises(self):
        import voluptuous as vol

        config = {**_standard_config(), "type": "released"}
        with pytest.raises(vol.Invalid):
            await async_validate_trigger_config(MagicMock(), config)

    async def test_missing_type_raises(self):
        import voluptuous as vol

        config = {"platform": "device", "domain": DOMAIN, "device_id": "abc"}
        with pytest.raises(vol.Invalid):
            await async_validate_trigger_config(MagicMock(), config)


# ── async_get_triggers ────────────────────────────────────────────────────────


class TestGetTriggers:
    async def test_returns_pressed_trigger_for_event_entity(self):
        entries = [_make_entry("event.sinum_btn_1")]
        with (
            patch("custom_components.sinum.device_trigger.er.async_get"),
            patch(
                "custom_components.sinum.device_trigger.er.async_entries_for_device",
                return_value=entries,
            ),
        ):
            triggers = await async_get_triggers(_make_hass(), "device-123")

        assert len(triggers) == 1
        assert triggers[0]["type"] == TRIGGER_TYPE_PRESSED
        assert triggers[0]["device_id"] == "device-123"
        assert triggers[0]["domain"] == DOMAIN

    async def test_returns_multiple_triggers_for_multiple_event_entities(self):
        entries = [
            _make_entry("event.sinum_btn_1"),
            _make_entry("event.sinum_btn_2"),
            _make_entry("event.sinum_btn_3"),
        ]
        with (
            patch("custom_components.sinum.device_trigger.er.async_get"),
            patch(
                "custom_components.sinum.device_trigger.er.async_entries_for_device",
                return_value=entries,
            ),
        ):
            triggers = await async_get_triggers(_make_hass(), "device-multi")

        assert len(triggers) == 3

    async def test_ignores_non_event_domain_entities(self):
        entries = [
            _make_entry("sensor.sinum_btn_1", domain="sensor"),
            _make_entry("event.sinum_btn_2", domain="event"),
        ]
        with (
            patch("custom_components.sinum.device_trigger.er.async_get"),
            patch(
                "custom_components.sinum.device_trigger.er.async_entries_for_device",
                return_value=entries,
            ),
        ):
            triggers = await async_get_triggers(_make_hass(), "device-mixed")

        assert len(triggers) == 1

    async def test_ignores_entities_from_other_platforms(self):
        entries = [_make_entry("event.btn", domain="event", platform="other_integration")]
        with (
            patch("custom_components.sinum.device_trigger.er.async_get"),
            patch(
                "custom_components.sinum.device_trigger.er.async_entries_for_device",
                return_value=entries,
            ),
        ):
            triggers = await async_get_triggers(_make_hass(), "device-other")

        assert len(triggers) == 0

    async def test_returns_empty_when_no_event_entities(self):
        with (
            patch("custom_components.sinum.device_trigger.er.async_get"),
            patch(
                "custom_components.sinum.device_trigger.er.async_entries_for_device",
                return_value=[],
            ),
        ):
            triggers = await async_get_triggers(_make_hass(), "device-empty")

        assert triggers == []


# ── async_attach_trigger ──────────────────────────────────────────────────────


class TestAttachTrigger:
    async def test_returns_noop_when_no_event_entities(self):
        with (
            patch("custom_components.sinum.device_trigger.er.async_get"),
            patch(
                "custom_components.sinum.device_trigger.er.async_entries_for_device",
                return_value=[],
            ),
        ):
            hass = _make_hass()
            unsubscribe = await async_attach_trigger(
                hass, _standard_config(), AsyncMock(), MagicMock()
            )
        assert callable(unsubscribe)
        unsubscribe()  # should not raise

    async def test_registers_state_changed_listener(self):
        entries = [_make_entry("event.sinum_btn_1")]
        with (
            patch("custom_components.sinum.device_trigger.er.async_get"),
            patch(
                "custom_components.sinum.device_trigger.er.async_entries_for_device",
                return_value=entries,
            ),
        ):
            hass = _make_hass()
            unsubscribe_mock = MagicMock()
            hass.bus.async_listen = MagicMock(return_value=unsubscribe_mock)
            result = await async_attach_trigger(
                hass, _standard_config(), MagicMock(), MagicMock()
            )

        hass.bus.async_listen.assert_called_once()
        assert hass.bus.async_listen.call_args[0][0] == "state_changed"
        assert result == unsubscribe_mock

    async def _attach_and_capture(self, entries: list) -> tuple[MagicMock, object]:
        """Helper: attach trigger, capture the listener callback."""
        hass = _make_hass()
        captured: list = []

        def capture_listen(event_type, listener):
            captured.append(listener)
            return MagicMock()

        hass.bus.async_listen = capture_listen

        with (
            patch("custom_components.sinum.device_trigger.er.async_get"),
            patch(
                "custom_components.sinum.device_trigger.er.async_entries_for_device",
                return_value=entries,
            ),
        ):
            await async_attach_trigger(hass, _standard_config("my-dev"), MagicMock(), MagicMock())

        return hass, captured[0] if captured else None

    async def test_fires_action_on_button_press(self):
        entity_id = "event.sinum_btn_1"
        entries = [_make_entry(entity_id)]
        hass = _make_hass()
        captured: list = []

        def capture_listen(event_type, listener):
            captured.append(listener)
            return MagicMock()

        hass.bus.async_listen = capture_listen
        action = MagicMock()

        with (
            patch("custom_components.sinum.device_trigger.er.async_get"),
            patch(
                "custom_components.sinum.device_trigger.er.async_entries_for_device",
                return_value=entries,
            ),
        ):
            await async_attach_trigger(hass, _standard_config(), action, MagicMock())

        listener = captured[0]
        listener(_make_state_changed_event(entity_id, action="single"))
        hass.async_run_hass_job.assert_called_once()
        payload = hass.async_run_hass_job.call_args[0][1]
        assert payload["action"] == "single"
        assert payload["entity_id"] == entity_id

    async def test_skips_initial_state_write(self):
        entity_id = "event.sinum_btn_1"
        entries = [_make_entry(entity_id)]
        hass = _make_hass()
        captured: list = []

        def capture_listen(event_type, listener):
            captured.append(listener)
            return MagicMock()

        hass.bus.async_listen = capture_listen

        with (
            patch("custom_components.sinum.device_trigger.er.async_get"),
            patch(
                "custom_components.sinum.device_trigger.er.async_entries_for_device",
                return_value=entries,
            ),
        ):
            await async_attach_trigger(hass, _standard_config(), MagicMock(), MagicMock())

        listener = captured[0]
        listener(_make_state_changed_event(entity_id, old_state_is_none=True))
        hass.async_run_hass_job.assert_not_called()

    async def test_ignores_events_for_other_entities(self):
        entity_id = "event.sinum_btn_1"
        entries = [_make_entry(entity_id)]
        hass = _make_hass()
        captured: list = []

        def capture_listen(event_type, listener):
            captured.append(listener)
            return MagicMock()

        hass.bus.async_listen = capture_listen

        with (
            patch("custom_components.sinum.device_trigger.er.async_get"),
            patch(
                "custom_components.sinum.device_trigger.er.async_entries_for_device",
                return_value=entries,
            ),
        ):
            await async_attach_trigger(hass, _standard_config(), MagicMock(), MagicMock())

        listener = captured[0]
        listener(_make_state_changed_event("event.some_other_entity"))
        hass.async_run_hass_job.assert_not_called()

    async def test_skips_when_new_state_is_none(self):
        entity_id = "event.sinum_btn_1"
        entries = [_make_entry(entity_id)]
        hass = _make_hass()
        captured: list = []

        def capture_listen(event_type, listener):
            captured.append(listener)
            return MagicMock()

        hass.bus.async_listen = capture_listen

        with (
            patch("custom_components.sinum.device_trigger.er.async_get"),
            patch(
                "custom_components.sinum.device_trigger.er.async_entries_for_device",
                return_value=entries,
            ),
        ):
            await async_attach_trigger(hass, _standard_config(), MagicMock(), MagicMock())

        listener = captured[0]
        bad_event = MagicMock()
        bad_event.data = {"new_state": None, "old_state": MagicMock()}
        listener(bad_event)
        hass.async_run_hass_job.assert_not_called()

    async def test_trigger_payload_includes_config_fields(self):
        entity_id = "event.sinum_btn_1"
        entries = [_make_entry(entity_id)]
        hass = _make_hass()
        captured: list = []

        def capture_listen(event_type, listener):
            captured.append(listener)
            return MagicMock()

        hass.bus.async_listen = capture_listen
        config = _standard_config("my-device")

        with (
            patch("custom_components.sinum.device_trigger.er.async_get"),
            patch(
                "custom_components.sinum.device_trigger.er.async_entries_for_device",
                return_value=entries,
            ),
        ):
            await async_attach_trigger(hass, config, MagicMock(), MagicMock())

        listener = captured[0]
        listener(_make_state_changed_event(entity_id, action="double"))
        payload = hass.async_run_hass_job.call_args[0][1]
        trigger = payload["trigger"]
        assert trigger["device_id"] == "my-device"
        assert trigger["domain"] == DOMAIN
        assert trigger["type"] == TRIGGER_TYPE_PRESSED
        assert "description" in trigger

    async def test_fires_for_action_none(self):
        """Action=None (SBUS poll missed the action type) should still fire the trigger."""
        entity_id = "event.sinum_btn_1"
        entries = [_make_entry(entity_id)]
        hass = _make_hass()
        captured: list = []

        def capture_listen(event_type, listener):
            captured.append(listener)
            return MagicMock()

        hass.bus.async_listen = capture_listen

        with (
            patch("custom_components.sinum.device_trigger.er.async_get"),
            patch(
                "custom_components.sinum.device_trigger.er.async_entries_for_device",
                return_value=entries,
            ),
        ):
            await async_attach_trigger(hass, _standard_config(), MagicMock(), MagicMock())

        listener = captured[0]
        listener(_make_state_changed_event(entity_id, action=None))
        hass.async_run_hass_job.assert_called_once()
        payload = hass.async_run_hass_job.call_args[0][1]
        assert payload["action"] is None
