"""Tests for SinumEnergyStorageSensor and SinumEnergyStorageStatusSensor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sinum.api import SinumConnectionError, SinumNotSupportedError
from custom_components.sinum.sensor_energy_center import (
    STORAGE_SENSORS,
    SinumEnergyStorageSensor,
    SinumEnergyStorageStatusSensor,
)
from custom_components.sinum.sensor import async_setup_entry

# Live API response (after _request() unwraps "data" key):
_STORAGE_LIVE = {
    "available": False,
    "energy_charged_today": 15000,
    "energy_discharged_today": 8000,
    "power": -200,
    "state_of_charge": {"available": False, "value": 72},
    "status": "discharging",
}


def _make_storage_sensor(data=None, suffix="storage_soc", tkey="energy_storage_soc",
                         icon="mdi:battery", path=("state_of_charge", "value"),
                         device_class=None, state_class=None, unit=None):
    client = MagicMock()
    client.get_energy_center_storage = AsyncMock(return_value=data or {})
    from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
    from homeassistant.const import PERCENTAGE
    return SinumEnergyStorageSensor(
        client,
        data or {},
        "st1",
        suffix,
        tkey,
        icon,
        path,
        device_class or SensorDeviceClass.BATTERY,
        state_class or SensorStateClass.MEASUREMENT,
        unit or PERCENTAGE,
    )


def _make_status_sensor(data=None):
    client = MagicMock()
    client.get_energy_center_storage = AsyncMock(return_value=data or {})
    return SinumEnergyStorageStatusSensor(client, data or {}, "st1")


# ---------------------------------------------------------------------------
# STORAGE_SENSORS tuple
# ---------------------------------------------------------------------------

class TestStorageSensorsTuple:
    def test_has_four_entries(self):
        assert len(STORAGE_SENSORS) == 4

    def test_soc_is_first(self):
        suffix, _, _, path, _, _, _ = STORAGE_SENSORS[0]
        assert suffix == "storage_soc"
        assert path == ("state_of_charge", "value")

    def test_power_is_second(self):
        suffix, _, _, path, _, _, _ = STORAGE_SENSORS[1]
        assert suffix == "storage_power"
        assert path == ("power",)

    def test_charged_today_is_third(self):
        suffix, _, _, path, _, _, _ = STORAGE_SENSORS[2]
        assert suffix == "storage_charged_today"

    def test_discharged_today_is_fourth(self):
        suffix, _, _, path, _, _, _ = STORAGE_SENSORS[3]
        assert suffix == "storage_discharged_today"


# ---------------------------------------------------------------------------
# SinumEnergyStorageSensor
# ---------------------------------------------------------------------------

class TestSinumEnergyStorageSensor:
    def test_soc_native_value(self):
        sensor = _make_storage_sensor(_STORAGE_LIVE, path=("state_of_charge", "value"))
        assert sensor.native_value == 72.0

    def test_power_native_value(self):
        sensor = _make_storage_sensor(_STORAGE_LIVE, suffix="storage_power",
                                      tkey="energy_storage_power", path=("power",))
        assert sensor.native_value == -200.0

    def test_charged_today_native_value(self):
        sensor = _make_storage_sensor(_STORAGE_LIVE, suffix="storage_charged_today",
                                      tkey="energy_storage_charged_today",
                                      path=("energy_charged_today",))
        assert sensor.native_value == 15000.0

    def test_native_value_none_when_path_missing(self):
        sensor = _make_storage_sensor({}, path=("state_of_charge", "value"))
        assert sensor.native_value is None

    def test_extra_attributes_has_status(self):
        sensor = _make_storage_sensor(_STORAGE_LIVE, path=("state_of_charge", "value"))
        attrs = sensor.extra_state_attributes
        assert attrs.get("status") == "discharging"

    def test_extra_attributes_has_available(self):
        sensor = _make_storage_sensor(_STORAGE_LIVE, path=("state_of_charge", "value"))
        assert sensor.extra_state_attributes.get("available") is False

    def test_unique_id(self):
        sensor = _make_storage_sensor(path=("state_of_charge", "value"))
        assert sensor._attr_unique_id == "st1_energy_storage_soc"

    @pytest.mark.asyncio
    async def test_async_update_fetches_storage(self):
        sensor = _make_storage_sensor(_STORAGE_LIVE, path=("state_of_charge", "value"))
        new_data = {**_STORAGE_LIVE, "state_of_charge": {"value": 80}}
        sensor._client.get_energy_center_storage = AsyncMock(return_value=new_data)
        await sensor.async_update()
        assert sensor.native_value == 80.0

    @pytest.mark.asyncio
    async def test_async_update_keeps_data_on_error(self):
        sensor = _make_storage_sensor(_STORAGE_LIVE, path=("state_of_charge", "value"))
        sensor._client.get_energy_center_storage = AsyncMock(
            side_effect=SinumConnectionError("down")
        )
        await sensor.async_update()
        assert sensor.native_value == 72.0


# ---------------------------------------------------------------------------
# SinumEnergyStorageStatusSensor
# ---------------------------------------------------------------------------

class TestSinumEnergyStorageStatusSensor:
    def test_native_value_is_status_string(self):
        sensor = _make_status_sensor(_STORAGE_LIVE)
        assert sensor.native_value == "discharging"

    def test_native_value_none_when_absent(self):
        sensor = _make_status_sensor({})
        assert sensor.native_value is None

    def test_unique_id(self):
        sensor = _make_status_sensor()
        assert sensor._attr_unique_id == "st1_energy_storage_status"

    def test_translation_key(self):
        sensor = _make_status_sensor()
        assert sensor._attr_translation_key == "energy_storage_status"

    @pytest.mark.asyncio
    async def test_async_update(self):
        sensor = _make_status_sensor(_STORAGE_LIVE)
        sensor._client.get_energy_center_storage = AsyncMock(
            return_value={**_STORAGE_LIVE, "status": "charging"}
        )
        await sensor.async_update()
        assert sensor.native_value == "charging"

    @pytest.mark.asyncio
    async def test_async_update_on_not_supported(self):
        sensor = _make_status_sensor(_STORAGE_LIVE)
        sensor._client.get_energy_center_storage = AsyncMock(
            side_effect=SinumNotSupportedError("404")
        )
        await sensor.async_update()
        assert sensor.native_value == "discharging"


# ---------------------------------------------------------------------------
# Integration via async_setup_entry
# ---------------------------------------------------------------------------

class TestStorageSensorsSetup:
    @pytest.mark.asyncio
    async def test_storage_sensors_added_when_available(self):
        client = MagicMock()
        client.get_weather = AsyncMock(side_effect=SinumConnectionError("no"))
        client.get_energy = AsyncMock(side_effect=SinumConnectionError("no"))
        client.get_energy_center_summary = AsyncMock(side_effect=SinumConnectionError("no"))
        client.get_energy_center_flow_monitor = AsyncMock(side_effect=SinumConnectionError("no"))
        client.get_energy_center_consumption = AsyncMock(side_effect=SinumConnectionError("no"))
        client.get_energy_center_production = AsyncMock(side_effect=SinumConnectionError("no"))
        client.get_energy_center_storage = AsyncMock(return_value=_STORAGE_LIVE)
        client.decode_temperature = lambda x: x / 10

        coordinator = MagicMock()
        coordinator.virtual_devices = {}
        coordinator.wtp_devices = {}
        coordinator.sbus_devices = {}
        coordinator.lora_devices = {}
        coordinator.hub_info = {}
        coordinator.schedules = []
        coordinator.automations = []
        coordinator.client = client

        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "st1"

        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))

        storage_sensors = [e for e in added if isinstance(e, (SinumEnergyStorageSensor, SinumEnergyStorageStatusSensor))]
        assert len(storage_sensors) == 5  # 4 numeric + 1 status

    @pytest.mark.asyncio
    async def test_storage_sensors_skipped_when_unavailable(self):
        client = MagicMock()
        client.get_weather = AsyncMock(side_effect=SinumConnectionError("no"))
        client.get_energy = AsyncMock(side_effect=SinumConnectionError("no"))
        client.get_energy_center_summary = AsyncMock(side_effect=SinumConnectionError("no"))
        client.get_energy_center_flow_monitor = AsyncMock(side_effect=SinumConnectionError("no"))
        client.get_energy_center_consumption = AsyncMock(side_effect=SinumConnectionError("no"))
        client.get_energy_center_production = AsyncMock(side_effect=SinumConnectionError("no"))
        client.get_energy_center_storage = AsyncMock(side_effect=SinumNotSupportedError("404"))
        client.decode_temperature = lambda x: x / 10

        coordinator = MagicMock()
        coordinator.virtual_devices = {}
        coordinator.wtp_devices = {}
        coordinator.sbus_devices = {}
        coordinator.lora_devices = {}
        coordinator.hub_info = {}
        coordinator.schedules = []
        coordinator.automations = []
        coordinator.client = client

        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "st1"

        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))

        storage_sensors = [e for e in added if isinstance(e, (SinumEnergyStorageSensor, SinumEnergyStorageStatusSensor))]
        assert len(storage_sensors) == 0
