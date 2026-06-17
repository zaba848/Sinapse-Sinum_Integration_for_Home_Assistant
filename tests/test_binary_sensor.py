"""Tests for Sinum binary sensor entities."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from custom_components.sinum.binary_sensor import (
    BINARY_SENSOR_TYPES,
    SBUS_BINARY_SENSOR_TYPES,
    SinumBinarySensor,
)

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "sinum_devices.json").read_text()
)


def _make_wtp_coordinator(device_id: int, device: dict):
    coordinator = MagicMock()
    coordinator.wtp_devices = {device_id: device}
    coordinator.sbus_devices = {}
    return coordinator


def _make_sbus_coordinator(device: dict):
    coordinator = MagicMock()
    coordinator.wtp_devices = {}
    coordinator.sbus_devices = {32: device}
    return coordinator


def _desc(key: str, source: str = "wtp"):
    for d in (BINARY_SENSOR_TYPES if source == "wtp" else SBUS_BINARY_SENSOR_TYPES):
        if d.key == key:
            return d
    raise KeyError(key)


class TestSbusBinarySensors:
    def test_two_state_input_sensor_reads_sbus_store(self):
        device = dict(FIXTURES["sbus_two_state_sensor"])
        coordinator = _make_sbus_coordinator(device)
        entity = SinumBinarySensor(coordinator, 32, SBUS_BINARY_SENSOR_TYPES[0], "test_entry")

        assert entity.is_on is True

        coordinator.sbus_devices[32]["state"] = False
        assert entity.is_on is False


class TestWtpFanCoilValve:
    def test_valve_state_true_is_on(self):
        """WTP fan_coil with valve_state=True reports is_on=True."""
        device = {
            "id": 4, "type": "fan_coil", "class": "wtp",
            "name": "Fan Coil", "valve_state": True,
            "gear_1": {"state": False}, "gear_2": {"state": False}, "gear_3": {"state": True},
        }
        coordinator = _make_wtp_coordinator(4, device)
        entity = SinumBinarySensor(coordinator, 4, _desc("valve"), "test_entry")
        assert entity.is_on is True

    def test_valve_state_false_is_off(self):
        device = {
            "id": 4, "type": "fan_coil", "class": "wtp",
            "name": "Fan Coil", "valve_state": False,
        }
        coordinator = _make_wtp_coordinator(4, device)
        entity = SinumBinarySensor(coordinator, 4, _desc("valve"), "test_entry")
        assert entity.is_on is False

    def test_valve_state_absent_returns_none(self):
        device = {"id": 4, "type": "fan_coil", "class": "wtp", "name": "Fan Coil"}
        coordinator = _make_wtp_coordinator(4, device)
        entity = SinumBinarySensor(coordinator, 4, _desc("valve"), "test_entry")
        assert entity.is_on is None

    def test_valve_state_exposes_gear_attributes(self):
        """Valve binary sensor exposes gear states and hotel_mode as attributes."""
        device = {
            "id": 4, "type": "fan_coil", "class": "wtp",
            "name": "Fan Coil", "valve_state": True,
            "gear_1": {"hysteresis": 3, "state": False},
            "gear_2": {"hysteresis": 30, "state": False},
            "gear_3": {"hysteresis": 42, "state": True},
            "hotel_mode": False,
        }
        coordinator = _make_wtp_coordinator(4, device)
        entity = SinumBinarySensor(coordinator, 4, _desc("valve"), "test_entry")
        attrs = entity.extra_state_attributes
        assert attrs["gear_1_active"] is False
        assert attrs["gear_2_active"] is False
        assert attrs["gear_3_active"] is True
        assert attrs["hotel_mode"] is False


class TestThermostatAttributes:
    def test_thermostat_exposes_heating_cooling_targets(self):
        """Thermostat exposes target_temperature_heating/cooling as attributes."""
        from custom_components.sinum.climate import SinumThermostat
        device = {
            **FIXTURES["virtual_thermostat"],
            "target_temperature_heating": 350,
            "target_temperature_cooling": 200,
            "target_temperature_mode": {"current": "constant", "remaining_time": 0},
            "is_window_open": False,
            "floor_temperature": 280,
        }
        coordinator = MagicMock()
        coordinator.client.decode_temperature = lambda raw: raw / 10
        coordinator.client.encode_temperature = lambda c: round(c * 10)
        coordinator.virtual_devices = {10: device}

        entity = SinumThermostat(coordinator, 10, "test_entry")
        attrs = entity.extra_state_attributes

        assert attrs["target_temperature_heating"] == 35.0
        assert attrs["target_temperature_cooling"] == 20.0
        assert attrs["target_temperature_mode"] == "constant"
        assert attrs["is_window_open"] is False
        assert attrs["floor_temperature"] == 28.0

