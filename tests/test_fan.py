"""Tests for fan.py — SinumFanCoilFan entity."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.sinum.fan import (
    SinumFanCoilFan,
    _add_fan_entities,
    _has_fan_control,
    async_setup_entry,
)
from custom_components.sinum.const import STYPE_FAN_COIL, WTYPE_FAN_COIL, WTYPE_FAN_COIL_V2


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_coordinator(*, sbus=None, wtp=None):
    c = MagicMock()
    c.sbus_devices = sbus or {}
    c.wtp_devices = wtp or {}
    c.client = MagicMock()
    return c


def _fan_coil_device(**kwargs):
    base = {
        "type": STYPE_FAN_COIL,
        "work_mode": "automatic",
        "target_temperature": 220,
        "fan": {"relay_fan": {"current_gear": "first"}, "manual_fan_gear": "first"},
        "_device_name": "Fan Coil 1",
        "_area": "Living Room",
    }
    base.update(kwargs)
    return base


def _make_fan_entity(device=None, bus="sbus", entry_id="entry1", device_id=1):
    dev = device or _fan_coil_device()
    store = {device_id: dev}
    if bus == "sbus":
        coordinator = _make_coordinator(sbus=store)
    else:
        coordinator = _make_coordinator(wtp=store)
    coordinator.sbus_devices = store if bus == "sbus" else {}
    coordinator.wtp_devices = store if bus == "wtp" else {}
    entity = SinumFanCoilFan(coordinator, device_id, entry_id, bus)
    entity.coordinator = coordinator
    return entity


# ---------------------------------------------------------------------------
# _has_fan_control
# ---------------------------------------------------------------------------

class TestHasFanControl:
    def test_returns_true_when_fan_and_work_mode_present(self):
        assert _has_fan_control({"fan": {}, "work_mode": "automatic"}) is True

    def test_returns_false_when_fan_absent(self):
        assert _has_fan_control({"work_mode": "automatic"}) is False

    def test_returns_false_when_work_mode_absent(self):
        assert _has_fan_control({"fan": {}}) is False

    def test_returns_false_when_empty(self):
        assert _has_fan_control({}) is False


# ---------------------------------------------------------------------------
# async_setup_entry
# ---------------------------------------------------------------------------

class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_adds_sbus_fan_coil(self):
        device = _fan_coil_device(type=STYPE_FAN_COIL)
        coordinator = _make_coordinator(sbus={1: device})
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "e1"
        added = []
        await async_setup_entry(None, entry, lambda entities, **kw: added.extend(entities))
        assert len(added) == 1
        assert isinstance(added[0], SinumFanCoilFan)

    @pytest.mark.asyncio
    async def test_adds_wtp_fan_coil(self):
        device = _fan_coil_device(type=WTYPE_FAN_COIL)
        coordinator = _make_coordinator(wtp={1: device})
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "e1"
        added = []
        await async_setup_entry(None, entry, lambda entities, **kw: added.extend(entities))
        assert len(added) == 1

    @pytest.mark.asyncio
    async def test_adds_wtp_fan_coil_v2(self):
        device = _fan_coil_device(type=WTYPE_FAN_COIL_V2)
        coordinator = _make_coordinator(wtp={1: device})
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "e1"
        added = []
        await async_setup_entry(None, entry, lambda entities, **kw: added.extend(entities))
        assert len(added) == 1

    @pytest.mark.asyncio
    async def test_skips_device_without_fan(self):
        device = {"type": STYPE_FAN_COIL, "work_mode": "automatic"}  # no "fan" key
        coordinator = _make_coordinator(sbus={1: device})
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "e1"
        added = []
        await async_setup_entry(None, entry, lambda entities, **kw: added.extend(entities))
        assert added == []

    @pytest.mark.asyncio
    async def test_skips_non_fan_coil_type(self):
        device = _fan_coil_device(type="relay")
        coordinator = _make_coordinator(sbus={1: device})
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "e1"
        added = []
        await async_setup_entry(None, entry, lambda entities, **kw: added.extend(entities))
        assert added == []


# ---------------------------------------------------------------------------
# SinumFanCoilFan properties
# ---------------------------------------------------------------------------

class TestFanCoilFanProperties:
    def test_is_on_when_work_mode_not_off(self):
        entity = _make_fan_entity(_fan_coil_device(work_mode="automatic"))
        assert entity.is_on is True

    def test_is_off_when_work_mode_is_off(self):
        entity = _make_fan_entity(_fan_coil_device(work_mode="off"))
        assert entity.is_on is False

    def test_preset_mode_first_gear(self):
        device = _fan_coil_device()
        device["fan"]["relay_fan"]["current_gear"] = "first"
        entity = _make_fan_entity(device)
        assert entity.preset_mode == "1"

    def test_preset_mode_second_gear(self):
        device = _fan_coil_device()
        device["fan"]["relay_fan"]["current_gear"] = "second"
        entity = _make_fan_entity(device)
        assert entity.preset_mode == "2"

    def test_preset_mode_third_gear(self):
        device = _fan_coil_device()
        device["fan"]["relay_fan"]["current_gear"] = "third"
        entity = _make_fan_entity(device)
        assert entity.preset_mode == "3"

    def test_preset_mode_none_when_no_gear(self):
        device = _fan_coil_device()
        device["fan"]["relay_fan"] = {}
        entity = _make_fan_entity(device)
        assert entity.preset_mode is None

    def test_preset_mode_none_when_gear_not_string(self):
        device = _fan_coil_device()
        device["fan"]["relay_fan"]["current_gear"] = 1
        entity = _make_fan_entity(device)
        assert entity.preset_mode is None

    def test_unique_id_includes_fan_suffix(self):
        entity = _make_fan_entity()
        assert entity._attr_unique_id.endswith("_fan")

    def test_device_info_uses_shared_identifier(self):
        entity = _make_fan_entity(device_id=42, bus="wtp", entry_id="e1")
        ident = list(entity._attr_device_info["identifiers"])[0]
        assert ident == ("sinum", "e1_wtp_42")

    def test_wtp_bus_reads_wtp_devices(self):
        device = _fan_coil_device()
        entity = _make_fan_entity(device, bus="wtp")
        assert entity._device == device


# ---------------------------------------------------------------------------
# Analog-output devices (fan.output_type == "analog")
#
# On these devices the relay isn't the active output, so
# fan.relay_fan.current_gear never reflects a manual gear change — the real
# hub payload always reports it stuck at "first" regardless of what gear was
# requested. fan.manual_fan_gear is the field that actually updates.
# ---------------------------------------------------------------------------

def _analog_fan_coil_device(**kwargs):
    base = _fan_coil_device(
        fan={
            "output_type": "analog",
            "manual_fan_gear": "second",
            "relay_fan": {"current_gear": "first"},
            "analog_fan": {
                "manual_first_gear_percent": 30,
                "manual_second_gear_percent": 60,
                "manual_third_gear_percent": 90,
            },
        }
    )
    base.update(kwargs)
    return base


class TestFanCoilFanAnalogOutput:
    def test_preset_mode_reads_manual_fan_gear_not_stale_relay_gear(self):
        entity = _make_fan_entity(_analog_fan_coil_device())
        assert entity.preset_mode == "2"

    def test_relay_output_preset_mode_unaffected(self):
        """Regression: devices without output_type (or "relay") still read current_gear."""
        entity = _make_fan_entity(_fan_coil_device())
        assert entity.preset_mode == "1"

    def test_supported_features_includes_set_speed(self):
        from homeassistant.components.fan import FanEntityFeature

        entity = _make_fan_entity(_analog_fan_coil_device())
        assert FanEntityFeature.SET_SPEED in entity.supported_features

    def test_relay_output_excludes_set_speed(self):
        from homeassistant.components.fan import FanEntityFeature

        entity = _make_fan_entity(_fan_coil_device())
        assert FanEntityFeature.SET_SPEED not in entity.supported_features

    def test_percentage_matches_current_gear(self):
        entity = _make_fan_entity(_analog_fan_coil_device())
        assert entity.percentage == 60

    def test_percentage_none_for_relay_output(self):
        entity = _make_fan_entity(_fan_coil_device())
        assert entity.percentage is None

    def test_percentage_none_when_gear_missing_percent_data(self):
        device = _analog_fan_coil_device()
        device["fan"]["analog_fan"] = {}
        entity = _make_fan_entity(device)
        assert entity.percentage is None

    def test_speed_count_is_three(self):
        entity = _make_fan_entity(_analog_fan_coil_device())
        assert entity.speed_count == 3

    @pytest.mark.asyncio
    async def test_set_percentage_picks_nearest_gear(self):
        entity = _make_fan_entity(_analog_fan_coil_device())
        entity.coordinator.client.patch_sbus_device = AsyncMock(return_value={})
        entity.async_write_ha_state = MagicMock()
        await entity.async_set_percentage(65)
        entity.coordinator.client.patch_sbus_device.assert_called_once_with(
            1, {"fan.manual_fan_gear": "second"}
        )

    @pytest.mark.asyncio
    async def test_set_percentage_noop_when_no_percent_data(self):
        device = _analog_fan_coil_device()
        device["fan"]["analog_fan"] = {}
        entity = _make_fan_entity(device)
        entity.coordinator.client.patch_sbus_device = AsyncMock(return_value={})
        await entity.async_set_percentage(50)
        entity.coordinator.client.patch_sbus_device.assert_not_called()


# ---------------------------------------------------------------------------
# SinumFanCoilFan commands
# ---------------------------------------------------------------------------

class TestFanCoilFanCommands:
    @pytest.mark.asyncio
    async def test_set_preset_mode_sbus(self):
        entity = _make_fan_entity()
        entity.coordinator.client.patch_sbus_device = AsyncMock(
            return_value={"fan": {"manual_fan_gear": "second"}}
        )
        entity.async_write_ha_state = MagicMock()
        await entity.async_set_preset_mode("2")
        entity.coordinator.client.patch_sbus_device.assert_called_once_with(
            1, {"fan.manual_fan_gear": "second"}
        )

    @pytest.mark.asyncio
    async def test_set_preset_mode_wtp(self):
        entity = _make_fan_entity(bus="wtp")
        entity.coordinator.client.patch_wtp_device = AsyncMock(return_value={})
        entity.async_write_ha_state = MagicMock()
        await entity.async_set_preset_mode("3")
        entity.coordinator.client.patch_wtp_device.assert_called_once_with(
            1, {"fan.manual_fan_gear": "third"}
        )

    @pytest.mark.asyncio
    async def test_set_preset_mode_unknown_logs_warning(self):
        entity = _make_fan_entity()
        entity.async_write_ha_state = MagicMock()
        await entity.async_set_preset_mode("99")  # no API call, no error
        entity.async_write_ha_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_preset_mode_raises_on_api_error(self):
        entity = _make_fan_entity()
        entity.coordinator.client.patch_sbus_device = AsyncMock(
            side_effect=Exception("connection error")
        )
        entity.async_write_ha_state = MagicMock()
        with pytest.raises(HomeAssistantError, match="Cannot set fan gear"):
            await entity.async_set_preset_mode("1")

    @pytest.mark.asyncio
    async def test_turn_on_when_off_sets_automatic(self):
        entity = _make_fan_entity(_fan_coil_device(work_mode="off"))
        entity.coordinator.client.patch_sbus_device = AsyncMock(return_value={})
        entity.async_write_ha_state = MagicMock()
        await entity.async_turn_on()
        call_args = entity.coordinator.client.patch_sbus_device.call_args[0][1]
        assert call_args["work_mode"] == "automatic"

    @pytest.mark.asyncio
    async def test_turn_on_with_preset_sets_gear(self):
        entity = _make_fan_entity(_fan_coil_device(work_mode="automatic"))
        entity.coordinator.client.patch_sbus_device = AsyncMock(return_value={})
        entity.async_write_ha_state = MagicMock()
        await entity.async_turn_on(preset_mode="2")
        call_args = entity.coordinator.client.patch_sbus_device.call_args[0][1]
        assert call_args["fan.manual_fan_gear"] == "second"

    @pytest.mark.asyncio
    async def test_turn_on_already_on_no_preset_is_noop(self):
        entity = _make_fan_entity(_fan_coil_device(work_mode="automatic"))
        entity.coordinator.client.patch_sbus_device = AsyncMock(return_value={})
        entity.async_write_ha_state = MagicMock()
        await entity.async_turn_on()
        entity.coordinator.client.patch_sbus_device.assert_not_called()

    @pytest.mark.asyncio
    async def test_turn_on_invalid_preset_ignored(self):
        entity = _make_fan_entity(_fan_coil_device(work_mode="off"))
        entity.coordinator.client.patch_sbus_device = AsyncMock(return_value={})
        entity.async_write_ha_state = MagicMock()
        await entity.async_turn_on(preset_mode="99")
        call_args = entity.coordinator.client.patch_sbus_device.call_args[0][1]
        assert "fan.manual_fan_gear" not in call_args
        assert call_args["work_mode"] == "automatic"

    @pytest.mark.asyncio
    async def test_turn_on_raises_on_api_error(self):
        entity = _make_fan_entity(_fan_coil_device(work_mode="off"))
        entity.coordinator.client.patch_sbus_device = AsyncMock(
            side_effect=Exception("timeout")
        )
        entity.async_write_ha_state = MagicMock()
        with pytest.raises(HomeAssistantError, match="Cannot turn on fan coil"):
            await entity.async_turn_on()

    @pytest.mark.asyncio
    async def test_turn_off_sends_work_mode_off(self):
        entity = _make_fan_entity()
        entity.coordinator.client.patch_sbus_device = AsyncMock(return_value={})
        entity.async_write_ha_state = MagicMock()
        await entity.async_turn_off()
        entity.coordinator.client.patch_sbus_device.assert_called_once_with(
            1, {"work_mode": "off"}
        )

    @pytest.mark.asyncio
    async def test_turn_off_raises_on_api_error(self):
        entity = _make_fan_entity()
        entity.coordinator.client.patch_sbus_device = AsyncMock(
            side_effect=Exception("error")
        )
        entity.async_write_ha_state = MagicMock()
        with pytest.raises(HomeAssistantError, match="Cannot turn off fan coil"):
            await entity.async_turn_off()

    @pytest.mark.asyncio
    async def test_turn_off_wtp_uses_patch_wtp(self):
        entity = _make_fan_entity(bus="wtp")
        entity.coordinator.client.patch_wtp_device = AsyncMock(return_value={})
        entity.async_write_ha_state = MagicMock()
        await entity.async_turn_off()
        entity.coordinator.client.patch_wtp_device.assert_called_once_with(
            1, {"work_mode": "off"}
        )

    @pytest.mark.asyncio
    async def test_patch_raises_for_unrecognized_bus(self):
        entity = _make_fan_entity(bus="unknown_bus")
        entity.async_write_ha_state = MagicMock()
        with pytest.raises(HomeAssistantError, match="Unsupported bus"):
            await entity.async_turn_off()

    @pytest.mark.asyncio
    async def test_set_preset_mode_no_update_when_empty_response(self):
        entity = _make_fan_entity()
        entity.coordinator.client.patch_sbus_device = AsyncMock(return_value={})
        entity.async_write_ha_state = MagicMock()
        await entity.async_set_preset_mode("1")
        entity.async_write_ha_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_turn_on_no_update_when_empty_response(self):
        entity = _make_fan_entity(_fan_coil_device(work_mode="off"))
        entity.coordinator.client.patch_sbus_device = AsyncMock(return_value={})
        entity.async_write_ha_state = MagicMock()
        await entity.async_turn_on()
        entity.async_write_ha_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_turn_on_updates_device_when_response_nonempty(self):
        device = _fan_coil_device(work_mode="off")
        entity = _make_fan_entity(device)
        entity.coordinator.client.patch_sbus_device = AsyncMock(
            return_value={"work_mode": "automatic"}
        )
        entity.async_write_ha_state = MagicMock()
        await entity.async_turn_on()
        assert device.get("work_mode") == "automatic"

    @pytest.mark.asyncio
    async def test_turn_off_no_update_when_empty_response(self):
        entity = _make_fan_entity()
        entity.coordinator.client.patch_sbus_device = AsyncMock(return_value={})
        entity.async_write_ha_state = MagicMock()
        await entity.async_turn_off()
        entity.async_write_ha_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_turn_off_updates_device_when_response_nonempty(self):
        device = _fan_coil_device(work_mode="automatic")
        entity = _make_fan_entity(device)
        entity.coordinator.client.patch_sbus_device = AsyncMock(
            return_value={"work_mode": "off"}
        )
        entity.async_write_ha_state = MagicMock()
        await entity.async_turn_off()
        assert device.get("work_mode") == "off"

    def test_turn_on_payload_with_preset_and_on(self):
        entity = _make_fan_entity(_fan_coil_device(work_mode="automatic"))
        payload = entity._turn_on_payload("2")
        assert payload == {"fan.manual_fan_gear": "second"}

    def test_turn_on_payload_off_no_preset(self):
        entity = _make_fan_entity(_fan_coil_device(work_mode="off"))
        payload = entity._turn_on_payload(None)
        assert payload == {"work_mode": "automatic"}

    def test_add_from_store_skips_wrong_type(self):
        from custom_components.sinum.fan import _add_from_store
        coordinator = _make_coordinator()
        device = {"type": "relay", "fan": {}, "work_mode": "automatic"}
        entities: list = []
        _add_from_store(coordinator, entities, "e1", "sbus", {1: device}, {"fan_coil"})
        assert entities == []
