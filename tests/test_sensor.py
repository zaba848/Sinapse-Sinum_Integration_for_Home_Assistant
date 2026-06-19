"""Tests for Sinum sensor entities."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from custom_components.sinum.sensor import (
    ENERGY_SENSORS,
    LORA_SENSORS,
    SBUS_SENSORS,
    VIRTUAL_SENSORS,
    WEATHER_SENSORS,
    WTP_SENSORS,
    SinumSensor,
    SinumTemperatureRegulatorSensor,
)

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "sinum_devices.json").read_text())


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


class TestSensorStateClassContracts:
    def test_measurement_device_classes_have_state_class(self):
        descriptors = VIRTUAL_SENSORS + WTP_SENSORS + SBUS_SENSORS + LORA_SENSORS + WEATHER_SENSORS
        measurement_classes = {
            SensorDeviceClass.TEMPERATURE,
            SensorDeviceClass.HUMIDITY,
            SensorDeviceClass.ILLUMINANCE,
            SensorDeviceClass.CO2,
            SensorDeviceClass.PRESSURE,
        }

        missing = [
            (desc.source, desc.key)
            for desc in descriptors
            if desc.device_class in measurement_classes
            and desc.state_class != SensorStateClass.MEASUREMENT
        ]

        assert missing == []

    def test_energy_and_impulse_totals_are_total_increasing(self):
        descriptors = WTP_SENSORS + SBUS_SENSORS + ENERGY_SENSORS
        total_keys = {
            "energy_consumed_total",
            "energy_consumed_today",
            "energy_consumption",
            "energy_production",
            "impulse_total_count",
            "impulse_total_value",
        }

        missing = [
            (desc.source, desc.key)
            for desc in descriptors
            if desc.key in total_keys and desc.state_class != SensorStateClass.TOTAL_INCREASING
        ]

        assert missing == []


class TestPhase7BTemperatureRegulators:
    """Phase 7B: Temperature regulator sensors."""

    def _wtp_regulator_description(self, key: str):
        """Get WTP regulator sensor description by key."""
        return next(
            desc for desc in WTP_SENSORS if desc.key == key and desc.source == "wtp_regulator"
        )

    def _make_wtp_coordinator(self, device_id: int, device: dict):
        """Create coordinator with WTP device."""
        coordinator = MagicMock()
        coordinator.virtual_devices = {}
        coordinator.wtp_devices = {device_id: device}
        coordinator.sbus_devices = {}
        return coordinator

    def test_regulator_temperature_sensor_returns_none_when_absent(self):
        """Real regulators have no temperature field — sensor correctly returns None."""
        device = dict(FIXTURES["wtp_temperature_regulator_full"])
        coordinator = self._make_wtp_coordinator(100, device)
        entity = SinumTemperatureRegulatorSensor(
            coordinator, 100, self._wtp_regulator_description("temperature"), "test_entry"
        )

        assert entity.native_value is None

    def test_regulator_target_temperature_sensor(self):
        """Temperature regulator reads target temperature."""
        device = dict(FIXTURES["wtp_temperature_regulator_full"])
        coordinator = self._make_wtp_coordinator(100, device)
        entity = SinumTemperatureRegulatorSensor(
            coordinator, 100, self._wtp_regulator_description("target_temperature"), "test_entry"
        )

        assert entity.native_value == 22.0

    def test_regulator_sensor_shows_attributes(self):
        """Temperature regulator sensor shows mode, mode_mutable, etc. as attributes."""
        device = dict(FIXTURES["wtp_temperature_regulator_full"])
        coordinator = self._make_wtp_coordinator(100, device)
        entity = SinumTemperatureRegulatorSensor(
            coordinator, 100, self._wtp_regulator_description("temperature"), "test_entry"
        )

        attrs = entity.extra_state_attributes
        assert attrs["system_mode"] == "heating"
        assert attrs["target_temperature_mode"] == "constant"
        assert attrs["mode_mutable"] is True
        assert attrs["parent_id"] == 10

    def test_regulator_immutable_shows_attribute(self):
        """Temperature regulator with mode_mutable=false shows attribute."""
        device = dict(FIXTURES["wtp_temperature_regulator_immutable"])
        coordinator = self._make_wtp_coordinator(102, device)
        entity = SinumTemperatureRegulatorSensor(
            coordinator, 102, self._wtp_regulator_description("temperature"), "test_entry"
        )

        attrs = entity.extra_state_attributes
        assert attrs["mode_mutable"] is False

    def test_regulator_partial_handles_missing_fields(self):
        """Temperature regulator with no fields (partial) returns None for all sensors."""
        device = dict(FIXTURES["wtp_temperature_regulator_partial"])
        coordinator = self._make_wtp_coordinator(101, device)
        entity = SinumTemperatureRegulatorSensor(
            coordinator, 101, self._wtp_regulator_description("temperature"), "test_entry"
        )

        assert entity.native_value is None

        # Attributes should only include fields that exist
        attrs = entity.extra_state_attributes
        assert len(attrs) == 0  # No mode, parent_id, etc. in partial device
