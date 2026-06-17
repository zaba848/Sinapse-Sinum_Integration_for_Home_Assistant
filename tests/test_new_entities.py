"""Tests for new entities: target_reached binary sensor, DHW switch, valve sensors."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sinum.binary_sensor import SinumBinarySensor, _TARGET_REACHED_SBUS, _TARGET_REACHED_WTP
from custom_components.sinum.switch import SinumDhwSwitch
from custom_components.sinum.sensor import SBUS_SENSORS, SinumSensor


def _make_coordinator(*, wtp=None, sbus=None, virtual=None):
    c = MagicMock()
    c.virtual_devices = virtual or {}
    c.wtp_devices = wtp or {}
    c.sbus_devices = sbus or {}
    c.client = MagicMock()
    c.client.patch_virtual_device = AsyncMock(return_value={})
    c.client.patch_sbus_device = AsyncMock(return_value={})
    c.client.decode_temperature = lambda raw: raw / 10
    return c


def _wire(entity):
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    return entity


# ── target_temperature_reached binary sensor ───────────────────────────────────

class TestTargetReachedBinarySensor:
    def test_wtp_target_reached_is_on(self):
        device = {"id": 10, "type": "temperature_regulator", "target_temperature_reached": True}
        coordinator = _make_coordinator(wtp={10: device})
        entity = SinumBinarySensor(coordinator, 10, _TARGET_REACHED_WTP, "entry1")
        assert entity.is_on is True

    def test_wtp_target_reached_is_off(self):
        device = {"id": 10, "type": "temperature_regulator", "target_temperature_reached": False}
        coordinator = _make_coordinator(wtp={10: device})
        entity = SinumBinarySensor(coordinator, 10, _TARGET_REACHED_WTP, "entry1")
        assert entity.is_on is False

    def test_sbus_target_reached_is_on(self):
        device = {"id": 11, "type": "temperature_regulator", "target_temperature_reached": True}
        coordinator = _make_coordinator(sbus={11: device})
        entity = SinumBinarySensor(coordinator, 11, _TARGET_REACHED_SBUS, "entry1")
        assert entity.is_on is True

    def test_sbus_target_reached_is_off(self):
        device = {"id": 11, "type": "temperature_regulator", "target_temperature_reached": False}
        coordinator = _make_coordinator(sbus={11: device})
        entity = SinumBinarySensor(coordinator, 11, _TARGET_REACHED_SBUS, "entry1")
        assert entity.is_on is False

    def test_wtp_unique_id(self):
        device = {"id": 10, "type": "temperature_regulator", "target_temperature_reached": True}
        coordinator = _make_coordinator(wtp={10: device})
        entity = SinumBinarySensor(coordinator, 10, _TARGET_REACHED_WTP, "entry_abc")
        assert entity.unique_id == "entry_abc_wtp_10_target_reached"

    def test_sbus_unique_id(self):
        device = {"id": 11, "type": "temperature_regulator", "target_temperature_reached": True}
        coordinator = _make_coordinator(sbus={11: device})
        entity = SinumBinarySensor(coordinator, 11, _TARGET_REACHED_SBUS, "entry_abc")
        assert entity.unique_id == "entry_abc_sbus_11_target_reached"

    def test_translation_key(self):
        assert _TARGET_REACHED_WTP.translation_key == "target_reached"
        assert _TARGET_REACHED_SBUS.translation_key == "target_reached"

    def test_no_device_class(self):
        assert _TARGET_REACHED_WTP.device_class is None

    def test_state_key(self):
        assert _TARGET_REACHED_WTP.state_key == "target_temperature_reached"


# ── SinumDhwSwitch ─────────────────────────────────────────────────────────────

class TestDhwSwitch:
    def _make_heat_pump(self, dhw_enabled: bool, dhw_state: bool = False):
        return {
            "id": 5,
            "type": "heat_pump_manager",
            "dhw_control": {
                "enabled": dhw_enabled,
                "state": dhw_state,
                "target_temperature": 720,
                "temperature": 450,
                "hysteresis": 50,
            },
        }

    def test_is_on_when_enabled(self):
        device = self._make_heat_pump(dhw_enabled=True)
        coordinator = _make_coordinator(virtual={5: device})
        entity = SinumDhwSwitch(coordinator, 5, "entry1")
        assert entity.is_on is True

    def test_is_off_when_disabled(self):
        device = self._make_heat_pump(dhw_enabled=False)
        coordinator = _make_coordinator(virtual={5: device})
        entity = SinumDhwSwitch(coordinator, 5, "entry1")
        assert entity.is_on is False

    def test_is_off_when_no_dhw_control(self):
        device = {"id": 5, "type": "heat_pump_manager"}
        coordinator = _make_coordinator(virtual={5: device})
        entity = SinumDhwSwitch(coordinator, 5, "entry1")
        assert entity.is_on is False

    def test_unique_id(self):
        device = self._make_heat_pump(dhw_enabled=False)
        coordinator = _make_coordinator(virtual={5: device})
        entity = SinumDhwSwitch(coordinator, 5, "entry_xyz")
        assert entity.unique_id == "entry_xyz_virtual_5_dhw"

    def test_translation_key(self):
        device = self._make_heat_pump(dhw_enabled=False)
        coordinator = _make_coordinator(virtual={5: device})
        entity = SinumDhwSwitch(coordinator, 5, "entry1")
        assert entity._attr_translation_key == "dhw_control"

    def test_icon(self):
        device = self._make_heat_pump(dhw_enabled=False)
        coordinator = _make_coordinator(virtual={5: device})
        entity = SinumDhwSwitch(coordinator, 5, "entry1")
        assert entity._attr_icon == "mdi:water-boiler"

    def test_extra_attrs_include_dhw_state(self):
        device = self._make_heat_pump(dhw_enabled=True, dhw_state=True)
        coordinator = _make_coordinator(virtual={5: device})
        entity = SinumDhwSwitch(coordinator, 5, "entry1")
        attrs = entity.extra_state_attributes
        assert attrs["dhw_active"] is True
        assert attrs["dhw_temperature_c"] == 45.0
        assert attrs["dhw_target_c"] == 72.0
        assert attrs["hysteresis"] == 5.0

    def test_extra_attrs_empty_when_no_dhw(self):
        device = {"id": 5, "type": "heat_pump_manager"}
        coordinator = _make_coordinator(virtual={5: device})
        entity = SinumDhwSwitch(coordinator, 5, "entry1")
        assert entity.extra_state_attributes == {}

    @pytest.mark.asyncio
    async def test_turn_on_patches_enabled_true(self):
        device = self._make_heat_pump(dhw_enabled=False)
        coordinator = _make_coordinator(virtual={5: device})
        entity = _wire(SinumDhwSwitch(coordinator, 5, "entry1"))
        await entity.async_turn_on()
        coordinator.client.patch_virtual_device.assert_called_once_with(
            5, {"dhw_control": {"enabled": True}}
        )

    @pytest.mark.asyncio
    async def test_turn_off_patches_enabled_false(self):
        device = self._make_heat_pump(dhw_enabled=True)
        coordinator = _make_coordinator(virtual={5: device})
        entity = _wire(SinumDhwSwitch(coordinator, 5, "entry1"))
        await entity.async_turn_off()
        coordinator.client.patch_virtual_device.assert_called_once_with(
            5, {"dhw_control": {"enabled": False}}
        )


# ── common_valve sensors ────────────────────────────────────────────────────────

class TestCommonValveSensors:
    def _valve_desc(self, key: str):
        return next(d for d in SBUS_SENSORS if d.key == key)

    def test_valve_temperature_descriptor_exists(self):
        desc = self._valve_desc("valve_temperature")
        assert desc.api_key == "temperature_valve"
        assert desc.scale == 0.1
        assert desc.translation_key == "valve_temperature"

    def test_valve_position_descriptor_exists(self):
        desc = self._valve_desc("valve_position")
        assert desc.api_key == "open_percent"
        assert desc.translation_key == "valve_position"

    def test_valve_temperature_value(self):
        device = {"id": 20, "type": "common_valve", "temperature_valve": 243}
        coordinator = MagicMock()
        coordinator.virtual_devices = {}
        coordinator.wtp_devices = {}
        coordinator.sbus_devices = {20: device}
        desc = self._valve_desc("valve_temperature")
        entity = SinumSensor(coordinator, 20, desc, "entry1")
        assert abs(entity.native_value - 24.3) < 0.001

    def test_valve_position_value(self):
        device = {"id": 20, "type": "common_valve", "open_percent": 1700}
        coordinator = MagicMock()
        coordinator.virtual_devices = {}
        coordinator.wtp_devices = {}
        coordinator.sbus_devices = {20: device}
        desc = self._valve_desc("valve_position")
        entity = SinumSensor(coordinator, 20, desc, "entry1")
        assert abs(entity.native_value - 17.0) < 0.001

    def test_valve_temperature_none_when_missing(self):
        device = {"id": 20, "type": "common_valve"}
        coordinator = MagicMock()
        coordinator.virtual_devices = {}
        coordinator.wtp_devices = {}
        coordinator.sbus_devices = {20: device}
        desc = self._valve_desc("valve_temperature")
        entity = SinumSensor(coordinator, 20, desc, "entry1")
        assert entity.native_value is None

    def test_valve_temperature_sentinel_returns_none(self):
        device = {"id": 20, "type": "common_valve", "temperature_valve": -32768}
        coordinator = MagicMock()
        coordinator.virtual_devices = {}
        coordinator.wtp_devices = {}
        coordinator.sbus_devices = {20: device}
        desc = self._valve_desc("valve_temperature")
        entity = SinumSensor(coordinator, 20, desc, "entry1")
        assert entity.native_value is None
