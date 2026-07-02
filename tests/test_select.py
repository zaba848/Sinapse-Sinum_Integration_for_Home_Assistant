"""Tests for SinumFanCoilModeSelect (select.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.sinum.api import SinumConnectionError
from custom_components.sinum.select import (
    SinumFanCoilModeSelect,
    _needs_select,
    _work_mode_options,
    async_setup_entry,
)
from custom_components.sinum.const import STYPE_FAN_COIL


def _make_coordinator(sbus=None, wtp=None):
    c = MagicMock()
    c.sbus_devices = sbus or {}
    c.wtp_devices = wtp or {}
    c.hub_info = {}
    c.client = MagicMock()
    return c


def _make_entry(coordinator):
    e = MagicMock()
    e.runtime_data = coordinator
    e.entry_id = "sel1"
    return e


def _make_sensor(device, bus="sbus"):
    c = _make_coordinator(sbus={1: device} if bus == "sbus" else {}, wtp={1: device} if bus == "wtp" else {})
    c.client.patch_sbus_device = AsyncMock(return_value=device)
    c.client.patch_wtp_device = AsyncMock(return_value=device)
    return SinumFanCoilModeSelect(c, 1, "sel1", bus)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TestNeedsSelect:
    def test_true_when_work_mode_no_target_temp(self):
        assert _needs_select({"work_mode": "automatic"}) is True

    def test_false_when_target_temperature_present(self):
        assert _needs_select({"work_mode": "automatic", "target_temperature": 220}) is False

    def test_false_when_no_work_mode(self):
        assert _needs_select({"target_temperature": 220}) is False

    def test_false_empty(self):
        assert _needs_select({}) is False


class TestWorkModeOptions:
    def test_declared_modes_used_when_present(self):
        device = {"available_work_modes": ["heating", "cooling"]}
        assert _work_mode_options(device) == ["heating", "cooling"]

    def test_defaults_when_no_declared(self):
        opts = _work_mode_options({})
        assert "heating" in opts
        assert "automatic" in opts

    def test_empty_list_falls_back_to_defaults(self):
        opts = _work_mode_options({"available_work_modes": []})
        assert "heating" in opts


# ---------------------------------------------------------------------------
# SinumFanCoilModeSelect
# ---------------------------------------------------------------------------

class TestSinumFanCoilModeSelect:
    def test_unique_id(self):
        sensor = _make_sensor({"type": STYPE_FAN_COIL, "work_mode": "automatic"})
        assert sensor._attr_unique_id == "sel1_sbus_1_work_mode"

    def test_current_option_from_device(self):
        sensor = _make_sensor({"type": STYPE_FAN_COIL, "work_mode": "cooling"})
        assert sensor.current_option == "cooling"

    def test_current_option_none_when_missing(self):
        sensor = _make_sensor({"type": STYPE_FAN_COIL})
        assert sensor.current_option is None

    def test_options_from_device(self):
        sensor = _make_sensor({
            "type": STYPE_FAN_COIL,
            "work_mode": "heating",
            "available_work_modes": ["heating", "cooling"],
        })
        assert sensor._attr_options == ["heating", "cooling"]

    def test_translation_key(self):
        sensor = _make_sensor({"type": STYPE_FAN_COIL, "work_mode": "off"})
        assert sensor._attr_translation_key == "fan_coil_work_mode"

    @pytest.mark.asyncio
    async def test_select_option_sbus(self):
        device = {"type": STYPE_FAN_COIL, "work_mode": "automatic"}
        sensor = _make_sensor(device, bus="sbus")
        sensor.coordinator.client.patch_sbus_device = AsyncMock(return_value={"work_mode": "cooling"})
        sensor.async_write_ha_state = MagicMock()
        await sensor.async_select_option("cooling")
        sensor.coordinator.client.patch_sbus_device.assert_called_once_with(1, {"work_mode": "cooling"})

    @pytest.mark.asyncio
    async def test_select_option_wtp(self):
        device = {"type": STYPE_FAN_COIL, "work_mode": "automatic"}
        sensor = _make_sensor(device, bus="wtp")
        sensor.coordinator.client.patch_wtp_device = AsyncMock(return_value={"work_mode": "heating"})
        sensor.async_write_ha_state = MagicMock()
        await sensor.async_select_option("heating")
        sensor.coordinator.client.patch_wtp_device.assert_called_once_with(1, {"work_mode": "heating"})

    @pytest.mark.asyncio
    async def test_select_option_raises_on_error(self):
        device = {"type": STYPE_FAN_COIL, "work_mode": "automatic"}
        sensor = _make_sensor(device, bus="sbus")
        sensor.coordinator.client.patch_sbus_device = AsyncMock(side_effect=Exception("fail"))
        sensor.async_write_ha_state = MagicMock()
        with pytest.raises(HomeAssistantError):
            await sensor.async_select_option("cooling")


# ---------------------------------------------------------------------------
# async_setup_entry
# ---------------------------------------------------------------------------

class TestSelectSetup:
    @pytest.mark.asyncio
    async def test_fan_coil_without_target_temp_gets_select(self):
        device = {"type": STYPE_FAN_COIL, "work_mode": "automatic"}
        coordinator = _make_coordinator(sbus={1: device})
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        assert len(added) == 1
        assert isinstance(added[0], SinumFanCoilModeSelect)

    @pytest.mark.asyncio
    async def test_fan_coil_with_target_temp_skipped(self):
        device = {"type": STYPE_FAN_COIL, "work_mode": "automatic", "target_temperature": 220}
        coordinator = _make_coordinator(sbus={1: device})
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        assert len(added) == 0

    @pytest.mark.asyncio
    async def test_no_work_mode_device_skipped(self):
        device = {"type": STYPE_FAN_COIL}
        coordinator = _make_coordinator(sbus={1: device})
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        assert len(added) == 0

    @pytest.mark.asyncio
    async def test_multiple_fan_coils_both_added(self):
        devices = {
            1: {"type": STYPE_FAN_COIL, "work_mode": "heating"},
            2: {"type": STYPE_FAN_COIL, "work_mode": "cooling"},
        }
        coordinator = _make_coordinator(sbus=devices)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        assert len(added) == 2
