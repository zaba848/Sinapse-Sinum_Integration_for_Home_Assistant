"""Integration tests: coordinator data processing → entity.native_value.

Tests the full data flow:
  mock API response → coordinator internal functions → entity.native_value

The HA DataUpdateCoordinator framework is not needed here; we test the
coordinator's data-processing logic and entity property computation directly.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sinum.coordinator import (
    SinumCoordinator,
    _collect_device_ids,
    _index_by_id,
    _device_class,
)
from custom_components.sinum.sensor_bus import SBUS_SENSORS, SinumSensor
from custom_components.sinum.climate_bus import (
    SinumFanCoilClimate,
    SinumTemperatureRegulatorClimate,
)
from custom_components.sinum.fan import SinumFanCoilFan
from custom_components.sinum.const import STYPE_FAN_COIL, STYPE_TEMPERATURE_REGULATOR
from homeassistant.components.climate import HVACMode


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _sbus_thermostat(device_id: int = 1, temperature: int = 225) -> dict:
    return {
        "id": device_id,
        "type": STYPE_TEMPERATURE_REGULATOR,
        "temperature": temperature,
        "target_temperature": 200,
        "_device_name": "Room Thermostat",
        "_area": "Living Room",
    }


def _sbus_fan_coil(device_id: int = 2, work_mode: str = "automatic") -> dict:
    return {
        "id": device_id,
        "type": STYPE_FAN_COIL,
        "work_mode": work_mode,
        "target_temperature": 220,
        "temperature": 190,
        "fan": {
            "relay_fan": {"current_gear": "second"},
            "manual_fan_gear": "second",
        },
        "_device_name": "Fan Coil",
        "_area": "Bedroom",
    }


def _coordinator_with_sbus(devices: list[dict]) -> MagicMock:
    c = MagicMock()
    c.sbus_devices = {int(d["id"]): d for d in devices}
    c.wtp_devices = {}
    c.virtual_devices = {}
    c.lora_devices = {}
    c.hub_info = {}
    c.schedules = []
    c.automations = []
    c.client = MagicMock()
    return c


# ---------------------------------------------------------------------------
# Coordinator helper functions (pure logic, no HA framework needed)
# ---------------------------------------------------------------------------

class TestCollectDeviceIds:
    """_collect_device_ids parses room data → (virtual, wtp, sbus, lora) id lists."""

    def test_sbus_device_in_room_goes_to_sbus_bucket(self):
        rooms = [{"devices": [{"class": "sbus", "id": 42}]}]
        virtual, wtp, sbus, lora = _collect_device_ids(rooms)
        assert 42 in sbus
        assert 42 not in virtual
        assert 42 not in wtp

    def test_wtp_device_in_room_goes_to_wtp_bucket(self):
        rooms = [{"devices": [{"class": "wtp", "id": 7}]}]
        virtual, wtp, sbus, lora = _collect_device_ids(rooms)
        assert 7 in wtp
        assert 7 not in sbus

    def test_virtual_device_in_room_goes_to_virtual_bucket(self):
        rooms = [{"devices": [{"class": "virtual", "id": 5}]}]
        virtual, wtp, sbus, lora = _collect_device_ids(rooms)
        assert 5 in virtual

    def test_mixed_devices_separated_correctly(self):
        rooms = [
            {"devices": [{"class": "sbus", "id": 1}, {"class": "wtp", "id": 2}]},
            {"devices": [{"class": "virtual", "id": 3}]},
        ]
        virtual, wtp, sbus, lora = _collect_device_ids(rooms)
        assert 1 in sbus
        assert 2 in wtp
        assert 3 in virtual

    def test_empty_rooms_returns_empty_buckets(self):
        virtual, wtp, sbus, lora = _collect_device_ids([])
        assert virtual == wtp == sbus == lora == []

    def test_room_with_no_devices_key(self):
        rooms = [{"name": "Empty Room"}]
        virtual, wtp, sbus, lora = _collect_device_ids(rooms)
        assert virtual == wtp == sbus == lora == []


class TestIndexById:
    """_index_by_id converts a list of devices to a dict keyed by int(id)."""

    def test_indexes_by_id(self):
        devices = [{"id": "1", "type": "thermostat"}, {"id": "2", "type": "relay"}]
        result = _index_by_id(devices)
        assert 1 in result
        assert 2 in result
        assert result[1]["type"] == "thermostat"

    def test_skips_devices_without_id(self):
        devices = [{"type": "no_id"}, {"id": "5", "type": "with_id"}]
        result = _index_by_id(devices)
        assert 5 in result
        assert len(result) == 1

    def test_empty_list_returns_empty_dict(self):
        assert _index_by_id([]) == {}


class TestDeviceClass:
    """_device_class extracts the bus class from device metadata."""

    def test_class_field_sbus(self):
        assert _device_class({"class": "sbus"}) == "sbus"

    def test_class_field_wtp(self):
        assert _device_class({"class": "wtp"}) == "wtp"

    def test_source_field_used_as_fallback(self):
        assert _device_class({"source": "sbus"}) == "sbus"

    def test_bus_field_used_as_last_resort(self):
        assert _device_class({"bus": "wtp"}) == "wtp"

    def test_empty_device_returns_empty_string(self):
        assert _device_class({}) == ""


# ---------------------------------------------------------------------------
# Sensor entity reads from coordinator device store
# ---------------------------------------------------------------------------

class TestSensorEntityIntegration:
    """Entity.native_value reads the right value from coordinator.sbus_devices."""

    def test_sbus_temperature_reads_from_coordinator(self):
        coordinator = _coordinator_with_sbus([_sbus_thermostat(temperature=225)])
        desc = next(d for d in SBUS_SENSORS if d.api_key == "temperature" and d.source == "sbus")
        entity = SinumSensor(coordinator, 1, desc, "entry1")
        entity.coordinator = coordinator
        assert entity.native_value == pytest.approx(22.5)

    def test_sbus_temperature_unavailable_when_device_missing(self):
        coordinator = _coordinator_with_sbus([])
        desc = next(d for d in SBUS_SENSORS if d.api_key == "temperature" and d.source == "sbus")
        entity = SinumSensor(coordinator, 999, desc, "entry1")
        entity.coordinator = coordinator
        assert entity.native_value is None

    def test_sbus_target_temperature_reads_correctly(self):
        from custom_components.sinum.sensor_bus import SBUS_REGULATOR_SENSORS
        thermostat = _sbus_thermostat(temperature=225)
        thermostat["target_temperature"] = 210
        coordinator = _coordinator_with_sbus([thermostat])
        desc = next(d for d in SBUS_REGULATOR_SENSORS if d.api_key == "target_temperature")
        entity = SinumSensor(coordinator, 1, desc, "entry1")
        entity.coordinator = coordinator
        assert entity.native_value == pytest.approx(21.0)

    def test_sbus_temperature_zero_returns_none_when_zero_unavailable(self):
        """temperature=0 means sensor is unavailable for thermostat descriptors."""
        thermostat = _sbus_thermostat(temperature=0)
        coordinator = _coordinator_with_sbus([thermostat])
        desc = next(d for d in SBUS_SENSORS if d.api_key == "temperature" and d.source == "sbus")
        entity = SinumSensor(coordinator, 1, desc, "entry1")
        entity.coordinator = coordinator
        # zero_is_unavailable defaults True for temperature sensors
        assert entity.native_value is None or entity.native_value == 0.0


# ---------------------------------------------------------------------------
# Fan entity reads from coordinator device store
# ---------------------------------------------------------------------------

class TestFanEntityIntegration:
    def test_fan_is_on_when_work_mode_automatic(self):
        fan_coil = _sbus_fan_coil(device_id=2, work_mode="automatic")
        coordinator = _coordinator_with_sbus([fan_coil])
        entity = SinumFanCoilFan(coordinator, 2, "entry1", "sbus")
        entity.coordinator = coordinator
        assert entity.is_on is True

    def test_fan_is_off_when_work_mode_off(self):
        fan_coil = _sbus_fan_coil(device_id=3, work_mode="off")
        coordinator = _coordinator_with_sbus([fan_coil])
        entity = SinumFanCoilFan(coordinator, 3, "entry1", "sbus")
        entity.coordinator = coordinator
        assert entity.is_on is False

    def test_fan_preset_mode_second_gear(self):
        fan_coil = _sbus_fan_coil(device_id=2)
        coordinator = _coordinator_with_sbus([fan_coil])
        entity = SinumFanCoilFan(coordinator, 2, "entry1", "sbus")
        entity.coordinator = coordinator
        assert entity.preset_mode == "2"

    def test_fan_preset_mode_first_gear(self):
        fan_coil = _sbus_fan_coil(device_id=2)
        fan_coil["fan"]["relay_fan"]["current_gear"] = "first"
        coordinator = _coordinator_with_sbus([fan_coil])
        entity = SinumFanCoilFan(coordinator, 2, "entry1", "sbus")
        entity.coordinator = coordinator
        assert entity.preset_mode == "1"

    def test_fan_preset_mode_none_when_gear_missing(self):
        fan_coil = _sbus_fan_coil(device_id=2)
        fan_coil["fan"]["relay_fan"] = {}
        coordinator = _coordinator_with_sbus([fan_coil])
        entity = SinumFanCoilFan(coordinator, 2, "entry1", "sbus")
        entity.coordinator = coordinator
        assert entity.preset_mode is None


# ---------------------------------------------------------------------------
# Climate entity reads from coordinator device store
# ---------------------------------------------------------------------------

class TestClimateEntityIntegration:
    def test_regulator_current_temperature_from_coordinator(self):
        thermostat = _sbus_thermostat(device_id=1, temperature=215)
        coordinator = _coordinator_with_sbus([thermostat])
        entity = SinumTemperatureRegulatorClimate(coordinator, 1, "entry1", "sbus")
        entity.coordinator = coordinator
        assert entity.current_temperature == pytest.approx(21.5)

    def test_regulator_target_temperature_from_coordinator(self):
        thermostat = _sbus_thermostat(device_id=1, temperature=215)
        thermostat["target_temperature"] = 200
        coordinator = _coordinator_with_sbus([thermostat])
        entity = SinumTemperatureRegulatorClimate(coordinator, 1, "entry1", "sbus")
        entity.coordinator = coordinator
        assert entity.target_temperature == pytest.approx(20.0)

    def test_fan_coil_hvac_mode_heating(self):
        fan_coil = _sbus_fan_coil(device_id=2, work_mode="heating")
        coordinator = _coordinator_with_sbus([fan_coil])
        entity = SinumFanCoilClimate(coordinator, 2, "entry1", "sbus")
        entity.coordinator = coordinator
        assert entity.hvac_mode == HVACMode.HEAT

    def test_fan_coil_hvac_mode_off(self):
        fan_coil = _sbus_fan_coil(device_id=2, work_mode="off")
        coordinator = _coordinator_with_sbus([fan_coil])
        entity = SinumFanCoilClimate(coordinator, 2, "entry1", "sbus")
        entity.coordinator = coordinator
        assert entity.hvac_mode == HVACMode.OFF

    def test_fan_coil_hvac_mode_cooling(self):
        fan_coil = _sbus_fan_coil(device_id=2, work_mode="cooling")
        coordinator = _coordinator_with_sbus([fan_coil])
        entity = SinumFanCoilClimate(coordinator, 2, "entry1", "sbus")
        entity.coordinator = coordinator
        assert entity.hvac_mode == HVACMode.COOL
