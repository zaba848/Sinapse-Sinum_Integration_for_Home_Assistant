"""Extended tests for climate.py edge cases and entity behavior.

Covers:
- async_setup_entry (lines 77-81, 85-88, 97)
- helper functions _is_thermostat, _has_climate_control, _available_hvac_modes
  (lines 105, 117, 135-150)
- SinumThermostat: hvac_modes, current/target temp None, hvac_action branches,
  min/max for HEAT/COOL modes, extra_state_attributes (lines 181, 191, 198,
  209-217, 227, 229-232, 246, 248-251, 265, 280)
- SinumFanCoilClimate: current temp None, min/max, hvac_action cooling/idle,
  extra attrs, set_temperature error (lines 368, 388, 396, 413, 416, 431, 453-454)
- SinumTemperatureRegulatorClimate SBUS: current temp, hvac_modes, target None,
  hvac_action, set_temperature no-op, SBUS patch (lines 532, 536, 542, 567-574,
  594, 619)
- SinumHeatPumpManagerClimate: current/target temp None, hvac_mode/action,
  set_temperature branches, set_hvac_mode, turn_on, turn_off
  (lines 664, 671, 674, 691, 718, 726, 729-730, 732, 746, 754, 762)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.climate import HVACAction, HVACMode
from homeassistant.exceptions import HomeAssistantError

from custom_components.sinum.api import SinumConnectionError
from custom_components.sinum.climate import (
    SinumFanCoilClimate,
    SinumHeatPumpManagerClimate,
    SinumTemperatureRegulatorClimate,
    SinumThermostat,
    _available_hvac_modes,
    _has_climate_control,
    _is_thermostat,
    async_setup_entry,
)
from custom_components.sinum.const import (
    STYPE_FAN_COIL,
    TEMP_MAX,
    TEMP_MIN,
    VTYPE_HEAT_PUMP_MANAGER,
    WTYPE_FAN_COIL,
)


# ---------------------------------------------------------------------------
# Shared helpers (same pattern as test_climate_fixes.py)
# ---------------------------------------------------------------------------

def _make_coordinator(virtual=None, wtp=None, sbus=None):
    c = MagicMock()
    c.virtual_devices = virtual or {}
    c.wtp_devices = wtp or {}
    c.sbus_devices = sbus or {}
    c.client = MagicMock()
    c.client.encode_temperature = lambda t: round(t * 10)
    c.client.decode_temperature = lambda r: r / 10
    c.client.patch_virtual_device = AsyncMock(return_value={})
    c.client.patch_wtp_device = AsyncMock(return_value={})
    c.client.patch_sbus_device = AsyncMock(return_value={})
    return c


def _wire(entity):
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    return entity


# ---------------------------------------------------------------------------
# 1. async_setup_entry
# ---------------------------------------------------------------------------

class TestAsyncSetupEntry:
    """Test that async_setup_entry creates the right entity types."""

    @pytest.mark.asyncio
    async def test_setup_creates_heat_pump_manager(self):
        """VTYPE_HEAT_PUMP_MANAGER virtual device → SinumHeatPumpManagerClimate."""
        device = {"id": 1, "type": VTYPE_HEAT_PUMP_MANAGER, "enabled": True, "work_mode": "heating"}
        coordinator = _make_coordinator(virtual={1: device})

        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "e1"

        added = []
        await async_setup_entry(MagicMock(), entry, lambda ents, **kw: added.extend(ents))

        assert len(added) == 1
        assert isinstance(added[0], SinumHeatPumpManagerClimate)

    @pytest.mark.asyncio
    async def test_setup_creates_sbus_fan_coil_climate(self):
        """SBUS fan_coil with work_mode + target_temperature → SinumFanCoilClimate."""
        device = {
            "id": 5,
            "type": STYPE_FAN_COIL,
            "work_mode": "heating",
            "target_temperature": 220,
        }
        coordinator = _make_coordinator(sbus={5: device})

        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "e2"

        added = []
        await async_setup_entry(MagicMock(), entry, lambda ents, **kw: added.extend(ents))

        assert len(added) == 1
        assert isinstance(added[0], SinumFanCoilClimate)
        assert added[0]._source == "sbus"

    @pytest.mark.asyncio
    async def test_setup_creates_sbus_temperature_regulator(self):
        """SBUS temperature_regulator → SinumTemperatureRegulatorClimate (bus=sbus)."""
        device = {"id": 6, "type": "temperature_regulator", "system_mode": "heating"}
        coordinator = _make_coordinator(sbus={6: device})

        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "e3"

        added = []
        await async_setup_entry(MagicMock(), entry, lambda ents, **kw: added.extend(ents))

        assert len(added) == 1
        assert isinstance(added[0], SinumTemperatureRegulatorClimate)
        assert added[0]._bus == "sbus"

    @pytest.mark.asyncio
    async def test_setup_creates_wtp_temperature_regulator(self):
        """WTP temperature_regulator → SinumTemperatureRegulatorClimate (bus=wtp)."""
        device = {
            "id": 100,
            "type": "temperature_regulator",
            "system_mode": "heating",
            "target_temperature": 220,
            "mode_mutable": True,
        }
        coordinator = _make_coordinator(wtp={100: device})

        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "e4"

        added = []
        await async_setup_entry(MagicMock(), entry, lambda ents, **kw: added.extend(ents))

        assert len(added) == 1
        assert isinstance(added[0], SinumTemperatureRegulatorClimate)
        assert added[0]._bus == "wtp"

    @pytest.mark.asyncio
    async def test_setup_creates_wtp_fan_coil(self):
        """WTP fan_coil with climate fields → SinumFanCoilClimate (source=wtp)."""
        device = {
            "id": 22,
            "type": WTYPE_FAN_COIL,
            "work_mode": "heating",
            "target_temperature": 220,
            "room_temperature": 195,
        }
        coordinator = _make_coordinator(wtp={22: device})

        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "e5"

        added = []
        await async_setup_entry(MagicMock(), entry, lambda ents, **kw: added.extend(ents))

        assert len(added) == 1
        assert isinstance(added[0], SinumFanCoilClimate)
        assert added[0]._source == "wtp"

    @pytest.mark.asyncio
    async def test_setup_creates_thermostat_for_thermostat_type(self):
        """Virtual device with type=thermostat → SinumThermostat."""
        device = {
            "id": 10,
            "type": "thermostat",
            "temperature": 215,
            "target_temperature": 220,
            "mode": "heating",
        }
        coordinator = _make_coordinator(virtual={10: device})

        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "e6"

        added = []
        await async_setup_entry(MagicMock(), entry, lambda ents, **kw: added.extend(ents))

        assert len(added) == 1
        assert isinstance(added[0], SinumThermostat)

    @pytest.mark.asyncio
    async def test_setup_empty_coordinator_adds_nothing(self):
        """Empty coordinator produces no entities."""
        coordinator = _make_coordinator()
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "e7"

        added = []
        await async_setup_entry(MagicMock(), entry, lambda ents, **kw: added.extend(ents))

        assert added == []


# ---------------------------------------------------------------------------
# 2. Helper function coverage
# ---------------------------------------------------------------------------

class TestIsThermostat:
    def test_type_thermostat(self):
        assert _is_thermostat({"type": "thermostat"}) is True

    def test_duck_type_match(self):
        """Has target_temperature and temperature but no work_mode → thermostat."""
        assert _is_thermostat({"target_temperature": 220, "temperature": 215}) is True

    def test_duck_type_with_work_mode_not_thermostat(self):
        """Has work_mode → not a thermostat (fan coil)."""
        assert _is_thermostat({"target_temperature": 220, "temperature": 215, "work_mode": "heating"}) is False

    def test_unrelated_device(self):
        assert _is_thermostat({"type": "relay_integrator"}) is False


class TestHasClimateControl:
    def test_sbus_with_both_fields(self):
        device = {"work_mode": "heating", "target_temperature": 220}
        assert _has_climate_control(device, source="sbus") is True

    def test_sbus_missing_field(self):
        device = {"work_mode": "heating"}  # no target_temperature
        assert _has_climate_control(device, source="sbus") is False

    def test_wtp_with_work_mode_only(self):
        assert _has_climate_control({"work_mode": "heating"}, source="wtp") is False

    def test_wtp_with_room_temperature(self):
        assert _has_climate_control({"room_temperature": 195}, source="wtp") is False

    def test_wtp_with_full_control_fields(self):
        device = {"work_mode": "heating", "target_temperature": 220}
        assert _has_climate_control(device, source="wtp") is True

    def test_wtp_empty_device(self):
        assert _has_climate_control({}, source="wtp") is False


class TestAvailableHvacModes:
    def test_declared_modes_used_directly(self):
        device = {"available_work_modes": ["heating", "cooling"]}
        modes = _available_hvac_modes(device)
        assert HVACMode.OFF in modes
        assert HVACMode.HEAT in modes
        assert HVACMode.COOL in modes

    def test_declared_modes_skips_unknown(self):
        device = {"available_work_modes": ["unknown_mode"]}
        modes = _available_hvac_modes(device)
        # Only OFF should survive (unknown_mode has no mapping)
        assert modes == [HVACMode.OFF]

    def test_inferred_from_heating_range(self):
        device = {"target_temperature_heating_minimum": 100, "target_temperature_heating_maximum": 300}
        modes = _available_hvac_modes(device)
        assert HVACMode.HEAT in modes

    def test_inferred_from_cooling_range(self):
        device = {"target_temperature_cooling_minimum": 100, "target_temperature_cooling_maximum": 300}
        modes = _available_hvac_modes(device)
        assert HVACMode.COOL in modes

    def test_current_mode_included(self):
        """Active mode always appears even if not inferred from range."""
        device = {"mode": "automatic"}
        modes = _available_hvac_modes(device)
        assert HVACMode.AUTO in modes

    def test_fallback_heat_when_no_info(self):
        """If nothing inferred and no current mode, HEAT is added as fallback."""
        modes = _available_hvac_modes({})
        assert HVACMode.HEAT in modes

    def test_cooling_not_duplicated(self):
        device = {
            "available_work_modes": ["cooling"],
            "target_temperature_cooling_minimum": 100,
        }
        modes = _available_hvac_modes(device)
        assert modes.count(HVACMode.COOL) == 1


# ---------------------------------------------------------------------------
# 3. SinumThermostat — uncovered branches
# ---------------------------------------------------------------------------

class TestSinumThermostatExtended:
    def _make(self, device: dict):
        c = _make_coordinator(virtual={1: device})
        entity = _wire(SinumThermostat(c, 1, "e"))
        return entity, c

    # line 181 — hvac_modes
    def test_hvac_modes_returns_list(self):
        entity, _ = self._make({"id": 1, "type": "thermostat", "mode": "heating"})
        modes = entity.hvac_modes
        assert isinstance(modes, list)
        assert HVACMode.OFF in modes

    # line 191 — current_temperature None
    def test_current_temperature_none_when_missing(self):
        entity, _ = self._make({"id": 1})
        assert entity.current_temperature is None

    # line 198 — target_temperature None
    def test_target_temperature_none_when_missing(self):
        entity, _ = self._make({"id": 1})
        assert entity.target_temperature is None

    # lines 209-217 — hvac_action branches
    def test_hvac_action_cooling_when_state_true_and_cooling(self):
        entity, _ = self._make({"id": 1, "state": True, "mode": "cooling"})
        assert entity.hvac_action == HVACAction.COOLING

    def test_hvac_action_heating_when_state_true_not_cooling(self):
        entity, _ = self._make({"id": 1, "state": True, "mode": "heating"})
        assert entity.hvac_action == HVACAction.HEATING

    def test_hvac_action_off_when_mode_off(self):
        entity, _ = self._make({"id": 1, "state": False, "mode": "off"})
        assert entity.hvac_action == HVACAction.OFF

    def test_hvac_action_idle_when_mode_on_but_state_false(self):
        entity, _ = self._make({"id": 1, "state": False, "mode": "heating"})
        assert entity.hvac_action == HVACAction.IDLE

    # lines 227, 246 — min/max temp in HEAT mode
    def test_min_temp_heat_mode_uses_heating_range(self):
        device = {
            "id": 1,
            "mode": "heating",
            "target_temperature_heating_minimum": 150,
            "target_temperature_heating_maximum": 280,
        }
        entity, _ = self._make(device)
        assert entity.min_temp == 15.0
        assert entity.max_temp == 28.0

    # lines 229-232, 248-251 — min/max temp in COOL mode
    def test_min_temp_cool_mode_uses_cooling_range(self):
        device = {
            "id": 1,
            "mode": "cooling",
            "target_temperature_cooling_minimum": 160,
            "target_temperature_cooling_maximum": 260,
        }
        entity, _ = self._make(device)
        assert entity.min_temp == 16.0
        assert entity.max_temp == 26.0

    # line 265 — extra_state_attributes dew_point
    def test_extra_attrs_includes_dew_point(self):
        device = {
            "id": 1,
            "dew_point": 100,
        }
        entity, _ = self._make(device)
        attrs = entity.extra_state_attributes
        assert "dew_point" in attrs
        assert attrs["dew_point"] == 10.0

    # line 280 — extra_state_attributes schedule_id
    def test_extra_attrs_includes_schedule_id(self):
        device = {"id": 1, "schedule_id": 42}
        entity, _ = self._make(device)
        attrs = entity.extra_state_attributes
        assert attrs["schedule_id"] == 42

    def test_extra_attrs_includes_floor_temperature(self):
        device = {"id": 1, "floor_temperature": 250}
        entity, _ = self._make(device)
        attrs = entity.extra_state_attributes
        assert "floor_temperature" in attrs
        assert attrs["floor_temperature"] == 25.0

    def test_extra_attrs_target_temp_mode_dict(self):
        device = {"id": 1, "target_temperature_mode": {"current": "constant", "remaining_time": 0}}
        entity, _ = self._make(device)
        attrs = entity.extra_state_attributes
        assert attrs["target_temperature_mode"] == "constant"

    def test_extra_attrs_target_temp_mode_string(self):
        device = {"id": 1, "target_temperature_mode": "schedule"}
        entity, _ = self._make(device)
        attrs = entity.extra_state_attributes
        assert attrs["target_temperature_mode"] == "schedule"

    def test_extra_attrs_is_window_open(self):
        device = {"id": 1, "is_window_open": True}
        entity, _ = self._make(device)
        attrs = entity.extra_state_attributes
        assert attrs["is_window_open"] is True

    def test_extra_attrs_target_temperature_heating_cooling(self):
        device = {
            "id": 1,
            "target_temperature_heating": 220,
            "target_temperature_cooling": 260,
        }
        entity, _ = self._make(device)
        attrs = entity.extra_state_attributes
        assert attrs["target_temperature_heating"] == 22.0
        assert attrs["target_temperature_cooling"] == 26.0

    def test_min_temp_heat_mode_missing_range_falls_through(self):
        """In HEAT mode but no heating-specific range → use generic min."""
        device = {
            "id": 1,
            "mode": "heating",
            "target_temperature_minimum": 50,
            "target_temperature_maximum": 300,
        }
        entity, _ = self._make(device)
        assert entity.min_temp == 5.0
        assert entity.max_temp == 30.0


# ---------------------------------------------------------------------------
# 4. SinumFanCoilClimate — uncovered branches
# ---------------------------------------------------------------------------

class TestSinumFanCoilClimateExtended:
    def _make_sbus(self, device: dict):
        c = _make_coordinator(sbus={5: device})
        entity = _wire(SinumFanCoilClimate(c, 5, "e", "sbus"))
        return entity, c

    def _make_wtp(self, device: dict):
        c = _make_coordinator(wtp={22: device})
        entity = _wire(SinumFanCoilClimate(c, 22, "e", "wtp"))
        return entity, c

    # line 368 — current_temperature None
    def test_current_temperature_none_when_no_room_temperature(self):
        entity, _ = self._make_sbus({"id": 5, "work_mode": "heating", "target_temperature": 220})
        assert entity.current_temperature is None

    def test_current_temperature_decoded(self):
        entity, _ = self._make_sbus(
            {"id": 5, "work_mode": "heating", "target_temperature": 220, "room_temperature": 195}
        )
        assert entity.current_temperature == 19.5

    # line 388 — min_temp returns raw_min / 10 (when set)
    def test_min_temp_from_device(self):
        entity, _ = self._make_sbus(
            {"id": 5, "work_mode": "off", "target_temperature": 220, "target_temperature_minimum": 100}
        )
        assert entity.min_temp == 10.0

    # line 396 — max_temp falls back to TEMP_MAX when not set
    def test_max_temp_fallback(self):
        entity, _ = self._make_sbus({"id": 5, "work_mode": "off", "target_temperature": 220})
        assert entity.max_temp == TEMP_MAX

    def test_max_temp_from_device(self):
        entity, _ = self._make_sbus(
            {"id": 5, "work_mode": "off", "target_temperature": 220, "target_temperature_maximum": 300}
        )
        assert entity.max_temp == 30.0

    # line 413 — hvac_action COOLING via state string fallback
    def test_hvac_action_cooling_via_state_string(self):
        entity, _ = self._make_sbus(
            {"id": 5, "work_mode": "cooling", "target_temperature": 220, "state": "cooling_demand"}
        )
        assert entity.hvac_action == HVACAction.COOLING

    # line 416 — hvac_action IDLE
    def test_hvac_action_idle_when_on_but_no_active_state(self):
        entity, _ = self._make_sbus(
            {"id": 5, "work_mode": "heating", "target_temperature": 220, "state": ""}
        )
        assert entity.hvac_action == HVACAction.IDLE

    def test_hvac_action_off_when_mode_off(self):
        entity, _ = self._make_sbus(
            {"id": 5, "work_mode": "off", "target_temperature": 220}
        )
        assert entity.hvac_action == HVACAction.OFF

    def test_hvac_action_heating_via_working_state(self):
        entity, _ = self._make_sbus(
            {"id": 5, "work_mode": "heating", "target_temperature": 220, "working_state": "heating_active"}
        )
        assert entity.hvac_action == HVACAction.HEATING

    def test_hvac_action_heating_via_state_string(self):
        entity, _ = self._make_sbus(
            {"id": 5, "work_mode": "heating", "target_temperature": 220, "state": "heating_demand"}
        )
        assert entity.hvac_action == HVACAction.HEATING

    def test_hvac_modes(self):
        entity, _ = self._make_sbus(
            {"id": 5, "work_mode": "heating", "target_temperature": 220,
             "available_work_modes": ["heating", "cooling", "off"]}
        )
        modes = entity.hvac_modes
        assert HVACMode.HEAT in modes
        assert HVACMode.COOL in modes

    def test_hvac_mode_off(self):
        entity, _ = self._make_sbus({"id": 5, "work_mode": "off", "target_temperature": 220})
        assert entity.hvac_mode == HVACMode.OFF

    def test_hvac_mode_heat(self):
        entity, _ = self._make_sbus({"id": 5, "work_mode": "heating", "target_temperature": 220})
        assert entity.hvac_mode == HVACMode.HEAT

    def test_fan_mode_from_relay(self):
        entity, _ = self._make_sbus(
            {
                "id": 5,
                "work_mode": "heating",
                "target_temperature": 220,
                "fan": {"relay_fan": {"current_gear": "second"}},
            }
        )
        assert entity.fan_mode == "2"

    def test_fan_mode_none_when_no_fan(self):
        entity, _ = self._make_sbus({"id": 5, "work_mode": "heating", "target_temperature": 220})
        assert entity.fan_mode is None

    # line 431 — extra_state_attributes schedule_id
    def test_extra_attrs_schedule_id(self):
        entity, _ = self._make_sbus(
            {"id": 5, "work_mode": "heating", "target_temperature": 220, "schedule_id": 7}
        )
        attrs = entity.extra_state_attributes
        assert attrs["schedule_id"] == 7

    def test_extra_attrs_fan_operation_mode(self):
        entity, _ = self._make_sbus(
            {"id": 5, "work_mode": "heating", "target_temperature": 220, "fan_operation_mode": "automatic"}
        )
        attrs = entity.extra_state_attributes
        assert attrs["fan_operation_mode"] == "automatic"

    def test_extra_attrs_working_state(self):
        entity, _ = self._make_sbus(
            {"id": 5, "work_mode": "heating", "target_temperature": 220, "working_state": "heating_active"}
        )
        attrs = entity.extra_state_attributes
        assert attrs["working_state"] == "heating_active"

    def test_extra_attrs_manual_fan_gear(self):
        entity, _ = self._make_sbus(
            {
                "id": 5,
                "work_mode": "heating",
                "target_temperature": 220,
                "fan": {"manual_fan_gear": "third"},
            }
        )
        attrs = entity.extra_state_attributes
        assert attrs["manual_fan_gear"] == "third"

    # lines 453-454 — set_temperature exception → HomeAssistantError
    @pytest.mark.asyncio
    async def test_set_temperature_raises_ha_error(self):
        entity, c = self._make_sbus(
            {"id": 5, "work_mode": "heating", "target_temperature": 220}
        )
        c.client.patch_sbus_device = AsyncMock(side_effect=SinumConnectionError("err"))
        with pytest.raises(HomeAssistantError, match="Cannot set temperature"):
            await entity.async_set_temperature(temperature=22.0)

    @pytest.mark.asyncio
    async def test_set_temperature_sends_correct_payload(self):
        device = {"id": 5, "work_mode": "heating", "target_temperature": 220}
        entity, c = self._make_sbus(device)
        c.client.patch_sbus_device = AsyncMock(return_value={})
        await entity.async_set_temperature(temperature=22.0)
        c.client.patch_sbus_device.assert_awaited_once()
        payload = c.client.patch_sbus_device.await_args.args[1]
        assert payload["target_temperature"] == 220

    @pytest.mark.asyncio
    async def test_set_temperature_no_op_when_missing(self):
        entity, c = self._make_sbus({"id": 5, "work_mode": "heating", "target_temperature": 220})
        await entity.async_set_temperature()  # no temperature kwarg
        c.client.patch_sbus_device.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_set_hvac_mode_sends_work_mode(self):
        entity, c = self._make_sbus({"id": 5, "work_mode": "off", "target_temperature": 220})
        c.client.patch_sbus_device = AsyncMock(return_value={})
        await entity.async_set_hvac_mode(HVACMode.HEAT)
        payload = c.client.patch_sbus_device.await_args.args[1]
        assert payload["work_mode"] == "heating"

    @pytest.mark.asyncio
    async def test_set_fan_mode_sends_gear(self):
        entity, c = self._make_sbus({"id": 5, "work_mode": "heating", "target_temperature": 220})
        c.client.patch_sbus_device = AsyncMock(return_value={})
        await entity.async_set_fan_mode("2")
        payload = c.client.patch_sbus_device.await_args.args[1]
        assert payload["fan.manual_fan_gear"] == "second"

    @pytest.mark.asyncio
    async def test_set_fan_mode_unknown_logs_warning(self, caplog):
        import logging
        entity, c = self._make_sbus({"id": 5, "work_mode": "heating", "target_temperature": 220})
        with caplog.at_level(logging.WARNING):
            await entity.async_set_fan_mode("9")
        c.client.patch_sbus_device.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_wtp_set_temperature_uses_wtp_patch(self):
        device = {
            "id": 22,
            "type": WTYPE_FAN_COIL,
            "work_mode": "heating",
            "target_temperature": 220,
        }
        entity, c = self._make_wtp(device)
        c.client.patch_wtp_device = AsyncMock(return_value={})
        await entity.async_set_temperature(temperature=21.0)
        c.client.patch_wtp_device.assert_awaited_once()


# ---------------------------------------------------------------------------
# 5. SinumTemperatureRegulatorClimate (SBUS bus)
# ---------------------------------------------------------------------------

class TestSinumTemperatureRegulatorSbus:
    def _make_sbus(self, device: dict):
        c = _make_coordinator(sbus={6: device})
        entity = _wire(SinumTemperatureRegulatorClimate(c, 6, "e", "sbus"))
        return entity, c

    # line 532 — current_temperature returns raw / 10 when set
    def test_current_temperature_decoded(self):
        entity, _ = self._make_sbus({"id": 6, "temperature": 215, "system_mode": "heating"})
        assert entity.current_temperature == 21.5

    def test_current_temperature_none_when_missing(self):
        entity, _ = self._make_sbus({"id": 6, "system_mode": "heating"})
        assert entity.current_temperature is None

    # line 536 — hvac_modes property
    def test_hvac_modes_includes_heat(self):
        entity, _ = self._make_sbus(
            {"id": 6, "system_mode": "heating", "available_work_modes": ["heating", "off"]}
        )
        modes = entity.hvac_modes
        assert HVACMode.HEAT in modes

    # line 542 — target_temperature None when raw is None
    def test_target_temperature_none_when_missing(self):
        entity, _ = self._make_sbus({"id": 6, "system_mode": "heating"})
        assert entity.target_temperature is None

    def test_target_temperature_decoded(self):
        entity, _ = self._make_sbus({"id": 6, "system_mode": "heating", "target_temperature": 220})
        assert entity.target_temperature == 22.0

    # lines 567-574 — hvac_action branches
    def test_hvac_action_heating_via_state_string(self):
        entity, _ = self._make_sbus(
            {"id": 6, "system_mode": "heating", "state": "heating_demand"}
        )
        assert entity.hvac_action == HVACAction.HEATING

    def test_hvac_action_cooling_via_state_string(self):
        entity, _ = self._make_sbus(
            {"id": 6, "system_mode": "cooling", "state": "cooling_demand"}
        )
        assert entity.hvac_action == HVACAction.COOLING

    def test_hvac_action_off_when_system_mode_off(self):
        entity, _ = self._make_sbus({"id": 6, "system_mode": "off", "state": ""})
        assert entity.hvac_action == HVACAction.OFF

    def test_hvac_action_idle(self):
        entity, _ = self._make_sbus({"id": 6, "system_mode": "heating", "state": ""})
        assert entity.hvac_action == HVACAction.IDLE

    # line 594 — set_temperature no-op when temperature missing
    @pytest.mark.asyncio
    async def test_set_temperature_noop_when_missing(self):
        entity, c = self._make_sbus({"id": 6, "system_mode": "heating"})
        await entity.async_set_temperature()
        c.client.patch_sbus_device.assert_not_awaited()

    # line 619 — _patch uses SBUS when bus=="sbus"
    @pytest.mark.asyncio
    async def test_set_hvac_mode_uses_sbus_patch(self):
        device = {
            "id": 6,
            "system_mode": "off",
            "mode_mutable": True,
            "target_temperature": 220,
            "target_temperature_minimum": 50,
            "target_temperature_maximum": 300,
        }
        entity, c = self._make_sbus(device)
        c.client.patch_sbus_device = AsyncMock(return_value={})
        await entity.async_set_hvac_mode(HVACMode.HEAT)
        c.client.patch_sbus_device.assert_awaited_once()
        payload = c.client.patch_sbus_device.await_args.args[1]
        assert payload["system_mode"] == "heating"
        c.client.patch_wtp_device.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_set_temperature_uses_sbus_patch(self):
        device = {
            "id": 6,
            "system_mode": "heating",
            "target_temperature": 220,
            "target_temperature_minimum": 50,
            "target_temperature_maximum": 300,
        }
        entity, c = self._make_sbus(device)
        c.client.patch_sbus_device = AsyncMock(return_value={})
        await entity.async_set_temperature(temperature=22.0)
        c.client.patch_sbus_device.assert_awaited_once()
        c.client.patch_wtp_device.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_set_temperature_raises_ha_error(self):
        device = {"id": 6, "system_mode": "heating", "target_temperature": 220}
        entity, c = self._make_sbus(device)
        c.client.patch_sbus_device = AsyncMock(side_effect=SinumConnectionError("err"))
        with pytest.raises(HomeAssistantError, match="Cannot set temperature"):
            await entity.async_set_temperature(temperature=22.0)

    def test_min_temp_from_device(self):
        entity, _ = self._make_sbus(
            {"id": 6, "system_mode": "heating", "target_temperature_minimum": 100}
        )
        assert entity.min_temp == 10.0

    def test_max_temp_from_device(self):
        entity, _ = self._make_sbus(
            {"id": 6, "system_mode": "heating", "target_temperature_maximum": 300}
        )
        assert entity.max_temp == 30.0

    def test_min_temp_fallback(self):
        entity, _ = self._make_sbus({"id": 6, "system_mode": "heating"})
        assert entity.min_temp == TEMP_MIN

    def test_max_temp_fallback(self):
        entity, _ = self._make_sbus({"id": 6, "system_mode": "heating"})
        assert entity.max_temp == TEMP_MAX

    def test_hvac_mode_off(self):
        entity, _ = self._make_sbus({"id": 6, "system_mode": "off"})
        assert entity.hvac_mode == HVACMode.OFF

    def test_hvac_mode_heat(self):
        entity, _ = self._make_sbus({"id": 6, "system_mode": "heating"})
        assert entity.hvac_mode == HVACMode.HEAT

    def test_extra_attrs_mode_mutable(self):
        entity, _ = self._make_sbus({"id": 6, "system_mode": "heating", "mode_mutable": True})
        attrs = entity.extra_state_attributes
        assert attrs["mode_mutable"] is True

    def test_extra_attrs_parent_id(self):
        entity, _ = self._make_sbus({"id": 6, "system_mode": "heating", "parent_id": 10})
        attrs = entity.extra_state_attributes
        assert attrs["parent_id"] == 10

    @pytest.mark.asyncio
    async def test_turn_on_patches_heating(self):
        device = {"id": 6, "system_mode": "off", "mode_mutable": True}
        entity, c = self._make_sbus(device)
        c.client.patch_sbus_device = AsyncMock(return_value={"system_mode": "heating"})
        await entity.async_turn_on()
        c.client.patch_sbus_device.assert_awaited_once_with(6, {"system_mode": "heating"})
        assert c.sbus_devices[6]["system_mode"] == "heating"

    @pytest.mark.asyncio
    async def test_turn_off_patches_off(self):
        device = {"id": 6, "system_mode": "heating", "mode_mutable": True}
        entity, c = self._make_sbus(device)
        c.client.patch_sbus_device = AsyncMock(return_value={"system_mode": "off"})
        await entity.async_turn_off()
        c.client.patch_sbus_device.assert_awaited_once_with(6, {"system_mode": "off"})
        assert c.sbus_devices[6]["system_mode"] == "off"

    @pytest.mark.asyncio
    async def test_turn_on_no_update_when_empty(self):
        device = {"id": 6, "system_mode": "off"}
        entity, c = self._make_sbus(device)
        c.client.patch_sbus_device = AsyncMock(return_value={})
        await entity.async_turn_on()
        entity.async_write_ha_state.assert_called()
        assert c.sbus_devices[6]["system_mode"] == "off"


# ---------------------------------------------------------------------------
# 6. SinumHeatPumpManagerClimate
# ---------------------------------------------------------------------------

class TestSinumHeatPumpManagerClimate:
    def _make(self, device: dict):
        c = _make_coordinator(virtual={1: device})
        entity = _wire(SinumHeatPumpManagerClimate(c, 1, "e"))
        return entity, c

    # line 664 — current_temperature None when no temperature
    def test_current_temperature_none_when_missing(self):
        entity, _ = self._make({"id": 1, "type": VTYPE_HEAT_PUMP_MANAGER, "enabled": True})
        assert entity.current_temperature is None

    def test_current_temperature_decoded(self):
        entity, _ = self._make(
            {"id": 1, "type": VTYPE_HEAT_PUMP_MANAGER, "enabled": True, "temperature": 200}
        )
        assert entity.current_temperature == 20.0

    # line 671 — target_temperature None when tt is None
    def test_target_temperature_none_when_missing(self):
        entity, _ = self._make({"id": 1, "type": VTYPE_HEAT_PUMP_MANAGER, "enabled": True})
        assert entity.target_temperature is None

    # line 674 — target_temperature None when tt is dict without "current"
    def test_target_temperature_none_when_dict_no_current(self):
        entity, _ = self._make(
            {
                "id": 1,
                "type": VTYPE_HEAT_PUMP_MANAGER,
                "enabled": True,
                "target_temperature": {"heating": 200},  # no "current" key
            }
        )
        assert entity.target_temperature is None

    def test_target_temperature_from_dict_current(self):
        entity, _ = self._make(
            {
                "id": 1,
                "type": VTYPE_HEAT_PUMP_MANAGER,
                "enabled": True,
                "target_temperature": {"current": 220, "heating": 200},
            }
        )
        assert entity.target_temperature == 22.0

    def test_target_temperature_from_scalar(self):
        entity, _ = self._make(
            {"id": 1, "type": VTYPE_HEAT_PUMP_MANAGER, "enabled": True, "target_temperature": 220}
        )
        assert entity.target_temperature == 22.0

    # hvac_mode: enabled=False → OFF
    def test_hvac_mode_off_when_disabled(self):
        entity, _ = self._make(
            {"id": 1, "type": VTYPE_HEAT_PUMP_MANAGER, "enabled": False, "work_mode": "heating"}
        )
        assert entity.hvac_mode == HVACMode.OFF

    # hvac_mode: enabled=True, work_mode=heating → HEAT
    def test_hvac_mode_heat_when_enabled(self):
        entity, _ = self._make(
            {"id": 1, "type": VTYPE_HEAT_PUMP_MANAGER, "enabled": True, "work_mode": "heating"}
        )
        assert entity.hvac_mode == HVACMode.HEAT

    # hvac_mode: enabled=True, work_mode=cooling → COOL
    def test_hvac_mode_cool_when_enabled_cooling(self):
        entity, _ = self._make(
            {"id": 1, "type": VTYPE_HEAT_PUMP_MANAGER, "enabled": True, "work_mode": "cooling"}
        )
        assert entity.hvac_mode == HVACMode.COOL

    # hvac_action: mode=OFF → OFF
    def test_hvac_action_off_when_disabled(self):
        entity, _ = self._make(
            {"id": 1, "type": VTYPE_HEAT_PUMP_MANAGER, "enabled": False}
        )
        assert entity.hvac_action == HVACAction.OFF

    # line 691 — hvac_action cooling branch (state=True, work_mode=cooling)
    def test_hvac_action_cooling_when_cooling_and_active(self):
        entity, _ = self._make(
            {
                "id": 1,
                "type": VTYPE_HEAT_PUMP_MANAGER,
                "enabled": True,
                "work_mode": "cooling",
                "state": True,
            }
        )
        assert entity.hvac_action == HVACAction.COOLING

    def test_hvac_action_heating_when_heating_and_active(self):
        entity, _ = self._make(
            {
                "id": 1,
                "type": VTYPE_HEAT_PUMP_MANAGER,
                "enabled": True,
                "work_mode": "heating",
                "state": True,
            }
        )
        assert entity.hvac_action == HVACAction.HEATING

    def test_hvac_action_idle_when_not_active(self):
        entity, _ = self._make(
            {
                "id": 1,
                "type": VTYPE_HEAT_PUMP_MANAGER,
                "enabled": True,
                "work_mode": "heating",
                "state": False,
            }
        )
        assert entity.hvac_action == HVACAction.IDLE

    # line 718 — set_temperature no-op when no temperature kwarg
    @pytest.mark.asyncio
    async def test_set_temperature_noop_when_missing(self):
        entity, c = self._make(
            {"id": 1, "type": VTYPE_HEAT_PUMP_MANAGER, "enabled": True, "work_mode": "heating"}
        )
        await entity.async_set_temperature()
        c.client.patch_virtual_device.assert_not_awaited()

    # line 726 — set_temperature simple payload when tt is not a dict
    @pytest.mark.asyncio
    async def test_set_temperature_simple_payload(self):
        device = {
            "id": 1,
            "type": VTYPE_HEAT_PUMP_MANAGER,
            "enabled": True,
            "work_mode": "heating",
            "target_temperature": 220,
        }
        entity, c = self._make(device)
        c.client.patch_virtual_device = AsyncMock(return_value={})
        await entity.async_set_temperature(temperature=22.0)
        payload = c.client.patch_virtual_device.await_args.args[1]
        assert payload == {"target_temperature": 220}

    def test_set_temperature_dict_payload_when_tt_is_dict(self):
        """When target_temperature is a dict, payload wraps value in {"current": raw}."""
        device = {
            "id": 1,
            "type": VTYPE_HEAT_PUMP_MANAGER,
            "enabled": True,
            "work_mode": "heating",
            "target_temperature": {"current": 220, "heating": 200},
        }
        import asyncio

        entity, c = self._make(device)
        c.client.patch_virtual_device = AsyncMock(return_value={})
        asyncio.get_event_loop().run_until_complete(entity.async_set_temperature(temperature=22.0))
        payload = c.client.patch_virtual_device.call_args.args[1]
        assert payload == {"target_temperature": {"current": 220}}

    # lines 729-730 — set_temperature raises HomeAssistantError
    @pytest.mark.asyncio
    async def test_set_temperature_raises_ha_error(self):
        device = {
            "id": 1,
            "type": VTYPE_HEAT_PUMP_MANAGER,
            "enabled": True,
            "work_mode": "heating",
            "target_temperature": 220,
        }
        entity, c = self._make(device)
        c.client.patch_virtual_device = AsyncMock(side_effect=SinumConnectionError("err"))
        with pytest.raises(HomeAssistantError, match="Cannot set temperature"):
            await entity.async_set_temperature(temperature=22.0)

    # line 732 — set_temperature updates virtual_devices when updated is truthy
    @pytest.mark.asyncio
    async def test_set_temperature_updates_coordinator(self):
        device = {
            "id": 1,
            "type": VTYPE_HEAT_PUMP_MANAGER,
            "enabled": True,
            "work_mode": "heating",
            "target_temperature": 220,
        }
        entity, c = self._make(device)
        updated = {"target_temperature": 230}
        c.client.patch_virtual_device = AsyncMock(return_value=updated)
        await entity.async_set_temperature(temperature=23.0)
        # real dict.update() was called; verify the coordinator data was merged
        assert c.virtual_devices[1]["target_temperature"] == 230

    # async_set_hvac_mode
    @pytest.mark.asyncio
    async def test_set_hvac_mode_off_sends_enabled_false(self):
        device = {
            "id": 1,
            "type": VTYPE_HEAT_PUMP_MANAGER,
            "enabled": True,
            "work_mode": "heating",
        }
        entity, c = self._make(device)
        c.client.patch_virtual_device = AsyncMock(return_value={})
        await entity.async_set_hvac_mode(HVACMode.OFF)
        payload = c.client.patch_virtual_device.await_args.args[1]
        assert payload == {"enabled": False}

    @pytest.mark.asyncio
    async def test_set_hvac_mode_heat_sends_enabled_and_mode(self):
        device = {
            "id": 1,
            "type": VTYPE_HEAT_PUMP_MANAGER,
            "enabled": False,
            "work_mode": "off",
        }
        entity, c = self._make(device)
        c.client.patch_virtual_device = AsyncMock(return_value={})
        await entity.async_set_hvac_mode(HVACMode.HEAT)
        payload = c.client.patch_virtual_device.await_args.args[1]
        assert payload == {"enabled": True, "work_mode": "heating"}

    # line 746 — set_hvac_mode updates coordinator dict
    @pytest.mark.asyncio
    async def test_set_hvac_mode_updates_coordinator(self):
        device = {
            "id": 1,
            "type": VTYPE_HEAT_PUMP_MANAGER,
            "enabled": True,
            "work_mode": "heating",
        }
        entity, c = self._make(device)
        updated = {"enabled": False}
        c.client.patch_virtual_device = AsyncMock(return_value=updated)
        await entity.async_set_hvac_mode(HVACMode.OFF)
        # real dict.update() was called; verify the coordinator data was merged
        assert c.virtual_devices[1]["enabled"] is False

    # line 754 — async_turn_on updates coordinator
    @pytest.mark.asyncio
    async def test_turn_on_updates_coordinator(self):
        device = {
            "id": 1,
            "type": VTYPE_HEAT_PUMP_MANAGER,
            "enabled": False,
            "work_mode": "heating",
        }
        entity, c = self._make(device)
        updated = {"enabled": True}
        c.client.patch_virtual_device = AsyncMock(return_value=updated)
        await entity.async_turn_on()
        payload = c.client.patch_virtual_device.await_args.args[1]
        assert payload == {"enabled": True}
        # real dict.update() was called; verify coordinator data was merged
        assert c.virtual_devices[1]["enabled"] is True

    # line 762 — async_turn_off updates coordinator
    @pytest.mark.asyncio
    async def test_turn_off_updates_coordinator(self):
        device = {
            "id": 1,
            "type": VTYPE_HEAT_PUMP_MANAGER,
            "enabled": True,
            "work_mode": "heating",
        }
        entity, c = self._make(device)
        updated = {"enabled": False}
        c.client.patch_virtual_device = AsyncMock(return_value=updated)
        await entity.async_turn_off()
        payload = c.client.patch_virtual_device.await_args.args[1]
        assert payload == {"enabled": False}
        # real dict.update() was called; verify coordinator data was merged
        assert c.virtual_devices[1]["enabled"] is False

    # async_turn_on without update (empty dict)
    @pytest.mark.asyncio
    async def test_turn_on_no_update_when_empty(self):
        device = {
            "id": 1,
            "type": VTYPE_HEAT_PUMP_MANAGER,
            "enabled": False,
        }
        entity, c = self._make(device)
        c.client.patch_virtual_device = AsyncMock(return_value={})
        await entity.async_turn_on()  # empty dict → if-branch skipped
        # state is unchanged (enabled is still False in our dict)
        assert c.virtual_devices[1]["enabled"] is False
        entity.async_write_ha_state.assert_called()

    # extra_state_attributes
    def test_extra_attrs_target_temperature_heating_cooling(self):
        device = {
            "id": 1,
            "type": VTYPE_HEAT_PUMP_MANAGER,
            "enabled": True,
            "target_temperature": {
                "current": 220,
                "heating": 200,
                "cooling": 260,
                "automatic": 220,
            },
        }
        entity, _ = self._make(device)
        attrs = entity.extra_state_attributes
        assert "target_temperature_heating" in attrs
        assert "target_temperature_cooling" in attrs
        assert "target_temperature_automatic" in attrs

    def test_extra_attrs_dhw_control(self):
        device = {
            "id": 1,
            "type": VTYPE_HEAT_PUMP_MANAGER,
            "enabled": True,
            "dhw_control": {"target_temperature": 550, "state": True},
        }
        entity, _ = self._make(device)
        attrs = entity.extra_state_attributes
        assert "dhw_target_temperature" in attrs
        assert attrs["dhw_state"] is True

    def test_hvac_modes_include_all(self):
        entity, _ = self._make(
            {"id": 1, "type": VTYPE_HEAT_PUMP_MANAGER, "enabled": True, "work_mode": "heating"}
        )
        modes = entity._attr_hvac_modes
        assert HVACMode.OFF in modes
        assert HVACMode.HEAT in modes
        assert HVACMode.COOL in modes
