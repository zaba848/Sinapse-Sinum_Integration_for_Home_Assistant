"""Tests for SinumEnergyCenterFlowSensor and SinumEnergyCenterDataSensor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.sinum.api import SinumConnectionError, SinumNotSupportedError
from custom_components.sinum.sensor_energy_center import (
    SinumEnergyCenterDataSensor,
    SinumEnergyCenterFlowSensor,
    _ec_first_numeric,
    _energy_center_device_info,
)
from custom_components.sinum.sensor import (
    SinumEnergyCenterFlowSensor as FlowSensorViaSetup,
    async_setup_entry,
)

# Live API schema (after _request() unwraps the "data" key):
#
# flow-monitor → {summary: {building: {value, available}, pv: {...}, grid: {...},
#                            battery: {value, available, state_of_charge: {value}}},
#                 flow: {...}, voltage: {...}, building_consumption_details: {...}}
#
# energy-consumption → {available, today: {total_consumption, house_consumption,
#                        electrical_outlets_consumption, car_chargers_consumption},
#                        total: {same keys}}
#
# energy-production  → {available, today: {all, autoconsumption, energy_storage, grid_export},
#                        total: {same keys}}

_FLOW_LIVE = {
    "summary": {
        "building": {"available": True, "value": 422},
        "pv": {"available": False, "value": 0},
        "grid": {"available": True, "value": 10},
        "battery": {
            "available": False,
            "value": 0,
            "state_of_charge": {"available": False, "value": 55},
        },
    },
    "flow": {},
    "voltage": {"grid": {"max": None, "phases": []}},
    "building_consumption_details": {"by_devices": [], "rest": 0},
}

_CONSUMPTION_LIVE = {
    "available": True,
    "today": {
        "car_chargers_consumption": 0,
        "electrical_outlets_consumption": 3,
        "house_consumption": 0,
        "total_consumption": 3,
    },
    "total": {
        "car_chargers_consumption": 0,
        "electrical_outlets_consumption": 92181,
        "house_consumption": 0,
        "total_consumption": 92181,
    },
}

_PRODUCTION_LIVE = {
    "available": False,
    "today": {"all": 0, "autoconsumption": 0, "energy_storage": 0, "grid_export": 0},
    "total": {"all": 5000, "autoconsumption": 1000, "energy_storage": 200, "grid_export": 3800},
}


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
    client.get_energy_center_storage = AsyncMock(
        side_effect=SinumNotSupportedError("no storage")
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


def _data_sensor(
    data=None,
    suffix="consumption",
    tkey="energy_center_data_consumption",
    value_path: tuple[str, ...] = (),
):
    client = MagicMock()
    getter = AsyncMock(return_value=data or {})
    sensor = SinumEnergyCenterDataSensor(
        client, data or {}, "ec1", suffix, tkey, "mdi:lightning-bolt", getter,
        value_path=value_path,
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
    def test_native_value_reads_building_value(self):
        sensor = _flow_sensor(_FLOW_LIVE)
        assert sensor.native_value == 422.0

    def test_native_value_none_when_summary_absent(self):
        sensor = _flow_sensor({"flow": {}, "voltage": {}})
        assert sensor.native_value is None

    def test_native_value_none_when_building_absent(self):
        sensor = _flow_sensor({"summary": {"pv": {"value": 100}}})
        assert sensor.native_value is None

    def test_native_value_none_when_value_is_string(self):
        sensor = _flow_sensor({"summary": {"building": {"value": "n/a"}}})
        assert sensor.native_value is None

    def test_native_value_zero_is_valid(self):
        sensor = _flow_sensor({"summary": {"building": {"value": 0}}})
        assert sensor.native_value == 0.0

    def test_extra_state_attributes_contains_pv_grid_battery(self):
        sensor = _flow_sensor(_FLOW_LIVE)
        attrs = sensor.extra_state_attributes
        assert attrs["pv_power"] == 0
        assert attrs["grid_power"] == 10
        assert attrs["battery_power"] == 0
        assert attrs["battery_soc"] == 55

    def test_extra_state_attributes_none_for_absent_sections(self):
        sensor = _flow_sensor({"summary": {"grid": {"value": 5}}})
        attrs = sensor.extra_state_attributes
        assert attrs["grid_power"] == 5
        assert attrs["pv_power"] is None
        assert attrs["battery_power"] is None

    def test_unique_id_suffix(self):
        sensor = _flow_sensor()
        assert sensor._attr_unique_id == "ec1_energy_center_flow_power"

    def test_translation_key(self):
        sensor = _flow_sensor()
        assert sensor._attr_translation_key == "energy_center_flow_power"

    @pytest.mark.asyncio
    async def test_async_update_fetches_flow_monitor(self):
        new_data = {"summary": {"building": {"value": 750}}}
        sensor = _flow_sensor(_FLOW_LIVE)
        sensor._client.get_energy_center_flow_monitor = AsyncMock(return_value=new_data)
        await sensor.async_update()
        assert sensor._data == new_data
        assert sensor.native_value == 750.0

    @pytest.mark.asyncio
    async def test_async_update_on_connection_error_keeps_old_data(self):
        sensor = _flow_sensor(_FLOW_LIVE)
        sensor._client.get_energy_center_flow_monitor = AsyncMock(
            side_effect=SinumConnectionError("down")
        )
        await sensor.async_update()
        assert sensor._data == _FLOW_LIVE

    @pytest.mark.asyncio
    async def test_async_update_on_not_supported_keeps_old_data(self):
        sensor = _flow_sensor(_FLOW_LIVE)
        sensor._client.get_energy_center_flow_monitor = AsyncMock(
            side_effect=SinumNotSupportedError("404")
        )
        await sensor.async_update()
        assert sensor._data == _FLOW_LIVE


# ---------------------------------------------------------------------------
# SinumEnergyCenterDataSensor
# ---------------------------------------------------------------------------

class TestEnergyCenterDataSensor:
    def test_native_value_via_value_path_consumption(self):
        sensor = _data_sensor(_CONSUMPTION_LIVE, value_path=("total", "total_consumption"))
        assert sensor.native_value == 92181.0

    def test_native_value_via_value_path_production(self):
        sensor = _data_sensor(_PRODUCTION_LIVE, suffix="production",
                              tkey="energy_center_data_production",
                              value_path=("total", "all"))
        assert sensor.native_value == 5000.0

    def test_native_value_none_when_path_missing(self):
        sensor = _data_sensor({"available": True}, value_path=("total", "total_consumption"))
        assert sensor.native_value is None

    def test_native_value_none_when_path_not_dict(self):
        sensor = _data_sensor({"total": "bad"}, value_path=("total", "total_consumption"))
        assert sensor.native_value is None

    def test_native_value_fallback_to_ec_first_numeric(self):
        sensor = _data_sensor({"power": 1500})
        assert sensor.native_value == 1500.0

    def test_native_value_none_when_no_path_and_no_known_field(self):
        sensor = _data_sensor({"status": "ok"})
        assert sensor.native_value is None

    def test_extra_state_attributes_full_dict(self):
        sensor = _data_sensor(_CONSUMPTION_LIVE, value_path=("total", "total_consumption"))
        attrs = sensor.extra_state_attributes
        assert "today" in attrs
        assert "total" in attrs
        assert attrs["available"] is True

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
        sensor = _data_sensor(_CONSUMPTION_LIVE, value_path=("total", "total_consumption"))
        new_data = {**_CONSUMPTION_LIVE, "total": {"total_consumption": 99999}}
        sensor._getter = AsyncMock(return_value=new_data)
        await sensor.async_update()
        assert sensor.native_value == 99999.0

    @pytest.mark.asyncio
    async def test_async_update_on_connection_error_keeps_data(self):
        sensor = _data_sensor(_CONSUMPTION_LIVE, value_path=("total", "total_consumption"))
        sensor._getter = AsyncMock(side_effect=SinumConnectionError("down"))
        await sensor.async_update()
        assert sensor._data == _CONSUMPTION_LIVE

    @pytest.mark.asyncio
    async def test_async_update_on_not_supported_keeps_data(self):
        sensor = _data_sensor(_CONSUMPTION_LIVE, value_path=("total", "total_consumption"))
        sensor._getter = AsyncMock(side_effect=SinumNotSupportedError("404"))
        await sensor.async_update()
        assert sensor._data == _CONSUMPTION_LIVE


# ---------------------------------------------------------------------------
# _try_add_energy_center_detail_sensors via async_setup_entry
# ---------------------------------------------------------------------------

class TestTryAddEnergyCenterDetailSensors:
    @pytest.mark.asyncio
    async def test_flow_sensor_added_when_endpoint_available(self):
        client = _make_client(
            get_energy_center_flow_monitor=AsyncMock(return_value=_FLOW_LIVE)
        )
        coordinator = _make_coordinator(client)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        flows = [e for e in added if isinstance(e, SinumEnergyCenterFlowSensor)]
        assert len(flows) == 1
        assert flows[0].native_value == 422.0

    @pytest.mark.asyncio
    async def test_consumption_sensor_added_when_endpoint_available(self):
        client = _make_client(
            get_energy_center_consumption=AsyncMock(return_value=_CONSUMPTION_LIVE)
        )
        coordinator = _make_coordinator(client)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        data_sensors = [e for e in added if isinstance(e, SinumEnergyCenterDataSensor)]
        consumption = [s for s in data_sensors if "consumption" in s._attr_unique_id]
        assert len(consumption) == 1
        assert consumption[0].native_value == 92181.0

    @pytest.mark.asyncio
    async def test_production_sensor_added_when_endpoint_available(self):
        client = _make_client(
            get_energy_center_production=AsyncMock(return_value=_PRODUCTION_LIVE)
        )
        coordinator = _make_coordinator(client)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        data_sensors = [e for e in added if isinstance(e, SinumEnergyCenterDataSensor)]
        production = [s for s in data_sensors if "production" in s._attr_unique_id]
        assert len(production) == 1
        assert production[0].native_value == 5000.0

    @pytest.mark.asyncio
    async def test_all_three_sensors_added_when_all_available(self):
        client = _make_client(
            get_energy_center_flow_monitor=AsyncMock(return_value=_FLOW_LIVE),
            get_energy_center_consumption=AsyncMock(return_value=_CONSUMPTION_LIVE),
            get_energy_center_production=AsyncMock(return_value=_PRODUCTION_LIVE),
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
            get_energy_center_consumption=AsyncMock(return_value=_CONSUMPTION_LIVE),
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
