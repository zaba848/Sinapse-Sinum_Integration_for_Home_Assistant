"""Tests for new SBUS/WTP device types: button, valve_pump, common_valve, analog_output, PWM, heat_pump_manager."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "sinum_devices.json").read_text())


def _make_coordinator(*, wtp=None, sbus=None, virtual=None):
    c = MagicMock()
    c.virtual_devices = virtual or {}
    c.wtp_devices = wtp or {}
    c.sbus_devices = sbus or {}
    c.client = MagicMock()
    c.client.decode_temperature = lambda raw: raw / 10
    c.client.encode_temperature = lambda c: round(c * 10)
    c.client.patch_virtual_device = AsyncMock(return_value={})
    c.client.patch_wtp_device = AsyncMock(return_value={})
    c.client.patch_sbus_device = AsyncMock(return_value={})
    return c


def _wire(entity):
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    return entity


# ── Button sensor ──────────────────────────────────────────────────────────────


class TestButtonSensor:
    def test_sbus_button_action(self):
        from custom_components.sinum.sensor import SinumButtonSensor

        device = dict(FIXTURES["sbus_button"])
        coordinator = _make_coordinator(sbus={50: device})
        entity = SinumButtonSensor(coordinator, 50, "test_entry", "sbus")
        assert entity.native_value == "single_press"

    def test_wtp_button_action(self):
        from custom_components.sinum.sensor import SinumButtonSensor

        device = dict(FIXTURES["wtp_button"])
        coordinator = _make_coordinator(wtp={51: device})
        entity = SinumButtonSensor(coordinator, 51, "test_entry", "wtp")
        assert entity.native_value == "double_press"

    def test_button_none_when_empty_action(self):
        from custom_components.sinum.sensor import SinumButtonSensor

        device = {"id": 50, "type": "button", "action": ""}
        coordinator = _make_coordinator(sbus={50: device})
        entity = SinumButtonSensor(coordinator, 50, "test_entry", "sbus")
        assert entity.native_value is None

    def test_button_none_when_missing_action(self):
        from custom_components.sinum.sensor import SinumButtonSensor

        device = {"id": 50, "type": "button"}
        coordinator = _make_coordinator(sbus={50: device})
        entity = SinumButtonSensor(coordinator, 50, "test_entry", "sbus")
        assert entity.native_value is None

    def test_button_extra_attributes_include_count(self):
        from custom_components.sinum.sensor import SinumButtonSensor

        device = dict(FIXTURES["sbus_button"])
        coordinator = _make_coordinator(sbus={50: device})
        entity = SinumButtonSensor(coordinator, 50, "test_entry", "sbus")
        attrs = entity.extra_state_attributes
        assert attrs["buttons_count"] == 2

    def test_sbus_button_unique_id(self):
        from custom_components.sinum.sensor import SinumButtonSensor

        device = dict(FIXTURES["sbus_button"])
        coordinator = _make_coordinator(sbus={50: device})
        entity = SinumButtonSensor(coordinator, 50, "entry_x", "sbus")
        assert "entry_x" in entity.unique_id
        assert "50" in entity.unique_id
        assert "last_action" in entity.unique_id


# ── Valve pump binary sensor ───────────────────────────────────────────────────


class TestValvePumpBinarySensor:
    def test_is_on_when_state_true(self):
        from custom_components.sinum.binary_sensor import (
            SBUS_BINARY_SENSOR_TYPES,
            SinumBinarySensor,
        )
        from custom_components.sinum.const import STYPE_VALVE_PUMP

        desc = next(d for d in SBUS_BINARY_SENSOR_TYPES if d.wtp_type == STYPE_VALVE_PUMP)
        device = dict(FIXTURES["sbus_valve_pump"])
        coordinator = _make_coordinator(sbus={52: device})
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "homeassistant.helpers.frame.report_usage", return_value=None
        ):
            entity = SinumBinarySensor(coordinator, 52, desc, "test_entry")
        assert entity.is_on is True

    def test_is_off_when_state_false(self):
        from custom_components.sinum.binary_sensor import (
            SBUS_BINARY_SENSOR_TYPES,
            SinumBinarySensor,
        )
        from custom_components.sinum.const import STYPE_VALVE_PUMP

        desc = next(d for d in SBUS_BINARY_SENSOR_TYPES if d.wtp_type == STYPE_VALVE_PUMP)
        device = dict(FIXTURES["sbus_valve_pump"])
        device["state"] = False
        coordinator = _make_coordinator(sbus={52: device})
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "homeassistant.helpers.frame.report_usage", return_value=None
        ):
            entity = SinumBinarySensor(coordinator, 52, desc, "test_entry")
        assert entity.is_on is False

    def test_unique_id_contains_pump_key(self):
        from custom_components.sinum.binary_sensor import (
            SBUS_BINARY_SENSOR_TYPES,
            SinumBinarySensor,
        )
        from custom_components.sinum.const import STYPE_VALVE_PUMP

        desc = next(d for d in SBUS_BINARY_SENSOR_TYPES if d.wtp_type == STYPE_VALVE_PUMP)
        device = dict(FIXTURES["sbus_valve_pump"])
        coordinator = _make_coordinator(sbus={52: device})
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "homeassistant.helpers.frame.report_usage", return_value=None
        ):
            entity = SinumBinarySensor(coordinator, 52, desc, "entry_y")
        assert "entry_y" in entity.unique_id
        assert "52" in entity.unique_id
        assert "pump" in entity.unique_id


# ── Common valve switch ────────────────────────────────────────────────────────


class TestCommonValveSwitch:
    def test_is_off_when_enabled_false(self):
        from custom_components.sinum.switch import SinumCommonValveSwitch

        device = dict(FIXTURES["sbus_common_valve"])
        coordinator = _make_coordinator(sbus={53: device})
        entity = SinumCommonValveSwitch(coordinator, 53, "test_entry")
        assert entity.is_on is False

    def test_is_on_when_enabled_true(self):
        from custom_components.sinum.switch import SinumCommonValveSwitch

        device = dict(FIXTURES["sbus_common_valve"])
        device["enabled"] = True
        coordinator = _make_coordinator(sbus={53: device})
        entity = SinumCommonValveSwitch(coordinator, 53, "test_entry")
        assert entity.is_on is True

    @pytest.mark.asyncio
    async def test_turn_on_patches_enabled_true(self):
        from custom_components.sinum.switch import SinumCommonValveSwitch

        device = dict(FIXTURES["sbus_common_valve"])
        coordinator = _make_coordinator(sbus={53: device})
        entity = _wire(SinumCommonValveSwitch(coordinator, 53, "test_entry"))
        await entity.async_turn_on()
        coordinator.client.patch_sbus_device.assert_called_once_with(53, {"enabled": True})

    @pytest.mark.asyncio
    async def test_turn_off_patches_enabled_false(self):
        from custom_components.sinum.switch import SinumCommonValveSwitch

        device = dict(FIXTURES["sbus_common_valve"])
        coordinator = _make_coordinator(sbus={53: device})
        entity = _wire(SinumCommonValveSwitch(coordinator, 53, "test_entry"))
        await entity.async_turn_off()
        coordinator.client.patch_sbus_device.assert_called_once_with(53, {"enabled": False})

    def test_extra_attributes_include_blockade_reasons(self):
        from custom_components.sinum.switch import SinumCommonValveSwitch

        device = dict(FIXTURES["sbus_common_valve"])
        coordinator = _make_coordinator(sbus={53: device})
        entity = SinumCommonValveSwitch(coordinator, 53, "test_entry")
        attrs = entity.extra_state_attributes
        assert "blockade" in attrs
        assert "blockade_reasons" in attrs


# ── Analog output number ───────────────────────────────────────────────────────


class TestAnalogOutputNumber:
    def test_native_value(self):
        from custom_components.sinum.number import SinumAnalogOutputNumber

        device = dict(FIXTURES["sbus_analog_output"])
        coordinator = _make_coordinator(sbus={54: device})
        entity = SinumAnalogOutputNumber(coordinator, 54, "test_entry")
        assert entity.native_value == 5000.0

    def test_native_value_none_when_missing(self):
        from custom_components.sinum.number import SinumAnalogOutputNumber

        device = {"id": 54, "type": "analog_output"}
        coordinator = _make_coordinator(sbus={54: device})
        entity = SinumAnalogOutputNumber(coordinator, 54, "test_entry")
        assert entity.native_value is None

    def test_min_max_from_device(self):
        from custom_components.sinum.number import SinumAnalogOutputNumber

        device = dict(FIXTURES["sbus_analog_output"])
        coordinator = _make_coordinator(sbus={54: device})
        entity = SinumAnalogOutputNumber(coordinator, 54, "test_entry")
        assert entity.native_min_value == 0.0
        assert entity.native_max_value == 10000.0

    @pytest.mark.asyncio
    async def test_set_value_calls_patch(self):
        from custom_components.sinum.number import SinumAnalogOutputNumber

        device = dict(FIXTURES["sbus_analog_output"])
        coordinator = _make_coordinator(sbus={54: device})
        entity = _wire(SinumAnalogOutputNumber(coordinator, 54, "test_entry"))
        await entity.async_set_native_value(7500.0)
        coordinator.client.patch_sbus_device.assert_called_once_with(54, {"value": 7500})

    def test_unique_id(self):
        from custom_components.sinum.number import SinumAnalogOutputNumber

        device = dict(FIXTURES["sbus_analog_output"])
        coordinator = _make_coordinator(sbus={54: device})
        entity = SinumAnalogOutputNumber(coordinator, 54, "entry_z")
        assert entity.unique_id == "entry_z_sbus_54"


# ── PWM sensors ────────────────────────────────────────────────────────────────


class TestPwmSensors:
    def _pwm_desc(self, key: str):
        from custom_components.sinum.sensor import SBUS_SENSORS

        return next(d for d in SBUS_SENSORS if d.key == key)

    def test_duty_cycle_value(self):
        from custom_components.sinum.sensor import SinumSensor

        device = dict(FIXTURES["sbus_pwm"])
        coordinator = _make_coordinator(sbus={55: device})
        entity = SinumSensor(coordinator, 55, self._pwm_desc("pwm_duty_cycle"), "test_entry")
        assert entity.native_value == 75.0

    def test_frequency_value(self):
        from custom_components.sinum.sensor import SinumSensor

        device = dict(FIXTURES["sbus_pwm"])
        coordinator = _make_coordinator(sbus={55: device})
        entity = SinumSensor(coordinator, 55, self._pwm_desc("pwm_frequency"), "test_entry")
        assert entity.native_value == 1000.0

    def test_duty_cycle_unit(self):
        from homeassistant.const import PERCENTAGE

        desc = self._pwm_desc("pwm_duty_cycle")
        assert desc.native_unit_of_measurement == PERCENTAGE

    def test_frequency_unit(self):
        from homeassistant.const import UnitOfFrequency

        desc = self._pwm_desc("pwm_frequency")
        assert desc.native_unit_of_measurement == UnitOfFrequency.HERTZ


# ── Heat pump manager climate ──────────────────────────────────────────────────


class TestHeatPumpManagerClimate:
    def _make_hpm(self, device_data):
        from custom_components.sinum.climate import SinumHeatPumpManagerClimate

        coordinator = _make_coordinator(virtual={15: device_data})
        entity = SinumHeatPumpManagerClimate(coordinator, 15, "test_entry")
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        return entity, coordinator

    def test_current_temperature(self):
        device = dict(FIXTURES["virtual_heat_pump_manager"])
        entity, _ = self._make_hpm(device)
        assert entity.current_temperature == 20.0  # 200 / 10

    def test_target_temperature_from_dict(self):
        device = dict(FIXTURES["virtual_heat_pump_manager"])
        entity, _ = self._make_hpm(device)
        assert entity.target_temperature == 21.2  # 212 / 10

    def test_hvac_mode_heat(self):
        from homeassistant.components.climate import HVACMode

        device = dict(FIXTURES["virtual_heat_pump_manager"])
        entity, _ = self._make_hpm(device)
        assert entity.hvac_mode == HVACMode.HEAT

    def test_hvac_mode_off_when_disabled(self):
        from homeassistant.components.climate import HVACMode

        device = {**FIXTURES["virtual_heat_pump_manager"], "enabled": False}
        entity, _ = self._make_hpm(device)
        assert entity.hvac_mode == HVACMode.OFF

    def test_hvac_action_heating_when_state_true(self):
        from homeassistant.components.climate import HVACAction

        device = dict(FIXTURES["virtual_heat_pump_manager"])
        entity, _ = self._make_hpm(device)
        assert entity.hvac_action == HVACAction.HEATING

    def test_hvac_action_idle_when_state_false(self):
        from homeassistant.components.climate import HVACAction

        device = {**FIXTURES["virtual_heat_pump_manager"], "state": False}
        entity, _ = self._make_hpm(device)
        assert entity.hvac_action == HVACAction.IDLE

    def test_hvac_action_off_when_disabled(self):
        from homeassistant.components.climate import HVACAction

        device = {**FIXTURES["virtual_heat_pump_manager"], "enabled": False}
        entity, _ = self._make_hpm(device)
        assert entity.hvac_action == HVACAction.OFF

    def test_extra_attributes_include_mode_temps(self):
        device = dict(FIXTURES["virtual_heat_pump_manager"])
        entity, _ = self._make_hpm(device)
        attrs = entity.extra_state_attributes
        assert attrs["target_temperature_heating"] == 20.0
        assert attrs["target_temperature_cooling"] == 21.2
        assert attrs["dhw_target_temperature"] == 55.0
        assert attrs["dhw_state"] is False

    @pytest.mark.asyncio
    async def test_set_temperature_patches_dict(self):
        device = dict(FIXTURES["virtual_heat_pump_manager"])
        entity, coordinator = self._make_hpm(device)
        await entity.async_set_temperature(temperature=22.0)
        coordinator.client.patch_virtual_device.assert_called_once_with(
            15, {"target_temperature": {"current": 220}}
        )

    @pytest.mark.asyncio
    async def test_set_hvac_mode_off_disables(self):
        from homeassistant.components.climate import HVACMode

        device = dict(FIXTURES["virtual_heat_pump_manager"])
        entity, coordinator = self._make_hpm(device)
        await entity.async_set_hvac_mode(HVACMode.OFF)
        coordinator.client.patch_virtual_device.assert_called_once_with(15, {"enabled": False})

    @pytest.mark.asyncio
    async def test_set_hvac_mode_cool_enables_and_sets_mode(self):
        from homeassistant.components.climate import HVACMode

        device = dict(FIXTURES["virtual_heat_pump_manager"])
        entity, coordinator = self._make_hpm(device)
        await entity.async_set_hvac_mode(HVACMode.COOL)
        coordinator.client.patch_virtual_device.assert_called_once_with(
            15, {"enabled": True, "work_mode": "cooling"}
        )

    @pytest.mark.asyncio
    async def test_turn_on_patches_enabled_true(self):
        device = {**FIXTURES["virtual_heat_pump_manager"], "enabled": False}
        entity, coordinator = self._make_hpm(device)
        await entity.async_turn_on()
        coordinator.client.patch_virtual_device.assert_called_once_with(15, {"enabled": True})

    @pytest.mark.asyncio
    async def test_turn_off_patches_enabled_false(self):
        device = dict(FIXTURES["virtual_heat_pump_manager"])
        entity, coordinator = self._make_hpm(device)
        await entity.async_turn_off()
        coordinator.client.patch_virtual_device.assert_called_once_with(15, {"enabled": False})

    def test_unique_id(self):
        device = dict(FIXTURES["virtual_heat_pump_manager"])
        entity, _ = self._make_hpm(device)
        assert entity.unique_id == "test_entry_virtual_15"
