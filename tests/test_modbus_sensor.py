"""Tests for Modbus energy meter sensor entities."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "sinum_devices.json").read_text())


def _make_coordinator(modbus: dict | None = None) -> MagicMock:
    coordinator = MagicMock()
    coordinator.modbus_devices = modbus or {}
    return coordinator


def _make_entity(field_path: str, device: dict | None = None):
    from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
    from homeassistant.const import UnitOfPower

    from custom_components.sinum.sensor_modbus import (
        SinumModbusSensor,
        SinumModbusSensorDescription,
    )

    dev = dict(device or FIXTURES["modbus_energy_meter"])
    coordinator = _make_coordinator(modbus={18: dev})
    desc = SinumModbusSensorDescription(
        key=field_path.replace(".", "_"),
        field_path=field_path,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
    )
    entity = SinumModbusSensor(coordinator, 18, "test_entry", desc)
    entity.hass = MagicMock()
    return entity, coordinator


class TestSinumModbusSensor:
    def test_unique_id(self):
        entity, _ = _make_entity("total_active_power")
        assert entity.unique_id == "test_entry_modbus_18_total_active_power"

    def test_native_value_top_level(self):
        entity, _ = _make_entity("total_active_power")
        assert entity.native_value == 2600

    def test_native_value_nested(self):
        entity, _ = _make_entity("phase_1.voltage")
        assert entity.native_value == 230

    def test_native_value_nested_phase_2_current(self):
        entity, _ = _make_entity("phase_2.current")
        assert entity.native_value == 3

    def test_native_value_missing_field_returns_none(self):
        entity, _ = _make_entity("nonexistent_field")
        assert entity.native_value is None

    def test_native_value_missing_nested_returns_none(self):
        entity, _ = _make_entity("phase_99.voltage")
        assert entity.native_value is None

    def test_native_value_with_scale(self):
        from homeassistant.components.sensor import SensorStateClass

        from custom_components.sinum.sensor_modbus import (
            SinumModbusSensor,
            SinumModbusSensorDescription,
        )

        dev = dict(FIXTURES["modbus_energy_meter"])
        coordinator = _make_coordinator(modbus={18: dev})
        desc = SinumModbusSensorDescription(
            key="total_active_power_kw",
            field_path="total_active_power",
            state_class=SensorStateClass.MEASUREMENT,
            scale=0.001,
        )
        entity = SinumModbusSensor(coordinator, 18, "entry", desc)
        assert entity.native_value == pytest.approx(2.6, abs=1e-3)

    def test_device_info_name(self):
        entity, _ = _make_entity("total_active_power")
        assert entity.device_info["name"] == "Energy meter 18"

    def test_available_when_device_present(self):
        entity, _ = _make_entity("total_active_power")
        assert entity.available is True

    def test_unavailable_when_device_absent(self):
        from custom_components.sinum.sensor_modbus import (
            SinumModbusSensor,
            SinumModbusSensorDescription,
        )

        coordinator = _make_coordinator(modbus={})
        desc = SinumModbusSensorDescription(
            key="total_active_power",
            field_path="total_active_power",
        )
        entity = SinumModbusSensor(coordinator, 18, "entry", desc)
        assert entity.available is False

    def test_tariff_indicator(self):
        entity, _ = _make_entity("tariff_indicator")
        assert entity.native_value == 1

    def test_energy_consumed_total(self):
        entity, _ = _make_entity("energy_consumed_total")
        assert entity.native_value == 12345678

    def test_energy_fed_total(self):
        entity, _ = _make_entity("energy_fed_total")
        assert entity.native_value == 987654

    def test_power_from_grid(self):
        entity, _ = _make_entity("power_from_grid")
        assert entity.native_value == 2600

    def test_power_to_grid(self):
        entity, _ = _make_entity("power_to_grid")
        assert entity.native_value == 0

    def test_phase_3_sags(self):
        entity, _ = _make_entity("phase_3.number_of_voltage_sags")
        assert entity.native_value == 1


class TestBuildModbusSensorEntities:
    def test_energy_meter_creates_15_sensors(self):
        from custom_components.sinum.sensor_modbus import build_modbus_sensor_entities

        dev = dict(FIXTURES["modbus_energy_meter"])
        coordinator = _make_coordinator(modbus={18: dev})
        entities = build_modbus_sensor_entities(coordinator, "entry")
        # 5 top-level + 3×3 per-phase (voltage/current/power) + tariff_indicator = 15
        assert len(entities) == 15

    def test_unknown_type_creates_no_sensors(self):
        from custom_components.sinum.sensor_modbus import build_modbus_sensor_entities

        coordinator = _make_coordinator(
            modbus={99: {"id": 99, "type": "unknown_device", "name": "X"}}
        )
        assert build_modbus_sensor_entities(coordinator, "entry") == []

    def test_empty_modbus_devices(self):
        from custom_components.sinum.sensor_modbus import build_modbus_sensor_entities

        coordinator = _make_coordinator(modbus={})
        assert build_modbus_sensor_entities(coordinator, "entry") == []

    def test_all_sensor_keys_unique(self):
        from custom_components.sinum.sensor_modbus import build_modbus_sensor_entities

        dev = dict(FIXTURES["modbus_energy_meter"])
        coordinator = _make_coordinator(modbus={18: dev})
        entities = build_modbus_sensor_entities(coordinator, "entry")
        unique_ids = [e.unique_id for e in entities]
        assert len(unique_ids) == len(set(unique_ids))

    def test_all_disabled_by_default(self):
        from custom_components.sinum.sensor_modbus import build_modbus_sensor_entities

        dev = dict(FIXTURES["modbus_energy_meter"])
        coordinator = _make_coordinator(modbus={18: dev})
        entities = build_modbus_sensor_entities(coordinator, "entry")
        for entity in entities:
            assert entity.entity_description.entity_registry_enabled_default is False
