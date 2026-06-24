"""Tests for SinumThermostat climate entity."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "sinum_devices.json").read_text())


def _make_thermostat(device_data: dict[str, Any]):
    from custom_components.sinum.climate import SinumThermostat

    coordinator = MagicMock()
    coordinator.client.decode_temperature = lambda raw: raw / 10
    coordinator.client.encode_temperature = lambda c: round(c * 10)
    coordinator.client.patch_virtual_device = AsyncMock(return_value=device_data)
    coordinator.virtual_devices = {10: device_data}

    entity = SinumThermostat(coordinator, 10, "test_entry")
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    return entity, coordinator


class TestSinumThermostat:
    def test_current_temperature(self):
        device = dict(FIXTURES["virtual_thermostat"])
        entity, _ = _make_thermostat(device)
        assert entity.current_temperature == 21.5  # 215 / 10

    def test_target_temperature(self):
        device = dict(FIXTURES["virtual_thermostat"])
        entity, _ = _make_thermostat(device)
        assert entity.target_temperature == 22.0  # 220 / 10

    def test_hvac_mode_heat_when_on(self):
        from homeassistant.components.climate import HVACMode

        device = {**FIXTURES["virtual_thermostat"], "mode": "heating", "state": True}
        entity, _ = _make_thermostat(device)
        assert entity.hvac_mode == HVACMode.HEAT

    def test_hvac_mode_off_when_false(self):
        from homeassistant.components.climate import HVACMode

        device = {**FIXTURES["virtual_thermostat"], "mode": "off", "state": False}
        entity, _ = _make_thermostat(device)
        assert entity.hvac_mode == HVACMode.OFF

    @pytest.mark.asyncio
    async def test_set_temperature_encodes_correctly(self):
        device = dict(FIXTURES["virtual_thermostat"])
        entity, coordinator = _make_thermostat(device)
        updated = {**device, "target_temperature": 230}
        coordinator.client.patch_virtual_device = AsyncMock(return_value=updated)

        await entity.async_set_temperature(temperature=23.0)

        coordinator.client.patch_virtual_device.assert_called_once_with(
            10, {"target_temperature": 230}
        )

    @pytest.mark.asyncio
    async def test_set_hvac_mode_off_sends_mode(self):
        from homeassistant.components.climate import HVACMode

        device = dict(FIXTURES["virtual_thermostat"])
        entity, coordinator = _make_thermostat(device)
        updated = {**device, "mode": "off", "state": False}
        coordinator.client.patch_virtual_device = AsyncMock(return_value=updated)

        await entity.async_set_hvac_mode(HVACMode.OFF)

        coordinator.client.patch_virtual_device.assert_called_once_with(10, {"mode": "off"})

    @pytest.mark.asyncio
    async def test_set_hvac_mode_heat_sends_mode(self):
        from homeassistant.components.climate import HVACMode

        device = {**FIXTURES["virtual_thermostat"], "mode": "off", "state": False}
        entity, coordinator = _make_thermostat(device)
        updated = {**device, "mode": "heating", "state": True}
        coordinator.client.patch_virtual_device = AsyncMock(return_value=updated)

        await entity.async_set_hvac_mode(HVACMode.HEAT)

        coordinator.client.patch_virtual_device.assert_called_once_with(10, {"mode": "heating"})

    def test_unique_id_contains_device_and_entry(self):
        device = dict(FIXTURES["virtual_thermostat"])
        entity, _ = _make_thermostat(device)
        assert "10" in entity.unique_id
        assert "test_entry" in entity.unique_id

    def test_temperature_range(self):
        device = dict(FIXTURES["virtual_thermostat"])
        entity, _ = _make_thermostat(device)
        assert entity.min_temp == 5.0
        assert entity.max_temp == 35.0
        assert entity.target_temperature_step == 0.5

    def test_set_temperature_noop_when_no_value(self):
        device = dict(FIXTURES["virtual_thermostat"])
        entity, coordinator = _make_thermostat(device)
        # calling without temperature kwarg should not call API
        import asyncio

        asyncio.get_event_loop().run_until_complete(entity.async_set_temperature())
        coordinator.client.patch_virtual_device.assert_not_called()


class TestPhase7B2TemperatureRegulator:
    """Phase 7B.2: Optional temperature regulator climate entities (experimental)."""

    def _make_regulator(self, device_data: dict[str, Any]):
        from custom_components.sinum.climate import SinumTemperatureRegulatorClimate

        coordinator = MagicMock()
        coordinator.client.patch_wtp_device = AsyncMock(return_value=device_data)
        coordinator.wtp_devices = {100: device_data}
        coordinator.virtual_devices = {}
        coordinator.sbus_devices = {}

        entity = SinumTemperatureRegulatorClimate(coordinator, 100, "test_entry")
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        return entity, coordinator

    def test_regulator_reads_temperature(self):
        """Real regulators have no temperature field — current_temperature is None."""
        device = dict(FIXTURES["wtp_temperature_regulator_full"])
        entity, _ = self._make_regulator(device)
        assert entity.current_temperature is None

    def test_regulator_reads_target_temperature(self):
        device = dict(FIXTURES["wtp_temperature_regulator_full"])
        entity, _ = self._make_regulator(device)
        assert entity.target_temperature == 22.0

    def test_regulator_shows_hvac_mode(self):
        from homeassistant.components.climate import HVACMode

        device = dict(FIXTURES["wtp_temperature_regulator_full"])
        entity, _ = self._make_regulator(device)
        assert entity.hvac_mode == HVACMode.HEAT

    async def test_regulator_mutable_allows_mode_set(self):
        from homeassistant.components.climate import HVACMode

        device = dict(FIXTURES["wtp_temperature_regulator_full"])
        entity, coordinator = self._make_regulator(device)

        await entity.async_set_hvac_mode(HVACMode.COOL)

        coordinator.client.patch_wtp_device.assert_called_with(100, {"system_mode": "cooling"})

    async def test_regulator_immutable_blocks_mode_set(self):
        from homeassistant.components.climate import HVACMode

        device = dict(FIXTURES["wtp_temperature_regulator_immutable"])
        entity, coordinator = self._make_regulator(device)

        # Should not call API when mode_mutable=false
        await entity.async_set_hvac_mode(HVACMode.COOL)

        coordinator.client.patch_wtp_device.assert_not_called()

    def test_regulator_shows_supervision_attributes(self):
        device = dict(FIXTURES["wtp_temperature_regulator_full"])
        entity, _ = self._make_regulator(device)

        attrs = entity.extra_state_attributes
        assert attrs["mode_mutable"] is True
        assert attrs["parent_id"] == 10

    async def test_regulator_set_temperature(self):
        device = dict(FIXTURES["wtp_temperature_regulator_full"])
        entity, coordinator = self._make_regulator(device)

        await entity.async_set_temperature(temperature=23.0)

        coordinator.client.patch_wtp_device.assert_called_with(100, {"target_temperature": 230})
