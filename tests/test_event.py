"""Tests for SinumButtonEvent entity."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.sinum.event import SinumButtonEvent, SinumMotionEvent, async_setup_entry
from custom_components.sinum.sensor import SinumButtonSensor


def _make_coordinator(wtp_devices=None, sbus_devices=None, virtual_devices=None):
    coordinator = MagicMock()
    coordinator.wtp_devices = wtp_devices or {}
    coordinator.sbus_devices = sbus_devices or {}
    coordinator.virtual_devices = virtual_devices or {}
    coordinator.hass.config_entries.async_entries.return_value = []
    return coordinator


def _make_wtp_button(action="single_press"):
    return {
        "id": 51,
        "name": "WTP Button",
        "type": "button",
        "action": action,
        "buttons_count": 1,
        "_device_name": "WTP Button",
        "_area": "Living Room",
        "class": "wtp",
    }


def _make_sbus_button(action="single_press"):
    return {
        "id": 50,
        "name": "SBUS Button",
        "type": "button",
        "action": action,
        "buttons_count": 2,
        "_device_name": "SBUS Button",
        "_area": "Kitchen",
        "class": "sbus",
    }


class TestSinumButtonEvent:
    def _make_entity(self, bus="wtp", action="single_press"):
        if bus == "wtp":
            device = _make_wtp_button(action)
            coordinator = _make_coordinator(wtp_devices={51: device})
        else:
            device = _make_sbus_button(action)
            coordinator = _make_coordinator(sbus_devices={50: device})

        device_id = 51 if bus == "wtp" else 50
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumButtonEvent(coordinator, device_id, "test_entry", bus)
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        return entity, coordinator

    def test_event_types(self):
        entity, _ = self._make_entity()
        assert entity.event_types == ["pressed"]

    def test_translation_key(self):
        entity, _ = self._make_entity()
        assert entity._attr_translation_key == "button_press"

    def test_initial_prev_action_set_from_device(self):
        """On creation, _prev_action is set to current action — no event fires on load."""
        entity, _ = self._make_entity(action="single_press")
        assert entity._prev_action == "single_press"

    def test_no_event_when_action_unchanged(self):
        entity, coordinator = self._make_entity(action="single_press")
        fired = []
        entity._trigger_event = lambda t, a: fired.append((t, a))

        # Update with same action
        coordinator.wtp_devices[51]["action"] = "single_press"
        entity._handle_coordinator_update()

        assert fired == []

    def test_event_fired_on_action_change(self):
        entity, coordinator = self._make_entity(bus="wtp", action="single_press")
        fired = []
        entity._trigger_event = lambda t, a: fired.append((t, a))

        # Action changes
        coordinator.wtp_devices[51]["action"] = "double_press"
        entity._handle_coordinator_update()

        assert len(fired) == 1
        assert fired[0][0] == "pressed"
        assert fired[0][1]["action"] == "double_press"

    def test_prev_action_updated_after_event(self):
        entity, coordinator = self._make_entity(bus="wtp", action="single_press")
        entity._trigger_event = MagicMock()

        coordinator.wtp_devices[51]["action"] = "double_press"
        entity._handle_coordinator_update()

        assert entity._prev_action == "double_press"

    def test_no_event_when_action_is_none(self):
        entity, coordinator = self._make_entity(bus="wtp", action="single_press")
        fired = []
        entity._trigger_event = lambda t, a: fired.append((t, a))

        coordinator.wtp_devices[51].pop("action", None)
        entity._handle_coordinator_update()

        assert fired == []

    def test_no_event_when_action_is_empty_string(self):
        entity, coordinator = self._make_entity(bus="wtp", action="single_press")
        fired = []
        entity._trigger_event = lambda t, a: fired.append((t, a))

        coordinator.wtp_devices[51]["action"] = ""
        entity._handle_coordinator_update()

        assert fired == []

    def test_wtp_button_unique_id(self):
        entity, _ = self._make_entity(bus="wtp")
        assert entity.unique_id == "test_entry_wtp_51_event"

    def test_sbus_button_unique_id(self):
        entity, _ = self._make_entity(bus="sbus")
        assert entity.unique_id == "test_entry_sbus_50_event"

    def test_sbus_button_reads_sbus_store(self):
        entity, coordinator = self._make_entity(bus="sbus", action="single_press")
        fired = []
        entity._trigger_event = lambda t, a: fired.append((t, a))

        coordinator.sbus_devices[50]["action"] = "long_press"
        entity._handle_coordinator_update()

        assert len(fired) == 1
        assert fired[0][1]["action"] == "long_press"

    def test_event_fired_when_count_increments_same_action(self):
        """Two presses of the same type in a row: action unchanged but buttons_count increments."""
        entity, coordinator = self._make_entity(bus="wtp", action="single_press")
        fired = []
        entity._trigger_event = lambda t, a: fired.append((t, a))

        # Same action, count goes from 1 → 2
        coordinator.wtp_devices[51]["action"] = "single_press"
        coordinator.wtp_devices[51]["buttons_count"] = 2
        entity._handle_coordinator_update()

        assert len(fired) == 1
        assert fired[0][1]["action"] == "single_press"
        assert fired[0][1]["buttons_count"] == 2

    def test_sbus_event_fires_with_none_action_when_count_increments_and_action_empty(self):
        """SBUS buttons reset action to '' before poll — count change alone fires event with action=None."""
        entity, coordinator = self._make_entity(bus="wtp", action="single_press")
        fired = []
        entity._trigger_event = lambda t, a: fired.append((t, a))

        coordinator.wtp_devices[51]["action"] = ""
        coordinator.wtp_devices[51]["buttons_count"] = 2
        entity._handle_coordinator_update()

        assert len(fired) == 1
        assert fired[0][1]["action"] is None
        assert fired[0][1]["buttons_count"] == 2

    def test_count_updated_even_without_event(self):
        """_prev_count is updated when count changes even if no event fires (action empty)."""
        entity, coordinator = self._make_entity(bus="wtp", action="single_press")
        entity._trigger_event = MagicMock()

        coordinator.wtp_devices[51]["action"] = ""
        coordinator.wtp_devices[51]["buttons_count"] = 5
        entity._handle_coordinator_update()

        assert entity._prev_count == 5

    @pytest.mark.asyncio
    async def test_setup_creates_wtp_and_sbus_entities(self):
        wtp_button = _make_wtp_button()
        sbus_button = _make_sbus_button()
        coordinator = _make_coordinator(
            wtp_devices={51: wtp_button},
            sbus_devices={50: sbus_button},
        )
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "test_entry"

        added = []
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            await async_setup_entry(
                MagicMock(), entry, lambda entities, **_: added.extend(entities)
            )

        assert len(added) == 2
        buses = {e._bus for e in added}
        assert buses == {"wtp", "sbus"}


class TestSinumButtonSensorDisabledByDefault:
    def test_entity_registry_enabled_default_via_instance(self):
        coordinator = _make_coordinator(wtp_devices={51: _make_wtp_button()})
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumButtonSensor(coordinator, 51, "test_entry", "wtp")
        assert entity.entity_registry_enabled_default is False


class TestEventSetupFiltering:
    @pytest.mark.asyncio
    async def test_setup_skips_non_button_devices(self):
        coordinator = _make_coordinator(
            wtp_devices={1: {"id": 1, "type": "relay"}},
            sbus_devices={2: {"id": 2, "type": "temperature_sensor"}},
        )
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "test_entry"

        added = []
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            await async_setup_entry(
                MagicMock(), entry, lambda entities, **_: added.extend(entities)
            )

        assert added == []


class TestSinumMotionEvent:
    def _make_coordinator(self, virtual_devices=None):
        coordinator = MagicMock()
        coordinator.virtual_devices = virtual_devices or {}
        coordinator.wtp_devices = {}
        coordinator.sbus_devices = {}
        coordinator.hass.config_entries.async_entries.return_value = []
        return coordinator

    def _make_entity(self, device_type="ip_camera"):
        device = {
            "id": 10,
            "type": device_type,
            "name": "Camera 1",
            "_device_name": "Camera 1",
            "_area": "Front Door",
            "_parent_model": "Sinum IP Camera",
        }
        coordinator = self._make_coordinator(virtual_devices={10: device})
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumMotionEvent(coordinator, 10, "test_entry")
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        return entity, coordinator

    def test_unique_id(self):
        entity, _ = self._make_entity()
        assert entity.unique_id == "test_entry_motion_10"

    def test_event_types(self):
        entity, _ = self._make_entity()
        assert entity.event_types == ["motion_detected"]

    def test_translation_key(self):
        entity, _ = self._make_entity()
        assert entity._attr_translation_key == "motion_detected"

    def test_device_info_name_no_prefix_single_hub(self):
        entity, _ = self._make_entity()
        assert entity._attr_device_info["name"] == "Camera 1"

    def test_motion_event_fires_trigger(self):
        entity, coordinator = self._make_entity()
        fired = []
        entity._trigger_event = lambda t, a: fired.append((t, a))

        coordinator.get_motion_event.return_value = {"timestamp": 1234567890, "device_id": 10}
        entity._handle_coordinator_update()

        assert len(fired) == 1
        assert fired[0][0] == "motion_detected"
        assert fired[0][1]["timestamp"] == 1234567890
        entity.async_write_ha_state.assert_called_once()

    def test_no_event_when_no_motion(self):
        entity, coordinator = self._make_entity()
        fired = []
        entity._trigger_event = lambda t, a: fired.append((t, a))

        coordinator.get_motion_event.return_value = None
        entity._handle_coordinator_update()

        assert fired == []
        entity.async_write_ha_state.assert_not_called()

    def test_motion_event_with_none_timestamp(self):
        entity, coordinator = self._make_entity()
        fired = []
        entity._trigger_event = lambda t, a: fired.append((t, a))

        coordinator.get_motion_event.return_value = {"device_id": 10}
        entity._handle_coordinator_update()

        assert len(fired) == 1
        assert fired[0][1]["timestamp"] is None

    @pytest.mark.asyncio
    async def test_setup_creates_motion_entity_for_ip_camera(self):
        device = {"id": 10, "type": "ip_camera", "name": "Front Camera", "_device_name": "Front Camera"}
        coordinator = self._make_coordinator(virtual_devices={10: device})
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "test_entry"

        added = []
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            await async_setup_entry(
                MagicMock(), entry, lambda entities, **_: added.extend(entities)
            )

        motion = [e for e in added if isinstance(e, SinumMotionEvent)]
        assert len(motion) == 1

    @pytest.mark.asyncio
    async def test_setup_creates_motion_entity_for_onvif_camera(self):
        device = {"id": 11, "type": "onvif_camera", "name": "ONVIF Cam", "_device_name": "ONVIF Cam"}
        coordinator = self._make_coordinator(virtual_devices={11: device})
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "test_entry"

        added = []
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            await async_setup_entry(
                MagicMock(), entry, lambda entities, **_: added.extend(entities)
            )

        motion = [e for e in added if isinstance(e, SinumMotionEvent)]
        assert len(motion) == 1

    @pytest.mark.asyncio
    async def test_setup_skips_non_camera_virtual_devices(self):
        device = {"id": 20, "type": "thermostat", "name": "Thermostat"}
        coordinator = self._make_coordinator(virtual_devices={20: device})
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "test_entry"

        added = []
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            await async_setup_entry(
                MagicMock(), entry, lambda entities, **_: added.extend(entities)
            )

        assert not any(isinstance(e, SinumMotionEvent) for e in added)
