"""Tests for Sinum sensor entities."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from custom_components.sinum.sensor import SBUS_SENSORS, SinumSensor

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "sinum_devices.json").read_text()
)


def _description(key: str):
    return next(desc for desc in SBUS_SENSORS if desc.key == key)


def _make_coordinator(device_id: int, device: dict):
    coordinator = MagicMock()
    coordinator.virtual_devices = {}
    coordinator.wtp_devices = {}
    coordinator.sbus_devices = {device_id: device}
    return coordinator


class TestSbusSensors:
    def test_temperature_sensor_reads_sbus_store(self):
        device = dict(FIXTURES["sbus_temperature_sensor"])
        coordinator = _make_coordinator(30, device)
        entity = SinumSensor(coordinator, 30, _description("temperature"), "test_entry")

        assert entity.native_value == 20.5

        coordinator.sbus_devices[30]["temperature"] = 211
        assert entity.native_value == 21.1

    def test_humidity_sensor_reads_sbus_store(self):
        device = dict(FIXTURES["sbus_humidity_sensor"])
        coordinator = _make_coordinator(31, device)
        entity = SinumSensor(coordinator, 31, _description("humidity"), "test_entry")

        assert entity.native_value == 52.0
