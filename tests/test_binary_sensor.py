"""Tests for Sinum binary sensor entities."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from custom_components.sinum.binary_sensor import (
    SBUS_BINARY_SENSOR_TYPES,
    SinumBinarySensor,
)

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "sinum_devices.json").read_text()
)


def _make_coordinator(device: dict):
    coordinator = MagicMock()
    coordinator.wtp_devices = {}
    coordinator.sbus_devices = {32: device}
    return coordinator


class TestSbusBinarySensors:
    def test_two_state_input_sensor_reads_sbus_store(self):
        device = dict(FIXTURES["sbus_two_state_sensor"])
        coordinator = _make_coordinator(device)
        entity = SinumBinarySensor(
            coordinator,
            32,
            SBUS_BINARY_SENSOR_TYPES[0],
            "test_entry",
        )

        assert entity.is_on is True

        coordinator.sbus_devices[32]["state"] = False
        assert entity.is_on is False
