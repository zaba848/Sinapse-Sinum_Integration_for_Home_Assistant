"""Tests for Sinum sensor entities."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
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
    _add_schedule_sensors,
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

    def test_regulator_temperature_zero_returns_none(self):
        """Hub sends temperature: 0 when no physical sensor — must show unavailable, not 0.0°C."""
        device = {**FIXTURES["wtp_temperature_regulator_full"], "temperature": 0}
        coordinator = self._make_wtp_coordinator(100, device)
        entity = SinumTemperatureRegulatorSensor(
            coordinator, 100, self._wtp_regulator_description("temperature"), "test_entry"
        )

        assert entity.native_value is None

    def test_target_temperature_mode_passthrough_for_non_dict(self):
        assert SinumTemperatureRegulatorSensor._target_temperature_mode("constant") == "constant"


class TestCountItems:
    """Lines 292, 294-298, 301: _count_items helper edge cases."""

    def test_none_returns_zero(self):
        from custom_components.sinum.sensor_virtual import _count_items

        assert _count_items(None) == 0

    def test_empty_dict_returns_zero(self):
        from custom_components.sinum.sensor_virtual import _count_items

        assert _count_items({}) == 0

    def test_flat_dict_returns_len(self):
        from custom_components.sinum.sensor_virtual import _count_items

        assert _count_items({"a": 1, "b": 2}) == 2

    def test_nested_dict_sums_recursively(self):
        """Lines 296-298: nested dict/list values trigger recursive sum."""
        from custom_components.sinum.sensor_virtual import _count_items

        assert _count_items({"a": [1, 2, 3], "b": [4, 5]}) == 5

    def test_list_returns_len(self):
        """Line 301: list/tuple/set returns len."""
        from custom_components.sinum.sensor_virtual import _count_items

        assert _count_items([1, 2, 3]) == 3
        assert _count_items(("a", "b")) == 2
        assert _count_items({"x", "y", "z"}) == 3

    def test_scalar_returns_one(self):
        from custom_components.sinum.sensor_virtual import _count_items

        assert _count_items(42) == 1
        assert _count_items("hello") == 1


class TestThermostatOutputGroupSensor:
    """Lines 342, 346-353: SinumThermostatOutputGroupSensor extra_state_attributes."""

    def _make(self):
        from unittest.mock import MagicMock, patch

        from custom_components.sinum.sensor_virtual import SinumThermostatOutputGroupSensor

        coord = MagicMock()
        coord.virtual_devices = {
            5: {
                "id": 5,
                "type": "thermostat_output_group",
                "name": "Group A",
                "room_id": 2,
                "state": True,
                "enabled": True,
                "mode": "auto",
                "class": "virtual",
                "source": "api",
                "zones": [1, 2, 3],
            }
        }
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumThermostatOutputGroupSensor(coord, 5, "e")
        return entity

    def test_extra_state_attributes_includes_all_keys(self):
        entity = self._make()
        attrs = entity.extra_state_attributes
        assert attrs["device_id"] == 5
        assert attrs["name"] == "Group A"
        assert attrs["state"] is True
        assert attrs["mode"] == "auto"

    def test_native_value_counts_list_from_output_key(self):
        entity = self._make()
        # "outputs" is a valid _OUTPUT_GROUP_KEYS key — list of 3 items
        entity.coordinator.virtual_devices = {
            5: {
                "id": 5,
                "type": "thermostat_output_group",
                "name": "Group A",
                "outputs": [1, 2, 3],
            }
        }
        assert entity.native_value == 3


class TestAutomationStatusSensor:
    """Lines 387, 395-396, 400-404: SinumAutomationStatusSensor properties."""

    def _make(self, automation):
        from unittest.mock import MagicMock, patch

        from custom_components.sinum.sensor_virtual import SinumAutomationStatusSensor

        coord = MagicMock()
        coord.automations = [automation]
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumAutomationStatusSensor(coord, automation, "e")
        return entity

    def test_native_value_enabled_true(self):
        entity = self._make({"id": 1, "enabled": True, "name": "auto1"})
        assert entity.native_value == "enabled"

    def test_native_value_enabled_false(self):
        entity = self._make({"id": 1, "enabled": False})
        assert entity.native_value == "disabled"

    def test_native_value_state_string_fallback(self):
        """Line 400: state/status string fallback."""
        entity = self._make({"id": 1, "state": "running"})
        assert entity.native_value == "running"

    def test_native_value_unknown_when_nothing(self):
        entity = self._make({"id": 1})
        assert entity.native_value == "unknown"

    def test_extra_state_attributes_includes_name_and_tags(self):
        """Lines 401-404: extra_state_attributes includes known keys."""
        entity = self._make({"id": 1, "name": "auto1", "tags": ["heat"]})
        attrs = entity.extra_state_attributes
        assert attrs["automation_id"] == 1  # stored as raw int
        assert attrs["name"] == "auto1"
        assert attrs["tags"] == ["heat"]

    def test_automation_property_falls_back_to_initial_when_runtime_list_missing_entry(self):
        """Line 387: _automation returns the initial payload when coordinator list no longer contains id."""
        entity = self._make({"id": 1, "state": "idle"})
        entity.coordinator.automations = [{"id": 2, "state": "running"}]

        assert entity._automation == {"id": 1, "state": "idle"}


class TestEnergyCenterStatusSensor:
    """Lines 434, 440-443: SinumEnergyCenterStatusSensor extra attrs + async_update."""

    def _make(self, data=None):
        from unittest.mock import AsyncMock, MagicMock

        from custom_components.sinum.sensor_energy_center import SinumEnergyCenterStatusSensor

        client = MagicMock()
        client.get_energy_center_summary = AsyncMock(
            return_value=data
            or {
                "available_endpoints": ["prices", "storage"],
                "missing_endpoints": ["consumption"],
            }
        )
        entity = SinumEnergyCenterStatusSensor(
            client,
            data
            or {
                "available_endpoints": ["prices", "storage"],
                "missing_endpoints": ["consumption"],
            },
            "e",
        )
        entity._client = client
        return entity

    def test_native_value_counts_available_endpoints(self):
        entity = self._make()
        assert entity.native_value == 2

    def test_extra_state_attributes_has_available_and_missing(self):
        """Line 440-443: extra_state_attributes returns both endpoint lists."""
        entity = self._make()
        attrs = entity.extra_state_attributes
        assert "prices" in attrs["available_endpoints"]
        assert "consumption" in attrs["missing_endpoints"]

    @pytest.mark.asyncio
    async def test_async_update_refreshes_data(self):
        """Line 434: async_update fetches new data."""
        entity = self._make()
        new_data = {"available_endpoints": ["prices"], "missing_endpoints": []}
        entity._client.get_energy_center_summary = AsyncMock(return_value=new_data)
        await entity.async_update()
        assert entity.native_value == 1

    @pytest.mark.asyncio
    async def test_async_update_handles_connection_error(self):
        """Line 443: SinumConnectionError during update is swallowed."""
        from custom_components.sinum.api import SinumConnectionError

        entity = self._make()
        entity._client.get_energy_center_summary = AsyncMock(
            side_effect=SinumConnectionError("unreachable")
        )
        # Should not raise
        await entity.async_update()


class TestScheduleSensorBuilder:
    def test_add_schedule_sensors_adds_thermal_entities(self):
        coordinator = MagicMock()
        coordinator.schedules = [
            {"id": 10, "type": "thermal", "name": "Thermal 1", "target_temp": 22.5}
        ]
        entities = []

        _add_schedule_sensors(coordinator, entities, "entry")

        names = [type(entity).__name__ for entity in entities]
        assert "SinumScheduleTargetTempSensor" in names
        assert "SinumScheduleFallbackTempSensor" in names
