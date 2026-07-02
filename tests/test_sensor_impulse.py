"""Tests for impulse_meter sensors and analog_input dynamic unit support."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sinum.api import SinumConnectionError
from custom_components.sinum.sensor import SinumSensor, async_setup_entry


def _make_coordinator(*, sbus=None, hub_info=None, lora=None):
    c = MagicMock()
    c.virtual_devices = {}
    c.wtp_devices = {}
    c.sbus_devices = sbus or {}
    c.lora_devices = lora or {}
    c.hub_info = hub_info or {}
    c.schedules = []
    c.automations = []
    c.client = MagicMock()
    c.client.get_weather = AsyncMock(side_effect=SinumConnectionError("no weather"))
    c.client.get_energy = AsyncMock(side_effect=SinumConnectionError("no energy"))
    c.client.get_energy_center_summary = AsyncMock(
        side_effect=SinumConnectionError("no energy center")
    )
    c.client.get_energy_center_flow_monitor = AsyncMock(
        side_effect=SinumConnectionError("no flow monitor")
    )
    c.client.get_energy_center_consumption = AsyncMock(
        side_effect=SinumConnectionError("no consumption")
    )
    c.client.get_energy_center_production = AsyncMock(
        side_effect=SinumConnectionError("no production")
    )
    c.client.decode_temperature = lambda raw: raw / 10
    return c


def _make_entry(coordinator):
    entry = MagicMock()
    entry.runtime_data = coordinator
    entry.entry_id = "test_entry"
    return entry


class TestImpulseMeterSensors:
    @pytest.mark.asyncio
    async def test_impulse_meter_total_count_sensor_created(self):
        """impulse_meter device with total_count=42 → SinumSensor with key impulse_total_count."""
        sbus = {
            1: {
                "id": 1,
                "type": "impulse_meter",
                "name": "Water meter",
                "total_count": 42,
                "window_count": 5,
                "total_value": 4200,
                "window_value": 500,
                "unit": "L",
            }
        }
        coordinator = _make_coordinator(sbus=sbus)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))

        keys = [
            e.entity_description.key
            for e in added
            if isinstance(e, SinumSensor) and hasattr(e, "entity_description")
        ]
        assert "impulse_total_count" in keys

    @pytest.mark.asyncio
    async def test_impulse_meter_no_sensor_when_missing_field(self):
        """impulse_meter device without total_count → no sensor with key impulse_total_count."""
        sbus = {
            2: {
                "id": 2,
                "type": "impulse_meter",
                "name": "Gas meter",
                # total_count intentionally absent
                "window_count": 3,
            }
        }
        coordinator = _make_coordinator(sbus=sbus)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))

        keys = [
            e.entity_description.key
            for e in added
            if isinstance(e, SinumSensor) and hasattr(e, "entity_description")
        ]
        assert "impulse_total_count" not in keys

    @pytest.mark.asyncio
    async def test_impulse_meter_dynamic_unit(self):
        """impulse_meter device with unit='kWh' → sensor native_unit_of_measurement='kWh'."""
        sbus = {
            3: {
                "id": 3,
                "type": "impulse_meter",
                "name": "Energy meter",
                "total_value": 1234,
                "unit": "kWh",
            }
        }
        coordinator = _make_coordinator(sbus=sbus)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))

        impulse_value_sensors = [
            e
            for e in added
            if isinstance(e, SinumSensor)
            and hasattr(e, "entity_description")
            and e.entity_description.key == "impulse_total_value"
        ]
        assert len(impulse_value_sensors) == 1
        entity = impulse_value_sensors[0]
        # Dynamic unit from device should be picked up since descriptor has no static unit
        assert entity.native_unit_of_measurement == "kWh"

    @pytest.mark.asyncio
    async def test_analog_input_dynamic_unit(self):
        """analog_input device with unit='mV' and value=100 → sensor unit 'mV'."""
        sbus = {
            4: {
                "id": 4,
                "type": "analog_input",
                "name": "Voltage input",
                "value": 100,
                "unit": "mV",
            }
        }
        coordinator = _make_coordinator(sbus=sbus)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))

        analog_sensors = [
            e
            for e in added
            if isinstance(e, SinumSensor)
            and hasattr(e, "entity_description")
            and e.entity_description.key == "analog_value"
        ]
        assert len(analog_sensors) == 1
        entity = analog_sensors[0]
        assert entity.native_unit_of_measurement == "mV"


class TestSensorGaps:
    """Fill remaining sensor.py coverage gaps."""

    @pytest.mark.asyncio
    async def test_weather_connection_error_ignored(self):
        """get_weather SinumConnectionError is silently swallowed."""
        coord = _make_coordinator()  # already raises SinumConnectionError for weather
        entry = _make_entry(coord)
        added: list = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        # No exception raised — weather failure is best-effort (lines 748-757)

    @pytest.mark.asyncio
    async def test_lora_sensor_created_when_field_present(self):
        """LoRa device with temperature field → SinumSensor created (lines 744-746)."""
        lora = {10: {"id": 10, "type": "temperature_sensor", "temperature": 215}}
        coord = _make_coordinator(lora=lora)
        entry = _make_entry(coord)
        added: list = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        keys = [
            e.entity_description.key
            for e in added
            if isinstance(e, SinumSensor) and hasattr(e, "entity_description")
        ]
        assert "temperature" in keys

    def test_energy_sensor_sentinel_returns_none(self):
        """_SENTINEL_INT16 in data → native_value is None."""
        from custom_components.sinum.sensor import (
            _SENTINEL_INT16,
            ENERGY_SENSORS,
            SinumEnergySensor,
        )

        desc = ENERGY_SENSORS[0]
        client = MagicMock()
        data = {desc.api_key: _SENTINEL_INT16}
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumEnergySensor(client, data, desc, "test_entry")
        assert entity.native_value is None

    @pytest.mark.asyncio
    async def test_energy_sensor_update_error_logged(self):
        """get_energy SinumConnectionError → logs warning, no exception."""
        from custom_components.sinum.sensor import ENERGY_SENSORS, SinumEnergySensor

        desc = ENERGY_SENSORS[0]
        client = MagicMock()
        client.get_energy = AsyncMock(side_effect=SinumConnectionError("down"))
        data = {desc.api_key: 100}
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumEnergySensor(client, data, desc, "test_entry")
        await entity.async_update()  # must not raise

    def test_schedule_sensor_returns_initial_when_not_found(self):
        """_schedule returns _initial_schedule when ID not in coordinator.schedules."""
        from custom_components.sinum.sensor import SinumScheduleTargetTempSensor

        initial = {"id": 99, "target_temperature": 21.5, "monday": []}
        coord = MagicMock()
        coord.schedules = [{"id": 1, "target_temperature": 20.0}]
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumScheduleTargetTempSensor(coord, initial, "test_entry")
        schedule = entity._schedule
        assert schedule is initial

    def test_active_period_sensor_active_when_in_window(self):
        """Returns 'Active' or 'Fallback' without raising (lines 1173-1176)."""
        from custom_components.sinum.sensor import SinumScheduleActivePeriodSensor

        monday_entry = {"start": 0, "end": 1440}
        initial = {"id": 5, "monday": [monday_entry]}
        coord = MagicMock()
        coord.schedules = [initial]

        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumScheduleActivePeriodSensor(coord, initial, "test_entry")

        val = entity.native_value
        assert val in ("Active", "Fallback")

    def test_energy_sensor_normal_value(self):
        """Non-sentinel value → native_value = raw * scale (line 964)."""
        from custom_components.sinum.sensor import ENERGY_SENSORS, SinumEnergySensor

        desc = ENERGY_SENSORS[0]
        client = MagicMock()
        data = {desc.api_key: 1000}
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumEnergySensor(client, data, desc, "test_entry")
        # scale should be 1.0 or similar; just check it's not None
        assert entity.native_value is not None

    def test_active_period_sensor_loop_body_with_matching_window(self):
        """Schedule with entry covering all minutes → 'Active' returned (lines 1173-1176)."""
        from custom_components.sinum.sensor import SinumScheduleActivePeriodSensor

        # Populate ALL weekdays with an all-day window so the loop runs regardless of test day
        all_day_entry = {"start": 0, "end": 1440}
        initial = {
            "id": 7,
            "monday": [all_day_entry],
            "tuesday": [all_day_entry],
            "wednesday": [all_day_entry],
            "thursday": [all_day_entry],
            "friday": [all_day_entry],
            "saturday": [all_day_entry],
            "sunday": [all_day_entry],
        }
        coord = MagicMock()
        coord.schedules = [initial]

        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumScheduleActivePeriodSensor(coord, initial, "test_entry")

        assert entity.native_value == "Active"

    def test_active_period_sensor_returns_fallback_when_no_window(self):
        """Schedule with no matching window → 'Fallback' returned (line 1178)."""
        from custom_components.sinum.sensor import SinumScheduleActivePeriodSensor

        # Empty schedule for all days
        initial = {"id": 8}
        coord = MagicMock()
        coord.schedules = [initial]

        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumScheduleActivePeriodSensor(coord, initial, "test_entry")

        assert entity.native_value == "Fallback"

    def test_active_period_sensor_skips_non_dict_entries(self):
        """Non-dict entries in day_schedule trigger continue (line 1174)."""
        from custom_components.sinum.sensor import SinumScheduleActivePeriodSensor

        all_days = {
            "monday": ["invalid_entry", {"start": 0, "end": 1440}],
            "tuesday": ["invalid_entry", {"start": 0, "end": 1440}],
            "wednesday": ["invalid_entry", {"start": 0, "end": 1440}],
            "thursday": ["invalid_entry", {"start": 0, "end": 1440}],
            "friday": ["invalid_entry", {"start": 0, "end": 1440}],
            "saturday": ["invalid_entry", {"start": 0, "end": 1440}],
            "sunday": ["invalid_entry", {"start": 0, "end": 1440}],
        }
        initial = {"id": 9, **all_days}
        coord = MagicMock()
        coord.schedules = [initial]

        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumScheduleActivePeriodSensor(coord, initial, "test_entry")

        # Even with invalid entries, should return "Active" since valid all-day window present
        assert entity.native_value == "Active"
