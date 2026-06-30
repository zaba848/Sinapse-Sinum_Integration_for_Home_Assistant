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
    coordinator.hub_name = ""
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


class TestModbusNewDeviceTypes:
    """Coverage for heat_pump, inverter, battery, car_charger, common_dhw_main."""

    def _make_coord(self, dev_type: str, fields: dict) -> object:
        dev = {"id": 1, "type": dev_type, "name": dev_type, **fields}
        return _make_coordinator(modbus={1: dev})

    def _build(self, dev_type: str, fields: dict):
        from custom_components.sinum.sensor_modbus import build_modbus_sensor_entities

        coord = self._make_coord(dev_type, fields)
        return build_modbus_sensor_entities(coord, "entry")

    def test_heat_pump_creates_7_sensors(self):
        entities = self._build(
            "heat_pump",
            {
                "temperature_outdoor": 50,
                "heating_supply": 300,
                "heating_return": 280,
                "buffer_temperature": 400,
                "hot_gas_temperature": 700,
                "compressor_percentage": 80,
                "running_hours": 1234,
            },
        )
        assert len(entities) == 7

    def test_heat_pump_temperature_scaled(self):
        coord = self._make_coord("heat_pump", {"temperature_outdoor": 150})
        from custom_components.sinum.sensor_modbus import build_modbus_sensor_entities

        entities = build_modbus_sensor_entities(coord, "entry")
        outdoor = next(e for e in entities if e.entity_description.key == "temperature_outdoor")
        assert outdoor.native_value == pytest.approx(15.0)

    def test_heat_pump_all_disabled_by_default(self):
        entities = self._build("heat_pump", {"temperature_outdoor": 0})
        for e in entities:
            assert e.entity_description.entity_registry_enabled_default is False

    def test_inverter_creates_5_sensors(self):
        entities = self._build(
            "inverter",
            {
                "pv_total_active_power": 3000,
                "grid_total_active_power": 100,
                "energy_produced_total": 5000000,
                "energy_produced_today": 12000,
                "energy_fed_today": 2000,
            },
        )
        assert len(entities) == 5

    def test_inverter_pv_power_value(self):
        coord = self._make_coord("inverter", {"pv_total_active_power": 3500})
        from custom_components.sinum.sensor_modbus import build_modbus_sensor_entities

        entities = build_modbus_sensor_entities(coord, "entry")
        pv = next(e for e in entities if e.entity_description.key == "pv_total_active_power")
        assert pv.native_value == 3500

    def test_battery_creates_4_sensors(self):
        entities = self._build(
            "battery",
            {
                "soc": 75,
                "charge_power": 2000,
                "energy_charged_total": 100000,
                "energy_discharged_total": 80000,
            },
        )
        assert len(entities) == 4

    def test_battery_soc_value(self):
        coord = self._make_coord("battery", {"soc": 90})
        from custom_components.sinum.sensor_modbus import build_modbus_sensor_entities

        entities = build_modbus_sensor_entities(coord, "entry")
        soc = next(e for e in entities if e.entity_description.key == "soc")
        assert soc.native_value == 90

    def test_car_charger_creates_5_sensors(self):
        entities = self._build(
            "car_charger",
            {
                "charge_power": 7400,
                "current": 32,
                "voltage": 230,
                "energy_charged_total": 50000,
                "energy_charged_today": 10000,
            },
        )
        assert len(entities) == 5

    def test_common_dhw_main_creates_2_sensors(self):
        entities = self._build(
            "common_dhw_main",
            {"temperature_domestic_hot_water": 520, "target_temperature": 600},
        )
        assert len(entities) == 2

    def test_dhw_temperature_scaled(self):
        coord = self._make_coord("common_dhw_main", {"temperature_domestic_hot_water": 520})
        from custom_components.sinum.sensor_modbus import build_modbus_sensor_entities

        entities = build_modbus_sensor_entities(coord, "entry")
        dhw = next(e for e in entities if "domestic_hot_water" in e.entity_description.key)
        assert dhw.native_value == pytest.approx(52.0)

    def test_all_new_types_disabled_by_default(self):
        for dev_type, fields in [
            ("inverter", {"pv_total_active_power": 0}),
            ("battery", {"soc": 0}),
            ("car_charger", {"charge_power": 0}),
            ("common_dhw_main", {"temperature_domestic_hot_water": 0}),
        ]:
            entities = self._build(dev_type, fields)
            for e in entities:
                assert e.entity_description.entity_registry_enabled_default is False, (
                    f"{dev_type}.{e.entity_description.key} should be disabled by default"
                )
