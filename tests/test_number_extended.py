"""Extended tests for number entities (improves 56% → 80%+ coverage)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sinum.number import SinumAnalogOutputNumber, SinumVariableNumber


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
