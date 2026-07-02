"""Tests for SLINK device support — relay switch + energy_meter sensors."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sinum.const import STYPE_RELAY

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "sinum_devices.json").read_text())


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_coordinator(slink: dict | None = None) -> MagicMock:
    c = MagicMock()
    c.slink_devices = slink or {}
    c.hub_name = ""
    c.client = MagicMock()
    c.client.patch_slink_device = AsyncMock(return_value={})
    return c


def _wire(entity):
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    return entity


# ── SLINK relay switch ─────────────────────────────────────────────────────────


class TestSlinkRelaySwitch:
    def _make_switch(self, state: bool = True):
        from custom_components.sinum.switch import SinumBusRelaySwitch

        dev = dict(FIXTURES["slink_relay"])
        dev["state"] = state
        coordinator = _make_coordinator(slink={1: dev})
        entity = SinumBusRelaySwitch(coordinator, 1, "entry", "slink")
        return _wire(entity), coordinator

    def test_unique_id(self):
        entity, _ = self._make_switch()
        assert entity.unique_id == "entry_slink_1"

    def test_is_on_true(self):
        entity, _ = self._make_switch(state=True)
        assert entity.is_on is True

    def test_is_on_false(self):
        entity, _ = self._make_switch(state=False)
        assert entity.is_on is False

    def test_device_info_model(self):
        entity, _ = self._make_switch()
        assert "SLINK" in entity.device_info["model"]

    @pytest.mark.asyncio
    async def test_turn_on_calls_patch(self):
        entity, coordinator = self._make_switch(state=False)
        coordinator.client.patch_slink_device = AsyncMock(return_value={"state": True})
        coordinator.slink_devices[1] = dict(FIXTURES["slink_relay"])
        coordinator.slink_devices[1]["state"] = False
        await entity.async_turn_on()
        coordinator.client.patch_slink_device.assert_awaited_once_with(1, {"state": True})

    @pytest.mark.asyncio
    async def test_turn_off_calls_patch(self):
        entity, coordinator = self._make_switch(state=True)
        coordinator.client.patch_slink_device = AsyncMock(return_value={"state": False})
        coordinator.slink_devices[1] = dict(FIXTURES["slink_relay"])
        await entity.async_turn_off()
        coordinator.client.patch_slink_device.assert_awaited_once_with(1, {"state": False})

    @pytest.mark.asyncio
    async def test_turn_on_raises_on_api_error(self):
        from homeassistant.exceptions import HomeAssistantError

        from custom_components.sinum.switch import SinumBusRelaySwitch

        dev = dict(FIXTURES["slink_relay"])
        coordinator = _make_coordinator(slink={1: dev})
        coordinator.client.patch_slink_device = AsyncMock(side_effect=Exception("hub down"))
        entity = _wire(SinumBusRelaySwitch(coordinator, 1, "entry", "slink"))
        with pytest.raises(HomeAssistantError):
            await entity.async_turn_on()

    def test_available_when_device_present(self):
        entity, _ = self._make_switch()
        assert entity.available is True

    def test_unavailable_when_device_absent(self):
        from custom_components.sinum.switch import SinumBusRelaySwitch

        coordinator = _make_coordinator(slink={})
        entity = _wire(SinumBusRelaySwitch(coordinator, 99, "entry", "slink"))
        assert entity.available is False


class TestSlinkSwitchEntityFactory:
    def test_relay_type_creates_switch(self):
        from custom_components.sinum.switch import _slink_switch_entity

        dev = dict(FIXTURES["slink_relay"])
        coordinator = _make_coordinator(slink={1: dev})
        entity = _slink_switch_entity(coordinator, 1, "entry", dev)
        assert entity is not None

    def test_non_relay_type_returns_none(self):
        from custom_components.sinum.switch import _slink_switch_entity

        dev = {"id": 2, "type": "energy_meter", "name": "EM"}
        coordinator = _make_coordinator(slink={2: dev})
        assert _slink_switch_entity(coordinator, 2, "entry", dev) is None

    def test_bus_entity_factory_slink_relay(self):
        from custom_components.sinum.switch import _bus_switch_entity

        dev = dict(FIXTURES["slink_relay"])
        coordinator = _make_coordinator(slink={1: dev})
        entity = _bus_switch_entity(coordinator, 1, "entry", "slink", dev)
        assert entity is not None


# ── SLINK energy_meter sensors ─────────────────────────────────────────────────


class TestSlinkSensor:
    def _make_entity(self, field_path: str):
        from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
        from homeassistant.const import UnitOfPower

        from custom_components.sinum.sensor_modbus import (
            SinumModbusSensorDescription,
            SinumSlinkSensor,
        )

        dev = dict(FIXTURES["slink_energy_meter"])
        coordinator = _make_coordinator(slink={2: dev})
        desc = SinumModbusSensorDescription(
            key=field_path.replace(".", "_"),
            field_path=field_path,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfPower.WATT,
        )
        entity = SinumSlinkSensor(coordinator, 2, "entry", desc)
        entity.hass = MagicMock()
        return entity, coordinator

    def test_unique_id(self):
        entity, _ = self._make_entity("active_power")
        assert entity.unique_id == "entry_slink_2_active_power"

    def test_device_info_name(self):
        entity, _ = self._make_entity("active_power")
        assert entity.device_info["name"] == "SLINK Energy Meter"

    def test_native_value_active_power(self):
        entity, _ = self._make_entity("active_power")
        assert entity.native_value == 1500

    def test_native_value_current(self):
        entity, _ = self._make_entity("current")
        assert entity.native_value == pytest.approx(6.5)

    def test_native_value_energy_consumed_total(self):
        entity, _ = self._make_entity("energy_consumed_total")
        assert entity.native_value == 54321000

    def test_native_value_energy_consumed_today(self):
        entity, _ = self._make_entity("energy_consumed_today")
        assert entity.native_value == 12000

    def test_native_value_energy_consumed_yesterday(self):
        entity, _ = self._make_entity("energy_consumed_yesterday")
        assert entity.native_value == 11000

    def test_native_value_missing_field_returns_none(self):
        entity, _ = self._make_entity("nonexistent")
        assert entity.native_value is None

    def test_available_when_device_present(self):
        entity, _ = self._make_entity("active_power")
        assert entity.available is True

    def test_unavailable_when_device_absent(self):
        from custom_components.sinum.sensor_modbus import (
            SinumModbusSensorDescription,
            SinumSlinkSensor,
        )

        coordinator = _make_coordinator(slink={})
        desc = SinumModbusSensorDescription(key="active_power", field_path="active_power")
        entity = SinumSlinkSensor(coordinator, 99, "entry", desc)
        entity.hass = MagicMock()
        assert entity.available is False


class TestBuildSlinkSensorEntities:
    def test_energy_meter_creates_5_sensors(self):
        from custom_components.sinum.sensor_modbus import build_slink_sensor_entities

        dev = dict(FIXTURES["slink_energy_meter"])
        coordinator = _make_coordinator(slink={2: dev})
        entities = build_slink_sensor_entities(coordinator, "entry")
        assert len(entities) == 5

    def test_relay_creates_no_sensors(self):
        from custom_components.sinum.sensor_modbus import build_slink_sensor_entities

        dev = dict(FIXTURES["slink_relay"])
        coordinator = _make_coordinator(slink={1: dev})
        assert build_slink_sensor_entities(coordinator, "entry") == []

    def test_unknown_type_creates_no_sensors(self):
        from custom_components.sinum.sensor_modbus import build_slink_sensor_entities

        coordinator = _make_coordinator(slink={99: {"id": 99, "type": "unknown", "name": "X"}})
        assert build_slink_sensor_entities(coordinator, "entry") == []

    def test_empty_slink_devices(self):
        from custom_components.sinum.sensor_modbus import build_slink_sensor_entities

        coordinator = _make_coordinator(slink={})
        assert build_slink_sensor_entities(coordinator, "entry") == []

    def test_all_sensor_unique_ids_distinct(self):
        from custom_components.sinum.sensor_modbus import build_slink_sensor_entities

        dev = dict(FIXTURES["slink_energy_meter"])
        coordinator = _make_coordinator(slink={2: dev})
        entities = build_slink_sensor_entities(coordinator, "entry")
        ids = [e.unique_id for e in entities]
        assert len(ids) == len(set(ids))


# ── SLINK in coordinator fetch ─────────────────────────────────────────────────


class TestSlinkInApplyOptionalStores:
    def test_slink_devices_set_when_provided(self):
        from custom_components.sinum.coordinator import _apply_optional_stores

        coordinator = MagicMock()
        coordinator.alarm_zones = {}
        coordinator.modbus_devices = {}
        coordinator.video_devices = {}
        coordinator.slink_devices = {}
        slink_list = [{"id": 1, "type": "relay"}, {"id": 2, "type": "energy_meter"}]
        _apply_optional_stores(coordinator, None, None, None, slink_list)
        assert 1 in coordinator.slink_devices
        assert 2 in coordinator.slink_devices

    def test_slink_devices_unchanged_when_none(self):
        from custom_components.sinum.coordinator import _apply_optional_stores

        coordinator = MagicMock()
        coordinator.alarm_zones = {}
        coordinator.modbus_devices = {}
        coordinator.video_devices = {}
        existing = {5: {"id": 5, "type": "relay"}}
        coordinator.slink_devices = existing
        _apply_optional_stores(coordinator, None, None, None, None)
        assert coordinator.slink_devices is existing

    def test_slink_not_passed_defaults_to_none(self):
        from custom_components.sinum.coordinator import _apply_optional_stores

        coordinator = MagicMock()
        coordinator.alarm_zones = {}
        coordinator.modbus_devices = {}
        coordinator.video_devices = {}
        existing = {5: {"id": 5, "type": "relay"}}
        coordinator.slink_devices = existing
        _apply_optional_stores(coordinator, None, None, None)
        assert coordinator.slink_devices is existing

    def test_native_value_with_scale(self):
        """SinumSlinkSensor.native_value applies scale when != 1.0."""
        from custom_components.sinum.sensor_modbus import (
            SinumModbusSensorDescription,
            SinumSlinkSensor,
        )

        dev = dict(FIXTURES["slink_energy_meter"])
        coordinator = _make_coordinator(slink={2: dev})
        desc = SinumModbusSensorDescription(
            key="active_power_kw",
            field_path="active_power",
            scale=0.001,
        )
        entity = SinumSlinkSensor(coordinator, 2, "entry", desc)
        entity.hass = MagicMock()
        assert entity.native_value == pytest.approx(1.5, abs=1e-3)
