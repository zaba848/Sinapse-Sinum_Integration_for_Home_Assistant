"""Tests for SinumEnergyCenterFlowSensor and SinumEnergyCenterDataSensor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.sinum.api import SinumConnectionError, SinumNotSupportedError
from custom_components.sinum.sensor_virtual import (
    SinumEnergyCenterDataSensor,
    SinumEnergyCenterFlowSensor,
    _ec_first_numeric,
    _energy_center_device_info,
)
from custom_components.sinum.sensor import (
    SinumEnergyCenterFlowSensor as FlowSensorViaSetup,
    async_setup_entry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client(**overrides):
    client = MagicMock()
    client.get_weather = AsyncMock(side_effect=SinumConnectionError("no weather"))
    client.get_energy = AsyncMock(side_effect=SinumConnectionError("no energy"))
    client.get_energy_center_summary = AsyncMock(
        side_effect=SinumConnectionError("no summary")
    )
    client.get_energy_center_flow_monitor = AsyncMock(
        side_effect=SinumConnectionError("no flow")
    )
    client.get_energy_center_consumption = AsyncMock(
        side_effect=SinumConnectionError("no consumption")
    )
    client.get_energy_center_production = AsyncMock(
        side_effect=SinumConnectionError("no production")
    )
    client.decode_temperature = lambda raw: raw / 10
    for k, v in overrides.items():
        setattr(client, k, v)
    return client


def _make_coordinator(client=None):
    c = MagicMock()
    c.virtual_devices = {}
    c.wtp_devices = {}
    c.sbus_devices = {}
    c.lora_devices = {}
    c.hub_info = {}
    c.schedules = []
    c.automations = []
    c.client = client or _make_client()
    return c


def _make_entry(coordinator):
    entry = MagicMock()
    entry.runtime_data = coordinator
    entry.entry_id = "ec1"
    return entry


def _flow_sensor(data=None):
    client = MagicMock()
    client.get_energy_center_flow_monitor = AsyncMock(return_value=data or {})
    return SinumEnergyCenterFlowSensor(client, data or {}, "ec1")


def _data_sensor(data=None, suffix="consumption", tkey="energy_center_data_consumption"):
    client = MagicMock()
    getter = AsyncMock(return_value=data or {})
    sensor = SinumEnergyCenterDataSensor(
        client, data or {}, "ec1", suffix, tkey, "mdi:lightning-bolt", getter
    )
    sensor._getter = getter
    return sensor


# ---------------------------------------------------------------------------
# _ec_first_numeric
# ---------------------------------------------------------------------------

class TestEcFirstNumeric:
    def test_returns_power_field_first(self):
        assert _ec_first_numeric({"power": 123, "value": 456}) == 123.0

    def test_falls_through_to_value(self):
        assert _ec_first_numeric({"value": 10}) == 10.0

    def test_returns_none_when_no_known_field(self):
        assert _ec_first_numeric({"unknown_field": 99}) is None

    def test_returns_none_for_empty_dict(self):
        assert _ec_first_numeric({}) is None

    def test_skips_non_numeric_returns_next(self):
        assert _ec_first_numeric({"power": "n/a", "value": 42}) == 42.0

    def test_converts_to_float(self):
        result = _ec_first_numeric({"power": 5})
        assert isinstance(result, float)

    def test_total_kwh_field(self):
        assert _ec_first_numeric({"total_kwh": 9000.5}) == 9000.5


# ---------------------------------------------------------------------------
# _energy_center_device_info
# ---------------------------------------------------------------------------

class TestEnergyCenterDeviceInfo:
    def test_identifiers_use_entry_id(self):
        info = _energy_center_device_info("myentry")
        assert ("sinum", "myentry_energy") in info["identifiers"]

    def test_name_and_manufacturer(self):
        info = _energy_center_device_info("e1")
        assert info["name"] == "Sinum Energy Center"
        assert info["manufacturer"] == "TECH Sterowniki"


# ---------------------------------------------------------------------------
# SinumEnergyCenterFlowSensor
# ---------------------------------------------------------------------------

class TestEnergyCenterFlowSensor:
    def test_native_value_reads_power_field(self):
        sensor = _flow_sensor({"power": 500, "direction": "in"})
        assert sensor.native_value == 500.0

    def test_native_value_none_when_no_power(self):
        sensor = _flow_sensor({"direction": "in"})
        assert sensor.native_value is None

    def test_native_value_none_when_power_is_string(self):
        sensor = _flow_sensor({"power": "n/a"})
        assert sensor.native_value is None

    def test_extra_state_attributes_excludes_power(self):
        sensor = _flow_sensor({"power": 100, "direction": "out", "grid_id": 1})
        attrs = sensor.extra_state_attributes
        assert "power" not in attrs
        assert attrs["direction"] == "out"
        assert attrs["grid_id"] == 1

    def test_unique_id_suffix(self):
        sensor = _flow_sensor()
        assert sensor._attr_unique_id == "ec1_energy_center_flow_power"

    def test_translation_key(self):
        sensor = _flow_sensor()
        assert sensor._attr_translation_key == "energy_center_flow_power"

    @pytest.mark.asyncio
    async def test_async_update_fetches_flow_monitor(self):
        sensor = _flow_sensor({"power": 0})
        sensor._client.get_energy_center_flow_monitor = AsyncMock(return_value={"power": 750})
        await sensor.async_update()
        assert sensor._data == {"power": 750}

    @pytest.mark.asyncio
    async def test_async_update_on_connection_error_keeps_old_data(self):
        sensor = _flow_sensor({"power": 300})
        sensor._client.get_energy_center_flow_monitor = AsyncMock(
            side_effect=SinumConnectionError("down")
        )
        await sensor.async_update()
        assert sensor._data == {"power": 300}

    @pytest.mark.asyncio
    async def test_async_update_on_not_supported_keeps_old_data(self):
        sensor = _flow_sensor({"power": 200})
        sensor._client.get_energy_center_flow_monitor = AsyncMock(
            side_effect=SinumNotSupportedError("404")
        )
        await sensor.async_update()
        assert sensor._data == {"power": 200}


# ---------------------------------------------------------------------------
# SinumEnergyCenterDataSensor
# ---------------------------------------------------------------------------

class TestEnergyCenterDataSensor:
    def test_native_value_first_numeric_field(self):
        sensor = _data_sensor({"power": 1500})
        assert sensor.native_value == 1500.0

    def test_native_value_none_when_no_known_field(self):
        sensor = _data_sensor({"status": "ok"})
        assert sensor.native_value is None

    def test_extra_state_attributes_full_dict(self):
        sensor = _data_sensor({"value": 10, "today": 5})
        assert sensor.extra_state_attributes == {"value": 10, "today": 5}

    def test_unique_id_uses_suffix(self):
        sensor = _data_sensor(suffix="production", tkey="energy_center_data_production")
        assert sensor._attr_unique_id == "ec1_energy_center_production"

    def test_translation_key_set_from_param(self):
        sensor = _data_sensor(tkey="energy_center_data_consumption")
        assert sensor._attr_translation_key == "energy_center_data_consumption"

    def test_icon_set_from_param(self):
        sensor = _data_sensor()
        assert sensor._attr_icon == "mdi:lightning-bolt"

    @pytest.mark.asyncio
    async def test_async_update_calls_getter(self):
        sensor = _data_sensor({"value": 0})
        sensor._getter = AsyncMock(return_value={"value": 42})
        await sensor.async_update()
        assert sensor._data == {"value": 42}

    @pytest.mark.asyncio
    async def test_async_update_on_connection_error_keeps_data(self):
        sensor = _data_sensor({"value": 5})
        sensor._getter = AsyncMock(side_effect=SinumConnectionError("down"))
        await sensor.async_update()
        assert sensor._data == {"value": 5}

    @pytest.mark.asyncio
    async def test_async_update_on_not_supported_keeps_data(self):
        sensor = _data_sensor({"value": 5})
        sensor._getter = AsyncMock(side_effect=SinumNotSupportedError("404"))
        await sensor.async_update()
        assert sensor._data == {"value": 5}


# ---------------------------------------------------------------------------
# _try_add_energy_center_detail_sensors via async_setup_entry
# ---------------------------------------------------------------------------

class TestTryAddEnergyCenterDetailSensors:
    @pytest.mark.asyncio
    async def test_flow_sensor_added_when_endpoint_available(self):
        client = _make_client(
            get_energy_center_flow_monitor=AsyncMock(return_value={"power": 100})
        )
        coordinator = _make_coordinator(client)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        flows = [e for e in added if isinstance(e, SinumEnergyCenterFlowSensor)]
        assert len(flows) == 1
        assert flows[0].native_value == 100.0

    @pytest.mark.asyncio
    async def test_consumption_sensor_added_when_endpoint_available(self):
        client = _make_client(
            get_energy_center_consumption=AsyncMock(return_value={"value": 55})
        )
        coordinator = _make_coordinator(client)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        data_sensors = [e for e in added if isinstance(e, SinumEnergyCenterDataSensor)]
        consumption = [s for s in data_sensors if "consumption" in s._attr_unique_id]
        assert len(consumption) == 1
        assert consumption[0].native_value == 55.0

    @pytest.mark.asyncio
    async def test_production_sensor_added_when_endpoint_available(self):
        client = _make_client(
            get_energy_center_production=AsyncMock(return_value={"power": 3000})
        )
        coordinator = _make_coordinator(client)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        data_sensors = [e for e in added if isinstance(e, SinumEnergyCenterDataSensor)]
        production = [s for s in data_sensors if "production" in s._attr_unique_id]
        assert len(production) == 1
        assert production[0].native_value == 3000.0

    @pytest.mark.asyncio
    async def test_all_three_sensors_added_when_all_available(self):
        client = _make_client(
            get_energy_center_flow_monitor=AsyncMock(return_value={"power": 1}),
            get_energy_center_consumption=AsyncMock(return_value={"value": 2}),
            get_energy_center_production=AsyncMock(return_value={"value": 3}),
        )
        coordinator = _make_coordinator(client)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        flows = [e for e in added if isinstance(e, SinumEnergyCenterFlowSensor)]
        data = [e for e in added if isinstance(e, SinumEnergyCenterDataSensor)]
        assert len(flows) == 1
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_skips_unavailable_endpoints_independently(self):
        client = _make_client(
            get_energy_center_flow_monitor=AsyncMock(
                side_effect=SinumConnectionError("no flow")
            ),
            get_energy_center_consumption=AsyncMock(return_value={"value": 10}),
            get_energy_center_production=AsyncMock(
                side_effect=SinumNotSupportedError("404")
            ),
        )
        coordinator = _make_coordinator(client)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        flows = [e for e in added if isinstance(e, SinumEnergyCenterFlowSensor)]
        data = [e for e in added if isinstance(e, SinumEnergyCenterDataSensor)]
        assert len(flows) == 0
        assert len(data) == 1
        assert "consumption" in data[0]._attr_unique_id
