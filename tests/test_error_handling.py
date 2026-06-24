"""Tests for HomeAssistantError propagation on API failures in all entity write methods.

Each write operation (set_hvac_mode, turn_on, turn_off, set_cover_position, etc.)
must raise HomeAssistantError when the API raises SinumConnectionError (e.g. 408 bus busy).
This prevents raw exceptions from surfacing in the HA UI as internal errors.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.exceptions import HomeAssistantError

from custom_components.sinum.api import SinumConnectionError

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _coordinator(virtual=None, wtp=None, sbus=None, lora=None):
    c = MagicMock()
    c.virtual_devices = virtual or {}
    c.wtp_devices = wtp or {}
    c.sbus_devices = sbus or {}
    c.lora_devices = lora or {}
    c.client = MagicMock()
    c.client.encode_temperature = lambda t: round(t * 10)
    c.client.decode_temperature = lambda r: r / 10
    c.client.patch_virtual_device = AsyncMock(return_value={})
    c.client.patch_wtp_device = AsyncMock(return_value={})
    c.client.patch_sbus_device = AsyncMock(return_value={})
    c.client.patch_lora_device = AsyncMock(return_value={})
    c.client.set_variable = AsyncMock(return_value={})
    return c


def _wire(entity):
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    return entity


_BUS_ERR = SinumConnectionError("Hub internal timeout for /api/v1/devices/virtual/9 (bus may be busy)")


# ===========================================================================
# Climate — SinumThermostat
# ===========================================================================

class TestThermostatErrors:
    def _make(self, device=None):
        from custom_components.sinum.climate import SinumThermostat
        dev = device or {"id": 1, "type": "thermostat", "mode": "heating",
                         "target_temperature": 220, "temperature": 215}
        c = _coordinator(virtual={1: dev})
        return _wire(SinumThermostat(c, 1, "e")), c

    @pytest.mark.asyncio
    async def test_set_hvac_mode_raises_homeassistant_error(self):
        entity, c = self._make()
        c.client.patch_virtual_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot set HVAC mode"):
            await entity.async_set_hvac_mode(HVACMode.OFF)

    @pytest.mark.asyncio
    async def test_set_temperature_raises_homeassistant_error(self):
        entity, c = self._make()
        c.client.patch_virtual_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot set temperature"):
            await entity.async_set_temperature(temperature=22.0)

    @pytest.mark.asyncio
    async def test_set_hvac_mode_heat_propagates_error(self):
        entity, c = self._make()
        c.client.patch_virtual_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError):
            await entity.async_set_hvac_mode(HVACMode.HEAT)

    @pytest.mark.asyncio
    async def test_set_hvac_mode_cool_propagates_error(self):
        entity, c = self._make()
        c.client.patch_virtual_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError):
            await entity.async_set_hvac_mode(HVACMode.COOL)


# ===========================================================================
# Climate — SinumFanCoilClimate (SBUS)
# ===========================================================================

class TestFanCoilErrors:
    def _make(self, device=None):
        from custom_components.sinum.climate import SinumFanCoilClimate
        dev = device or {"id": 5, "type": "fan_coil", "work_mode": "heating",
                         "target_temperature": 220}
        c = _coordinator(sbus={5: dev})
        return _wire(SinumFanCoilClimate(c, 5, "e", "sbus")), c

    @pytest.mark.asyncio
    async def test_set_hvac_mode_raises_homeassistant_error(self):
        entity, c = self._make()
        c.client.patch_sbus_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot set HVAC mode"):
            await entity.async_set_hvac_mode(HVACMode.OFF)

    @pytest.mark.asyncio
    async def test_set_fan_mode_raises_homeassistant_error(self):
        entity, c = self._make()
        c.client.patch_sbus_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot set fan mode"):
            await entity.async_set_fan_mode("1")

    @pytest.mark.asyncio
    async def test_set_temperature_raises_homeassistant_error(self):
        entity, c = self._make()
        c.client.patch_sbus_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot set temperature"):
            await entity.async_set_temperature(temperature=21.0)


# ===========================================================================
# Climate — SinumFanCoilClimate (WTP)
# ===========================================================================

class TestFanCoilWtpErrors:
    def _make(self):
        from custom_components.sinum.climate import SinumFanCoilClimate
        from custom_components.sinum.const import WTYPE_FAN_COIL
        dev = {"id": 7, "type": WTYPE_FAN_COIL, "work_mode": "heating",
               "target_temperature": 220, "room_temperature": 215}
        c = _coordinator(wtp={7: dev})
        return _wire(SinumFanCoilClimate(c, 7, "e", "wtp")), c

    @pytest.mark.asyncio
    async def test_set_hvac_mode_raises_homeassistant_error(self):
        entity, c = self._make()
        c.client.patch_wtp_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot set HVAC mode"):
            await entity.async_set_hvac_mode(HVACMode.OFF)


# ===========================================================================
# Climate — SinumTemperatureRegulatorClimate
# ===========================================================================

class TestTemperatureRegulatorErrors:
    def _make(self, bus="sbus"):
        from custom_components.sinum.climate import SinumTemperatureRegulatorClimate
        dev = {"id": 6, "type": "temperature_regulator", "system_mode": "heating",
               "target_temperature": 220, "mode_mutable": True}
        store = {6: dev}
        c = _coordinator(sbus=store if bus == "sbus" else {}, wtp=store if bus == "wtp" else {})
        return _wire(SinumTemperatureRegulatorClimate(c, 6, "e", bus)), c

    @pytest.mark.asyncio
    async def test_set_hvac_mode_raises_homeassistant_error_sbus(self):
        entity, c = self._make("sbus")
        c.client.patch_sbus_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot set HVAC mode"):
            await entity.async_set_hvac_mode(HVACMode.OFF)

    @pytest.mark.asyncio
    async def test_set_hvac_mode_raises_homeassistant_error_wtp(self):
        entity, c = self._make("wtp")
        c.client.patch_wtp_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot set HVAC mode"):
            await entity.async_set_hvac_mode(HVACMode.OFF)

    @pytest.mark.asyncio
    async def test_turn_on_raises_homeassistant_error(self):
        entity, c = self._make()
        c.client.patch_sbus_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot turn on"):
            await entity.async_turn_on()

    @pytest.mark.asyncio
    async def test_turn_off_raises_homeassistant_error(self):
        entity, c = self._make()
        c.client.patch_sbus_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot turn off"):
            await entity.async_turn_off()


# ===========================================================================
# Climate — SinumHeatPumpManagerClimate
# ===========================================================================

class TestHeatPumpManagerErrors:
    def _make(self):
        from custom_components.sinum.climate import SinumHeatPumpManagerClimate
        from custom_components.sinum.const import VTYPE_HEAT_PUMP_MANAGER
        dev = {"id": 3, "type": VTYPE_HEAT_PUMP_MANAGER, "enabled": True, "work_mode": "heating"}
        c = _coordinator(virtual={3: dev})
        return _wire(SinumHeatPumpManagerClimate(c, 3, "e")), c

    @pytest.mark.asyncio
    async def test_set_hvac_mode_off_raises_homeassistant_error(self):
        entity, c = self._make()
        c.client.patch_virtual_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot set HVAC mode"):
            await entity.async_set_hvac_mode(HVACMode.OFF)

    @pytest.mark.asyncio
    async def test_set_hvac_mode_heat_raises_homeassistant_error(self):
        entity, c = self._make()
        c.client.patch_virtual_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot set HVAC mode"):
            await entity.async_set_hvac_mode(HVACMode.HEAT)

    @pytest.mark.asyncio
    async def test_turn_on_raises_homeassistant_error(self):
        entity, c = self._make()
        c.client.patch_virtual_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot turn on"):
            await entity.async_turn_on()

    @pytest.mark.asyncio
    async def test_turn_off_raises_homeassistant_error(self):
        entity, c = self._make()
        c.client.patch_virtual_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot turn off"):
            await entity.async_turn_off()


# ===========================================================================
# Switch
# ===========================================================================

class TestSwitchErrors:
    def _make_relay(self):
        from custom_components.sinum.switch import SinumRelaySwitch
        dev = {"id": 2, "type": "relay_integrator", "state": False}
        c = _coordinator(virtual={2: dev})
        return _wire(SinumRelaySwitch(c, 2, "e")), c

    def _make_wicket(self):
        from custom_components.sinum.switch import SinumWicketSwitch
        dev = {"id": 4, "type": "wicket", "state": "locked"}
        c = _coordinator(virtual={4: dev})
        return _wire(SinumWicketSwitch(c, 4, "e")), c

    def _make_bus_relay(self, bus="wtp"):
        from custom_components.sinum.switch import SinumBusRelaySwitch
        dev = {"id": 8, "type": "relay", "state": False}
        store = {8: dev}
        c = _coordinator(
            wtp=store if bus == "wtp" else {},
            sbus=store if bus == "sbus" else {},
            lora=store if bus == "lora" else {},
        )
        return _wire(SinumBusRelaySwitch(c, 8, "e", bus)), c

    def _make_common_valve(self):
        from custom_components.sinum.switch import SinumCommonValveSwitch
        dev = {"id": 10, "type": "common_valve", "enabled": False}
        c = _coordinator(sbus={10: dev})
        return _wire(SinumCommonValveSwitch(c, 10, "e")), c

    @pytest.mark.asyncio
    async def test_relay_turn_on_raises_homeassistant_error(self):
        entity, c = self._make_relay()
        c.client.patch_virtual_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot turn on"):
            await entity.async_turn_on()

    @pytest.mark.asyncio
    async def test_relay_turn_off_raises_homeassistant_error(self):
        entity, c = self._make_relay()
        c.client.patch_virtual_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot turn off"):
            await entity.async_turn_off()

    @pytest.mark.asyncio
    async def test_wicket_turn_on_raises_homeassistant_error(self):
        entity, c = self._make_wicket()
        c.client.patch_virtual_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot unlock"):
            await entity.async_turn_on()

    @pytest.mark.asyncio
    async def test_wicket_turn_off_raises_homeassistant_error(self):
        entity, c = self._make_wicket()
        c.client.patch_virtual_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot lock"):
            await entity.async_turn_off()

    @pytest.mark.asyncio
    async def test_bus_relay_wtp_turn_on_raises_homeassistant_error(self):
        entity, c = self._make_bus_relay("wtp")
        c.client.patch_wtp_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot turn on"):
            await entity.async_turn_on()

    @pytest.mark.asyncio
    async def test_bus_relay_sbus_turn_on_raises_homeassistant_error(self):
        entity, c = self._make_bus_relay("sbus")
        c.client.patch_sbus_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot turn on"):
            await entity.async_turn_on()

    @pytest.mark.asyncio
    async def test_bus_relay_lora_turn_on_raises_homeassistant_error(self):
        entity, c = self._make_bus_relay("lora")
        c.client.patch_lora_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot turn on"):
            await entity.async_turn_on()

    @pytest.mark.asyncio
    async def test_bus_relay_wtp_turn_off_raises_homeassistant_error(self):
        entity, c = self._make_bus_relay("wtp")
        c.client.patch_wtp_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot turn off"):
            await entity.async_turn_off()

    @pytest.mark.asyncio
    async def test_common_valve_turn_on_raises_homeassistant_error(self):
        entity, c = self._make_common_valve()
        c.client.patch_sbus_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError):
            await entity.async_turn_on()

    @pytest.mark.asyncio
    async def test_common_valve_turn_off_raises_homeassistant_error(self):
        entity, c = self._make_common_valve()
        c.client.patch_sbus_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError):
            await entity.async_turn_off()


# ===========================================================================
# Light
# ===========================================================================

class TestLightErrors:
    def _make_virtual_dimmer(self):
        from custom_components.sinum.light import SinumDimmerLight
        dev = {"id": 11, "type": "dimmer_rgb_controller_integrator", "state": False,
               "brightness": 50}
        c = _coordinator(virtual={11: dev})
        return _wire(SinumDimmerLight(c, 11, "e")), c

    def _make_bus_dimmer(self, bus="wtp"):
        from custom_components.sinum.light import SinumBusDimmerLight
        dev = {"id": 12, "type": "dimmer", "state": False, "target_level": 50}
        store = {12: dev}
        c = _coordinator(
            wtp=store if bus == "wtp" else {},
            sbus=store if bus == "sbus" else {},
        )
        return _wire(SinumBusDimmerLight(c, 12, "e", bus)), c

    def _make_bus_rgb(self, bus="wtp"):
        from custom_components.sinum.light import SinumBusRgbLight
        dev = {"id": 13, "type": "rgb_controller", "state": False,
               "brightness": 50, "color": "#ff0000"}
        store = {13: dev}
        c = _coordinator(
            wtp=store if bus == "wtp" else {},
            sbus=store if bus == "sbus" else {},
        )
        return _wire(SinumBusRgbLight(c, 13, "e", bus)), c

    @pytest.mark.asyncio
    async def test_virtual_dimmer_turn_on_raises_homeassistant_error(self):
        entity, c = self._make_virtual_dimmer()
        c.client.patch_virtual_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot turn on"):
            await entity.async_turn_on()

    @pytest.mark.asyncio
    async def test_virtual_dimmer_turn_off_raises_homeassistant_error(self):
        entity, c = self._make_virtual_dimmer()
        c.client.patch_virtual_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot turn off"):
            await entity.async_turn_off()

    @pytest.mark.asyncio
    async def test_bus_dimmer_wtp_turn_on_raises_homeassistant_error(self):
        entity, c = self._make_bus_dimmer("wtp")
        c.client.patch_wtp_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot turn on"):
            await entity.async_turn_on()

    @pytest.mark.asyncio
    async def test_bus_dimmer_sbus_turn_off_raises_homeassistant_error(self):
        entity, c = self._make_bus_dimmer("sbus")
        c.client.patch_sbus_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot turn off"):
            await entity.async_turn_off()

    @pytest.mark.asyncio
    async def test_bus_rgb_wtp_turn_on_raises_homeassistant_error(self):
        entity, c = self._make_bus_rgb("wtp")
        c.client.patch_wtp_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot turn on"):
            await entity.async_turn_on()

    @pytest.mark.asyncio
    async def test_bus_rgb_sbus_turn_off_raises_homeassistant_error(self):
        entity, c = self._make_bus_rgb("sbus")
        c.client.patch_sbus_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot turn off"):
            await entity.async_turn_off()


# ===========================================================================
# Cover
# ===========================================================================

class TestCoverErrors:
    def _make_blind(self):
        from custom_components.sinum.cover import SinumBlindCover
        dev = {"id": 14, "type": "blind_controller_integrator", "state": "open",
               "last_set_target_opening": 100}
        c = _coordinator(virtual={14: dev})
        return _wire(SinumBlindCover(c, 14, "e")), c

    def _make_gate(self):
        from custom_components.sinum.cover import SinumGateCover
        dev = {"id": 15, "type": "gate", "state": "closed"}
        c = _coordinator(virtual={15: dev})
        return _wire(SinumGateCover(c, 15, "e")), c

    def _make_wtp_blind(self):
        from custom_components.sinum.cover import SinumWtpBlindCover
        dev = {"id": 16, "type": "blind_controller", "current_opening": 100}
        c = _coordinator(wtp={16: dev})
        return _wire(SinumWtpBlindCover(c, 16, "e")), c

    def _make_sbus_blind(self):
        from custom_components.sinum.cover import SinumSbusBlindCover
        dev = {"id": 17, "type": "blind_controller", "current_opening": 100}
        c = _coordinator(sbus={17: dev})
        return _wire(SinumSbusBlindCover(c, 17, "e")), c

    @pytest.mark.asyncio
    async def test_blind_open_raises_homeassistant_error(self):
        entity, c = self._make_blind()
        c.client.patch_virtual_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot open cover"):
            await entity.async_open_cover()

    @pytest.mark.asyncio
    async def test_blind_close_raises_homeassistant_error(self):
        entity, c = self._make_blind()
        c.client.patch_virtual_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot close cover"):
            await entity.async_close_cover()

    @pytest.mark.asyncio
    async def test_blind_stop_raises_homeassistant_error(self):
        entity, c = self._make_blind()
        c.client.patch_virtual_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot stop cover"):
            await entity.async_stop_cover()

    @pytest.mark.asyncio
    async def test_blind_set_position_raises_homeassistant_error(self):
        entity, c = self._make_blind()
        c.client.patch_virtual_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot set cover position"):
            await entity.async_set_cover_position(position=50)

    @pytest.mark.asyncio
    async def test_gate_open_raises_homeassistant_error(self):
        entity, c = self._make_gate()
        c.client.patch_virtual_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot open gate"):
            await entity.async_open_cover()

    @pytest.mark.asyncio
    async def test_gate_close_raises_homeassistant_error(self):
        entity, c = self._make_gate()
        c.client.patch_virtual_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot close gate"):
            await entity.async_close_cover()

    @pytest.mark.asyncio
    async def test_gate_stop_raises_homeassistant_error(self):
        entity, c = self._make_gate()
        c.client.patch_virtual_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot stop gate"):
            await entity.async_stop_cover()

    @pytest.mark.asyncio
    async def test_wtp_blind_open_raises_homeassistant_error(self):
        entity, c = self._make_wtp_blind()
        c.client.patch_wtp_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot open cover"):
            await entity.async_open_cover()

    @pytest.mark.asyncio
    async def test_wtp_blind_close_raises_homeassistant_error(self):
        entity, c = self._make_wtp_blind()
        c.client.patch_wtp_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot close cover"):
            await entity.async_close_cover()

    @pytest.mark.asyncio
    async def test_wtp_blind_set_position_raises_homeassistant_error(self):
        entity, c = self._make_wtp_blind()
        c.client.patch_wtp_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot set cover position"):
            await entity.async_set_cover_position(position=50)

    @pytest.mark.asyncio
    async def test_sbus_blind_open_raises_homeassistant_error(self):
        entity, c = self._make_sbus_blind()
        c.client.patch_sbus_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot open cover"):
            await entity.async_open_cover()

    @pytest.mark.asyncio
    async def test_sbus_blind_set_tilt_raises_homeassistant_error(self):
        entity, c = self._make_sbus_blind()
        c.client.patch_sbus_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot set cover tilt"):
            await entity.async_set_cover_tilt_position(tilt_position=45)


# ===========================================================================
# Number
# ===========================================================================

class TestNumberErrors:
    def _make_variable(self):
        from custom_components.sinum.number import SinumVariableNumber
        var = {"id": 20, "name": "setpoint", "value": 21.0,
               "min": 5.0, "max": 30.0}
        c = _coordinator()
        c.hub_info = {}
        c.variables = [var]
        return _wire(SinumVariableNumber(c, var, "e")), c

    def _make_analog_output(self):
        from custom_components.sinum.number import SinumAnalogOutputNumber
        dev = {"id": 21, "type": "analog_output", "value": 0,
               "value_minimum": 0, "value_maximum": 10000}
        c = _coordinator(sbus={21: dev})
        return _wire(SinumAnalogOutputNumber(c, 21, "e")), c

    def _make_pwm(self):
        from custom_components.sinum.number import SinumPwmNumber
        dev = {"id": 22, "type": "pulse_width_modulation", "duty_cycle": 50}
        c = _coordinator(sbus={22: dev})
        return _wire(SinumPwmNumber(c, 22, "e")), c

    @pytest.mark.asyncio
    async def test_variable_set_value_raises_homeassistant_error(self):
        entity, c = self._make_variable()
        c.client.set_variable = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot set variable"):
            await entity.async_set_native_value(22.0)

    @pytest.mark.asyncio
    async def test_analog_output_set_value_raises_homeassistant_error(self):
        entity, c = self._make_analog_output()
        c.client.patch_sbus_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot set analog output"):
            await entity.async_set_native_value(5000.0)

    @pytest.mark.asyncio
    async def test_pwm_set_value_raises_homeassistant_error(self):
        entity, c = self._make_pwm()
        c.client.patch_sbus_device = AsyncMock(side_effect=_BUS_ERR)
        with pytest.raises(HomeAssistantError, match="Cannot set PWM"):
            await entity.async_set_native_value(75.0)
