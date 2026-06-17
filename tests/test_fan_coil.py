"""Tests for SinumFanCoilClimate entity."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.climate import HVACMode

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "sinum_devices.json").read_text()
)


def _make_fan_coil(
    device_data: dict[str, Any],
    *,
    source: str = "sbus",
    device_id: int = 13,
):
    from custom_components.sinum.climate import SinumFanCoilClimate

    coordinator = MagicMock()
    coordinator.client.patch_sbus_device = AsyncMock(return_value=device_data)
    coordinator.client.patch_wtp_device = AsyncMock(return_value=device_data)
    coordinator.sbus_devices = {device_id: device_data} if source == "sbus" else {}
    coordinator.wtp_devices = {device_id: device_data} if source == "wtp" else {}

    entity = SinumFanCoilClimate(coordinator, device_id, "test_entry", source)
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    return entity, coordinator


class TestSinumFanCoilClimate:
    def test_current_temperature(self):
        device = dict(FIXTURES["sbus_fan_coil"])
        entity, _ = _make_fan_coil(device)
        assert entity.current_temperature == 19.5  # 195 / 10

    def test_target_temperature(self):
        device = dict(FIXTURES["sbus_fan_coil"])
        entity, _ = _make_fan_coil(device)
        assert entity.target_temperature == 22.0  # 220 / 10

    def test_temperature_range_from_device(self):
        device = dict(FIXTURES["sbus_fan_coil"])
        entity, _ = _make_fan_coil(device)
        assert entity.min_temp == 5.0   # 50 / 10
        assert entity.max_temp == 30.0  # 300 / 10

    def test_hvac_mode_heating(self):
        from homeassistant.components.climate import HVACMode
        device = dict(FIXTURES["sbus_fan_coil"])
        entity, _ = _make_fan_coil(device)
        assert entity.hvac_mode == HVACMode.HEAT

    def test_hvac_mode_off(self):
        from homeassistant.components.climate import HVACMode
        device = {**FIXTURES["sbus_fan_coil"], "work_mode": "off"}
        entity, _ = _make_fan_coil(device)
        assert entity.hvac_mode == HVACMode.OFF

    def test_hvac_action_heating_active(self):
        from homeassistant.components.climate import HVACAction
        device = dict(FIXTURES["sbus_fan_coil"])
        entity, _ = _make_fan_coil(device)
        assert entity.hvac_action == HVACAction.HEATING

    def test_hvac_action_idle(self):
        from homeassistant.components.climate import HVACAction
        device = {**FIXTURES["sbus_fan_coil"], "working_state": "idle"}
        entity, _ = _make_fan_coil(device)
        assert entity.hvac_action == HVACAction.IDLE

    def test_fan_mode_second(self):
        device = dict(FIXTURES["sbus_fan_coil"])
        entity, _ = _make_fan_coil(device)
        assert entity.fan_mode == "2"

    def test_fan_modes_list(self):
        device = dict(FIXTURES["sbus_fan_coil"])
        entity, _ = _make_fan_coil(device)
        assert entity.fan_modes == ["1", "2", "3"]

    def test_available_hvac_modes(self):
        from homeassistant.components.climate import HVACMode
        device = dict(FIXTURES["sbus_fan_coil"])
        entity, _ = _make_fan_coil(device)
        assert HVACMode.HEAT in entity.hvac_modes
        assert HVACMode.COOL in entity.hvac_modes
        assert HVACMode.AUTO in entity.hvac_modes
        assert HVACMode.OFF in entity.hvac_modes

    def test_unique_id(self):
        device = dict(FIXTURES["sbus_fan_coil"])
        entity, _ = _make_fan_coil(device)
        assert "13" in entity.unique_id
        assert "test_entry" in entity.unique_id
        assert "sbus" in entity.unique_id

    @pytest.mark.asyncio
    async def test_set_temperature_sends_raw(self):
        device = dict(FIXTURES["sbus_fan_coil"])
        entity, coordinator = _make_fan_coil(device)
        updated = {**device, "target_temperature": 230}
        coordinator.client.patch_sbus_device = AsyncMock(return_value=updated)

        await entity.async_set_temperature(temperature=23.0)

        coordinator.client.patch_sbus_device.assert_called_once_with(
            13, {"target_temperature": 230}
        )

    @pytest.mark.asyncio
    async def test_set_hvac_mode_sends_work_mode(self):
        from homeassistant.components.climate import HVACMode
        device = dict(FIXTURES["sbus_fan_coil"])
        entity, coordinator = _make_fan_coil(device)
        updated = {**device, "work_mode": "cooling"}
        coordinator.client.patch_sbus_device = AsyncMock(return_value=updated)

        await entity.async_set_hvac_mode(HVACMode.COOL)

        coordinator.client.patch_sbus_device.assert_called_once_with(
            13, {"work_mode": "cooling"}
        )

    @pytest.mark.asyncio
    async def test_set_fan_mode_sends_gear(self):
        device = dict(FIXTURES["sbus_fan_coil"])
        entity, coordinator = _make_fan_coil(device)
        coordinator.client.patch_sbus_device = AsyncMock(return_value=device)

        await entity.async_set_fan_mode("3")

        coordinator.client.patch_sbus_device.assert_called_once_with(
            13, {"fan.manual_fan_gear": "third"}
        )

    @pytest.mark.asyncio
    async def test_set_temperature_noop_without_value(self):
        device = dict(FIXTURES["sbus_fan_coil"])
        entity, coordinator = _make_fan_coil(device)

        await entity.async_set_temperature()

        coordinator.client.patch_sbus_device.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_fan_mode_unknown_does_not_call_api(self):
        device = dict(FIXTURES["sbus_fan_coil"])
        entity, coordinator = _make_fan_coil(device)

        await entity.async_set_fan_mode("invalid")

        coordinator.client.patch_sbus_device.assert_not_called()

    def test_extra_state_attributes(self):
        device = dict(FIXTURES["sbus_fan_coil"])
        entity, _ = _make_fan_coil(device)
        attrs = entity.extra_state_attributes
        assert attrs.get("fan_operation_mode") == "automatic"
        assert attrs.get("mode_mutable") is True
        assert attrs.get("manual_fan_gear") == "second"

    @pytest.mark.asyncio
    async def test_wtp_set_temperature_uses_wtp_patch(self):
        device = dict(FIXTURES["wtp_fan_coil_full"])
        entity, coordinator = _make_fan_coil(device, source="wtp", device_id=22)
        updated = {**device, "target_temperature": 225}
        coordinator.client.patch_wtp_device = AsyncMock(return_value=updated)

        await entity.async_set_temperature(temperature=22.5)

        coordinator.client.patch_wtp_device.assert_called_once_with(
            22, {"target_temperature": 225}
        )
        coordinator.client.patch_sbus_device.assert_not_called()

    @pytest.mark.asyncio
    async def test_wtp_set_hvac_mode_uses_wtp_patch(self):
        from homeassistant.components.climate import HVACMode

        device = dict(FIXTURES["wtp_fan_coil_full"])
        entity, coordinator = _make_fan_coil(device, source="wtp", device_id=22)
        updated = {**device, "work_mode": "cooling"}
        coordinator.client.patch_wtp_device = AsyncMock(return_value=updated)

        await entity.async_set_hvac_mode(HVACMode.COOL)

        coordinator.client.patch_wtp_device.assert_called_once_with(
            22, {"work_mode": "cooling"}
        )
        coordinator.client.patch_sbus_device.assert_not_called()

    @pytest.mark.asyncio
    async def test_setup_adds_wtp_fan_coil_when_full_climate_fields_exist(self):
        from custom_components.sinum.climate import async_setup_entry

        coordinator = MagicMock()
        coordinator.virtual_devices = {}
        coordinator.sbus_devices = {}
        coordinator.wtp_devices = {22: dict(FIXTURES["wtp_fan_coil_full"])}
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "test_entry"
        async_add_entities = MagicMock()

        await async_setup_entry(MagicMock(), entry, async_add_entities)

        entities = async_add_entities.call_args.args[0]
        assert len(entities) == 1
        assert entities[0].unique_id == "test_entry_wtp_22"

    @pytest.mark.asyncio
    async def test_setup_ignores_wtp_fan_coil_without_climate_fields(self):
        from custom_components.sinum.climate import async_setup_entry

        coordinator = MagicMock()
        coordinator.virtual_devices = {}
        coordinator.sbus_devices = {}
        coordinator.wtp_devices = {23: dict(FIXTURES["wtp_fan_coil_shell"])}
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "test_entry"
        async_add_entities = MagicMock()

        await async_setup_entry(MagicMock(), entry, async_add_entities)

        async_add_entities.assert_called_once_with([])

    @pytest.mark.asyncio
    async def test_setup_adds_wtp_fan_coil_partial_climate_fields(self):
        """Phase 7A: WTP fan coil with only room_temperature (partial support)."""
        from custom_components.sinum.climate import async_setup_entry

        partial_wtp = {
            "id": 24,
            "name": "WTP Fan Coil Partial",
            "type": "fan_coil",
            "class": "wtp",
            "room_id": 1,
            "room_temperature": 195,
            "status": "online"
        }

        coordinator = MagicMock()
        coordinator.virtual_devices = {}
        coordinator.sbus_devices = {}
        coordinator.wtp_devices = {24: partial_wtp}
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "test_entry"
        async_add_entities = MagicMock()

        await async_setup_entry(MagicMock(), entry, async_add_entities)

        # Phase 7A: Partial climate should be added
        entities = async_add_entities.call_args.args[0]
        assert len(entities) == 1
        assert entities[0]._source == "wtp"

    def test_partial_wtp_fan_coil_graceful_degradation(self):
        """Phase 7A: Partial WTP fan coil handles missing optional fields."""
        device = {
            "id": 24,
            "name": "WTP Partial",
            "type": "fan_coil",
            "room_temperature": 200
        }
        entity, _ = _make_fan_coil(device, source="wtp", device_id=24)

        assert entity.current_temperature == 20.0
        assert entity.target_temperature is None
        assert entity.hvac_mode == HVACMode.OFF
        assert entity.fan_mode is None

    def test_partial_wtp_fan_coil_supported_features(self):
        """Phase 7A: Partial WTP fan coil without fan has limited features."""
        from homeassistant.components.climate import ClimateEntityFeature

        device = {
            "id": 24,
            "name": "WTP Partial",
            "type": "fan_coil",
            "room_temperature": 200
        }
        entity, _ = _make_fan_coil(device, source="wtp", device_id=24)

        # No fan field = only TARGET_TEMPERATURE feature
        assert (
            entity._attr_supported_features
            == ClimateEntityFeature.TARGET_TEMPERATURE
        )

    def test_wtp_fan_coil_with_fan_field_enables_fan_mode(self):
        """Phase 7A: WTP fan coil with fan field enables FAN_MODE feature."""
        from homeassistant.components.climate import ClimateEntityFeature

        device = {
            "id": 25,
            "name": "WTP With Fan",
            "type": "fan_coil",
            "room_temperature": 200,
            "fan": {
                "relay_fan": {"current_gear": "second"}
            }
        }
        entity, _ = _make_fan_coil(device, source="wtp", device_id=25)

        # With fan field = both TARGET_TEMPERATURE and FAN_MODE
        assert (
            entity._attr_supported_features
            == (
                ClimateEntityFeature.TARGET_TEMPERATURE
                | ClimateEntityFeature.FAN_MODE
            )
        )
