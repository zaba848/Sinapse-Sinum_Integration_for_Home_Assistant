"""Extended tests for number entities (improves 56% → 80%+ coverage)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sinum.number import (
    SinumAnalogOutputNumber,
    SinumPwmNumber,
    SinumVariableNumber,
)


def _make_coordinator(sbus_devices=None):
    coord = MagicMock()
    coord.sbus_devices = sbus_devices or {}
    return coord


def _make_variable(var_id=1, name="Setpoint", value=50, min_val=0, max_val=100, var_type="integer"):
    return {"id": var_id, "name": name, "value": value, "min": min_val, "max": max_val, "type": var_type}


def _make_analog_device(device_id=40, value=500, v_min=0, v_max=10000, unit=""):
    return {
        "id": device_id,
        "type": "analog_output",
        "value": value,
        "value_minimum": v_min,
        "value_maximum": v_max,
        "unit": unit,
        "class": "sbus",
    }


class TestSinumVariableNumber:
    def _make_entity(self, variable=None):
        var = variable or _make_variable()
        coordinator = _make_coordinator()
        coordinator.client = MagicMock()
        entity = SinumVariableNumber(coordinator, var, "test_entry")
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        return entity, coordinator

    def test_native_value(self):
        entity, _ = self._make_entity(_make_variable(value=42))
        assert entity.native_value == 42.0

    def test_native_value_zero(self):
        entity, _ = self._make_entity(_make_variable(value=0))
        assert entity.native_value == 0.0

    def test_min_max(self):
        entity, _ = self._make_entity(_make_variable(min_val=-100, max_val=200))
        assert entity._attr_native_min_value == -100.0
        assert entity._attr_native_max_value == 200.0

    def test_step_integer(self):
        entity, _ = self._make_entity(_make_variable(var_type="integer"))
        assert entity._attr_native_step == 1.0

    def test_step_float(self):
        entity, _ = self._make_entity(_make_variable(var_type="float"))
        assert entity._attr_native_step == 0.01

    def test_unique_id(self):
        entity, _ = self._make_entity(_make_variable(var_id=7))
        assert entity.unique_id == "test_entry_variable_7"

    def test_icon(self):
        entity, _ = self._make_entity()
        assert entity._attr_icon == "mdi:variable"

    @pytest.mark.asyncio
    async def test_set_native_value(self):
        entity, coordinator = self._make_entity()
        coordinator.client.set_variable = AsyncMock(return_value={"id": 1, "value": 75})
        await entity.async_set_native_value(75.0)
        coordinator.client.set_variable.assert_awaited_once_with(1, 75.0)

    @pytest.mark.asyncio
    async def test_async_update_refreshes_value(self):
        entity, coordinator = self._make_entity(_make_variable(value=50))
        coordinator.client.get_variables = AsyncMock(
            return_value=[{"id": 1, "name": "Setpoint", "value": 99}]
        )
        await entity.async_update()
        assert entity._variable["value"] == 99

    @pytest.mark.asyncio
    async def test_async_update_connection_error_does_not_raise(self):
        """Lines 84-86: SinumConnectionError in async_update is caught gracefully."""
        from custom_components.sinum.api import SinumConnectionError as ConnErr

        entity, coordinator = self._make_entity(_make_variable(value=50))
        coordinator.client.get_variables = AsyncMock(side_effect=ConnErr("timeout"))
        # Should not raise; _variable remains unchanged
        await entity.async_update()
        assert entity._variable["value"] == 50


class TestSinumAnalogOutputNumber:
    def _make_entity(self, value=500, v_min=0, v_max=10000):
        device = _make_analog_device(value=value, v_min=v_min, v_max=v_max)
        coordinator = _make_coordinator(sbus_devices={40: device})
        coordinator.client = MagicMock()
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumAnalogOutputNumber(coordinator, 40, "test_entry")
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        return entity, coordinator

    def test_native_value(self):
        entity, _ = self._make_entity(value=750)
        assert entity.native_value == 750.0

    def test_native_value_zero(self):
        device = _make_analog_device(value=0)
        coord = _make_coordinator(sbus_devices={40: device})
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumAnalogOutputNumber(coord, 40, "test_entry")
        assert entity.native_value == 0.0

    def test_native_value_none_when_missing(self):
        device = {"id": 40, "type": "analog_output", "class": "sbus"}
        coord = _make_coordinator(sbus_devices={40: device})
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumAnalogOutputNumber(coord, 40, "test_entry")
        assert entity.native_value is None

    def test_min_max(self):
        entity, _ = self._make_entity(v_min=100, v_max=5000)
        assert entity._attr_native_min_value == 100.0
        assert entity._attr_native_max_value == 5000.0

    def test_unique_id(self):
        entity, _ = self._make_entity()
        assert entity.unique_id == "test_entry_sbus_40"

    @pytest.mark.asyncio
    async def test_set_native_value(self):
        entity, coordinator = self._make_entity()
        coordinator.client.patch_sbus_device = AsyncMock(return_value={})
        await entity.async_set_native_value(1234.0)
        coordinator.client.patch_sbus_device.assert_awaited_once_with(40, {"value": 1234})


class TestSinumPwmNumber:
    def _make_entity(self, duty_cycle=50):
        device = {
            "id": 10,
            "type": "pulse_width_modulation",
            "duty_cycle": duty_cycle,
            "name": "PWM Output",
        }
        coordinator = _make_coordinator(sbus_devices={10: device})
        coordinator.client = MagicMock()
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumPwmNumber(coordinator, 10, "test_entry")
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        return entity, coordinator

    def test_pwm_number_value(self):
        entity, _ = self._make_entity(duty_cycle=75)
        assert entity.native_value == 75.0

    def test_pwm_number_value_zero(self):
        entity, _ = self._make_entity(duty_cycle=0)
        assert entity.native_value == 0.0

    def test_pwm_number_value_none_when_missing(self):
        device = {"id": 10, "type": "pulse_width_modulation"}
        coord = _make_coordinator(sbus_devices={10: device})
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumPwmNumber(coord, 10, "test_entry")
        assert entity.native_value is None

    def test_pwm_unique_id(self):
        entity, _ = self._make_entity()
        assert entity.unique_id == "test_entry_sbus_10_pwm"

    def test_pwm_range(self):
        entity, _ = self._make_entity()
        assert entity._attr_native_min_value == 0.0
        assert entity._attr_native_max_value == 100.0

    def test_pwm_unit(self):
        entity, _ = self._make_entity()
        assert entity._attr_native_unit_of_measurement == "%"

    @pytest.mark.asyncio
    async def test_pwm_set_value(self):
        entity, coordinator = self._make_entity()
        coordinator.client.patch_sbus_device = AsyncMock(return_value={})
        await entity.async_set_native_value(80.0)
        coordinator.client.patch_sbus_device.assert_awaited_once_with(10, {"duty_cycle": 80})


class TestSinumVariableNumberSetup:
    """Tests that SinumVariableNumber is created for integer type in async_setup_entry."""

    @pytest.mark.asyncio
    async def test_variable_number_setup(self):
        from custom_components.sinum.number import async_setup_entry

        variable = {
            "id": 5,
            "name": "MyVar",
            "type": "integer",
            "value": 10,
            "min": 0,
            "max": 100,
        }
        coordinator = _make_coordinator()
        coordinator.client.get_variables = AsyncMock(return_value=[variable])
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "test_entry"

        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))

        assert any(isinstance(e, SinumVariableNumber) for e in added)
        var_entity = next(e for e in added if isinstance(e, SinumVariableNumber))
        assert var_entity._variable_id == 5

    @pytest.mark.asyncio
    async def test_setup_entry_variables_endpoint_unavailable(self):
        """Lines 28-30: SinumConnectionError from get_variables → no variable entities."""
        from custom_components.sinum.api import SinumConnectionError as ConnErr
        from custom_components.sinum.number import async_setup_entry

        coordinator = _make_coordinator()
        coordinator.client.get_variables = AsyncMock(side_effect=ConnErr("not found"))
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "test_entry"

        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))

        # No SinumVariableNumber should be created when the endpoint is unavailable
        assert not any(isinstance(e, SinumVariableNumber) for e in added)

    @pytest.mark.asyncio
    async def test_setup_entry_creates_analog_output(self):
        """Lines 38-39: sbus_devices with analog_output type → SinumAnalogOutputNumber."""
        from custom_components.sinum.number import async_setup_entry

        device = {"id": 40, "type": "analog_output", "value": 500,
                  "value_minimum": 0, "value_maximum": 10000}
        coordinator = _make_coordinator(sbus_devices={40: device})
        coordinator.client.get_variables = AsyncMock(return_value=[])
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "test_entry"

        added = []
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))

        assert any(isinstance(e, SinumAnalogOutputNumber) for e in added)

    @pytest.mark.asyncio
    async def test_setup_entry_creates_pwm(self):
        """Lines 40-41: sbus_devices with pulse_width_modulation type → SinumPwmNumber."""
        from custom_components.sinum.number import async_setup_entry

        device = {"id": 10, "type": "pulse_width_modulation", "duty_cycle": 50,
                  "name": "PWM Output"}
        coordinator = _make_coordinator(sbus_devices={10: device})
        coordinator.client.get_variables = AsyncMock(return_value=[])
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "test_entry"

        added = []
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))

        assert any(isinstance(e, SinumPwmNumber) for e in added)
