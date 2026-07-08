"""Tests for sensor async_setup_entry and entity class coverage."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sinum.api import SinumConnectionError, SinumNotSupportedError
from custom_components.sinum.const import STYPE_BUTTON, WTYPE_BUTTON
from custom_components.sinum.sensor import (
    ENERGY_SENSORS,
    SBUS_REGULATOR_SENSORS,
    SBUS_SENSORS,
    VIRTUAL_SENSORS,
    WEATHER_SENSORS,
    WTP_SENSORS,
    SinumAutomationStatusSensor,
    SinumButtonSensor,
    SinumEnergyCenterStatusSensor,
    SinumEnergySensor,
    SinumHubUptimeSensor,
    SinumHubWifiSensor,
    SinumScheduleActivePeriodSensor,
    SinumScheduleAssociationCountSensor,
    SinumSensor,
    SinumTemperatureRegulatorSensor,
    SinumThermostatOutputGroupSensor,
    SinumWeatherSensor,
    async_setup_entry,
)
from custom_components.sinum.sensor_bus import SinumSensorDescription


def _make_coordinator(
    *,
    virtual=None,
    wtp=None,
    sbus=None,
    lora=None,
    hub_info=None,
    schedules=None,
    automations=None,
):
    c = MagicMock()
    c.virtual_devices = virtual or {}
    c.wtp_devices = wtp or {}
    c.sbus_devices = sbus or {}
    c.lora_devices = lora or {}
    c.hub_info = hub_info or {}
    c.schedules = schedules or []
    c.automations = automations or []
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
    c.client.get_energy_center_storage = AsyncMock(
        side_effect=SinumNotSupportedError("no storage")
    )
    c.client.decode_temperature = lambda raw: raw / 10
    return c


def _make_entry(coordinator):
    entry = MagicMock()
    entry.runtime_data = coordinator
    entry.entry_id = "test_entry"
    return entry


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_virtual_sensor_with_api_key_creates_entity(self):
        # Use first VIRTUAL_SENSORS descriptor's api_key
        desc = next((d for d in VIRTUAL_SENSORS if d.source == "virtual"), None)
        assert desc is not None
        virtual = {1: {"id": 1, "type": "thermostat", "name": "T", desc.api_key: 220}}
        coordinator = _make_coordinator(virtual=virtual)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        sensors = [e for e in added if isinstance(e, SinumSensor) and e._source == "virtual"]
        assert len(sensors) >= 1

    @pytest.mark.asyncio
    async def test_thermostat_output_group_creates_diagnostic_sensor(self):
        virtual = {
            9: {
                "id": 9,
                "type": "thermostat_output_group",
                "name": "Heating outputs",
                "outputs": [{"id": 1}, {"id": 2}],
            }
        }
        coordinator = _make_coordinator(virtual=virtual)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        groups = [e for e in added if isinstance(e, SinumThermostatOutputGroupSensor)]
        assert len(groups) == 1
        assert groups[0].native_value == 2

    @pytest.mark.asyncio
    async def test_wtp_generic_sensor_created(self):
        desc = next((d for d in WTP_SENSORS if d.source == "wtp"), None)
        assert desc is not None
        wtp = {2: {"id": 2, "type": "temperature_sensor", "name": "Sensor", desc.api_key: 215}}
        coordinator = _make_coordinator(wtp=wtp)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        sensors = [e for e in added if isinstance(e, SinumSensor)]
        assert len(sensors) >= 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("device_type", "api_key", "raw_value", "expected_native"),
        [
            ("co2_sensor", "co2", 550, 550),
            ("pressure_sensor", "pressure", 10123, 1012.3),
            ("iaq_sensor", "iaq", 42, 42),
            ("aq_sensor", "air_quality", "good", "good"),
            ("air_quality_sensor", "pm2p5", 12, 12),
        ],
    )
    async def test_wtp_specific_sensor_types_create_expected_entities(
        self, device_type, api_key, raw_value, expected_native
    ):
        desc = next(
            (d for d in WTP_SENSORS if d.source == "wtp" and d.api_key == api_key),
            None,
        )
        assert desc is not None

        wtp = {
            200: {
                "id": 200,
                "type": device_type,
                "name": f"WTP {device_type}",
                api_key: raw_value,
            }
        }
        coordinator = _make_coordinator(wtp=wtp)
        entry = _make_entry(coordinator)
        added = []

        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))

        matching = [
            e
            for e in added
            if isinstance(e, SinumSensor)
            and getattr(e, "_source", None) == "wtp"
            and e.entity_description.api_key == api_key
        ]

        assert len(matching) == 1
        if isinstance(expected_native, float):
            assert matching[0].native_value == pytest.approx(expected_native)
        else:
            assert matching[0].native_value == expected_native

    @pytest.mark.asyncio
    async def test_wtp_regulator_creates_regulator_sensor(self):
        desc = next((d for d in WTP_SENSORS if d.source == "wtp_regulator"), None)
        assert desc is not None
        wtp = {3: {"id": 3, "type": "temperature_regulator", "name": "Reg", desc.api_key: 210}}
        coordinator = _make_coordinator(wtp=wtp)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        regulators = [e for e in added if isinstance(e, SinumTemperatureRegulatorSensor)]
        assert len(regulators) >= 1

    @pytest.mark.asyncio
    async def test_wtp_button_creates_button_sensor(self):
        wtp = {4: {"id": 4, "type": WTYPE_BUTTON, "name": "Btn", "action": "press"}}
        coordinator = _make_coordinator(wtp=wtp)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        buttons = [e for e in added if isinstance(e, SinumButtonSensor)]
        assert len(buttons) == 1
        assert buttons[0]._bus == "wtp"

    @pytest.mark.asyncio
    async def test_sbus_sensor_created(self):
        desc = next((d for d in SBUS_SENSORS if d.source == "sbus"), None)
        assert desc is not None
        sbus = {5: {"id": 5, "type": "temperature_sensor", "name": "T", desc.api_key: 200}}
        coordinator = _make_coordinator(sbus=sbus)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        sensors = [e for e in added if isinstance(e, SinumSensor) and e._source == "sbus"]
        assert len(sensors) >= 1

    @pytest.mark.asyncio
    async def test_sbus_button_creates_button_sensor(self):
        sbus = {6: {"id": 6, "type": STYPE_BUTTON, "name": "Btn", "action": "1"}}
        coordinator = _make_coordinator(sbus=sbus)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        buttons = [e for e in added if isinstance(e, SinumButtonSensor)]
        assert len(buttons) == 1
        assert buttons[0]._bus == "sbus"

    @pytest.mark.asyncio
    async def test_sbus_regulator_sensor_created(self):
        desc = next((d for d in SBUS_REGULATOR_SENSORS), None)
        assert desc is not None
        sbus = {7: {"id": 7, "type": "temperature_regulator", "name": "Reg", desc.api_key: 210}}
        coordinator = _make_coordinator(sbus=sbus)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        regulators = [e for e in added if isinstance(e, SinumTemperatureRegulatorSensor)]
        assert len(regulators) >= 1

    @pytest.mark.asyncio
    async def test_weather_unavailable_skipped(self):
        coordinator = _make_coordinator()
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        weather = [e for e in added if isinstance(e, SinumWeatherSensor)]
        assert len(weather) == 0

    @pytest.mark.asyncio
    async def test_weather_available_creates_sensors(self):
        weather_data = {}
        for desc in WEATHER_SENSORS:
            weather_data[desc.api_key] = 100
        coordinator = _make_coordinator()
        coordinator.client.get_weather = AsyncMock(return_value=weather_data)
        coordinator.client.get_energy = AsyncMock(side_effect=SinumConnectionError("no energy"))
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        weather = [e for e in added if isinstance(e, SinumWeatherSensor)]
        assert len(weather) >= 1

    @pytest.mark.asyncio
    async def test_energy_available_creates_sensors(self):
        energy_data = {}
        for desc in ENERGY_SENSORS:
            energy_data[desc.api_key] = 500
        coordinator = _make_coordinator()
        coordinator.client.get_weather = AsyncMock(side_effect=SinumConnectionError("no weather"))
        coordinator.client.get_energy = AsyncMock(return_value=energy_data)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        energy = [e for e in added if isinstance(e, SinumEnergySensor)]
        assert len(energy) >= 1

    @pytest.mark.asyncio
    async def test_energy_center_summary_creates_status_sensor(self):
        coordinator = _make_coordinator()
        coordinator.client.get_energy_center_summary = AsyncMock(
            return_value={
                "available_endpoints": ["associations", "prices"],
                "missing_endpoints": ["flow_monitor"],
            }
        )
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        statuses = [e for e in added if isinstance(e, SinumEnergyCenterStatusSensor)]
        assert len(statuses) == 1
        assert statuses[0].native_value == 2

    @pytest.mark.asyncio
    async def test_hub_uptime_sensor_created_when_hub_info_present(self):
        coordinator = _make_coordinator(hub_info={"uptime": 12345, "firmware": "1.24.0"})
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        uptime = [e for e in added if isinstance(e, SinumHubUptimeSensor)]
        assert len(uptime) == 1

    @pytest.mark.asyncio
    async def test_hub_firmware_sensor_created_when_version_present(self):
        coordinator = _make_coordinator(hub_info={"uptime": 100, "version": "1.24.0-alpha.4"})
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        from custom_components.sinum.sensor_hub import SinumHubFirmwareSensor
        fw = [e for e in added if isinstance(e, SinumHubFirmwareSensor)]
        assert len(fw) == 1
        assert fw[0].native_value == "1.24.0-alpha.4"

    @pytest.mark.asyncio
    async def test_hub_firmware_sensor_value_is_none_when_no_version(self):
        from custom_components.sinum.sensor_hub import SinumHubFirmwareSensor
        coordinator = _make_coordinator(hub_info={"uptime": 100})
        s = SinumHubFirmwareSensor(coordinator, "entry")
        assert s.native_value is None

    @pytest.mark.asyncio
    async def test_hub_firmware_sensor_extra_attrs(self):
        from custom_components.sinum.sensor_hub import SinumHubFirmwareSensor
        coordinator = _make_coordinator(
            hub_info={"uptime": 100, "version": "1.24.0", "device_type": "sinum_plus", "api": "1.4"}
        )
        s = SinumHubFirmwareSensor(coordinator, "entry")
        assert s.extra_state_attributes == {"device_type": "sinum_plus", "api_version": "1.4"}

    @pytest.mark.asyncio
    async def test_hub_wifi_sensor_created_when_signal_present(self):
        coordinator = _make_coordinator(
            hub_info={"uptime": 100, "wifi": {"signal": -65, "ssid": "Home"}}
        )
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        wifi = [e for e in added if isinstance(e, SinumHubWifiSensor)]
        assert len(wifi) == 1

    @pytest.mark.asyncio
    async def test_hub_wifi_sensor_not_created_when_no_signal(self):
        coordinator = _make_coordinator(hub_info={"uptime": 100})
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        wifi = [e for e in added if isinstance(e, SinumHubWifiSensor)]
        assert len(wifi) == 0

    @pytest.mark.asyncio
    async def test_energy_404_does_not_crash_platform(self):
        """Regression: SinumNotSupportedError (404) from optional endpoints must not
        propagate — the sensor platform was crashing silently on hubs without /energy."""
        coordinator = _make_coordinator()
        coordinator.client.get_energy = AsyncMock(
            side_effect=SinumNotSupportedError("Endpoint not found on this hub: /api/v1/energy")
        )
        coordinator.client.get_weather = AsyncMock(
            side_effect=SinumNotSupportedError("Endpoint not found")
        )
        coordinator.client.get_energy_center_summary = AsyncMock(
            side_effect=SinumNotSupportedError("Endpoint not found")
        )
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        # Platform must not raise; some entities are created (virtual/wtp/sbus are empty in
        # _make_coordinator default, so total may be 0 — the key is no exception).

    @pytest.mark.asyncio
    async def test_schedule_sensors_created(self):
        schedules = [{"id": 1, "name": "Morning", "target_temperature": 210}]
        coordinator = _make_coordinator(schedules=schedules)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        sched_sensors = [
            e
            for e in added
            if isinstance(e, (SinumScheduleAssociationCountSensor, SinumScheduleActivePeriodSensor))
        ]
        assert len(sched_sensors) == 2

    @pytest.mark.asyncio
    async def test_schedule_without_id_skipped(self):
        schedules = [{"name": "NoId"}]
        coordinator = _make_coordinator(schedules=schedules)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        assert len(added) == 0

    @pytest.mark.asyncio
    async def test_automation_status_sensor_created(self):
        automations = [{"id": 3, "name": "Evening", "enabled": True}]
        coordinator = _make_coordinator(automations=automations)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        statuses = [e for e in added if isinstance(e, SinumAutomationStatusSensor)]
        assert len(statuses) == 1
        assert statuses[0].native_value == "enabled"


class TestSinumSensorNativeValue:
    def _make(self, api_key: str, value):
        desc = next(d for d in WTP_SENSORS if d.source == "wtp" and not d.is_text)
        coordinator = MagicMock()
        coordinator.wtp_devices = {
            1: {"id": 1, "type": "temperature_sensor", "name": "T", desc.api_key: value}
        }
        return SinumSensor(coordinator, 1, desc, "test_entry"), desc

    def test_text_value_returns_str(self):
        desc = next((d for d in WTP_SENSORS if d.is_text), None)
        if desc is None:
            pytest.skip("No text descriptor found")
        coordinator = MagicMock()
        coordinator.wtp_devices = {
            1: {"id": 1, "type": "something", "name": "T", desc.api_key: "active"}
        }
        entity = SinumSensor(coordinator, 1, desc, "test_entry")
        assert entity.native_value == "active"

    def test_non_numeric_returns_none(self):
        desc = next(d for d in WTP_SENSORS if d.source == "wtp" and not d.is_text)
        coordinator = MagicMock()
        coordinator.wtp_devices = {1: {"id": 1, "name": "T", desc.api_key: "bad"}}
        entity = SinumSensor(coordinator, 1, desc, "test_entry")
        assert entity.native_value is None

    def test_unknown_bus_source_returns_empty_device_dict(self):
        coordinator = MagicMock()
        desc = SinumSensorDescription(
            key="temperature",
            api_key="temperature",
            source="unknown_bus",
        )
        entity = SinumSensor(coordinator, 1, desc, "test_entry")
        assert entity._device == {}

    def test_sentinel_returns_none(self):
        desc = next(d for d in WTP_SENSORS if d.source == "wtp" and not d.is_text)
        coordinator = MagicMock()
        coordinator.wtp_devices = {1: {"id": 1, "name": "T", desc.api_key: -32768}}
        entity = SinumSensor(coordinator, 1, desc, "test_entry")
        assert entity.native_value is None

    def test_zero_is_unavailable_returns_none(self):
        """Virtual thermostat temperature=0 (no sensor) should map to None."""
        from custom_components.sinum.sensor_virtual import VIRTUAL_SENSORS

        desc = next(d for d in VIRTUAL_SENSORS if d.api_key == "temperature")
        assert desc.zero_is_unavailable is True
        coordinator = MagicMock()
        coordinator.virtual_devices = {
            1: {"id": 1, "type": "thermostat", "name": "T", "temperature": 0}
        }
        coordinator.wtp_devices = {}
        entity = SinumSensor(coordinator, 1, desc, "test_entry")
        assert entity.native_value is None

    def test_zero_is_unavailable_false_allows_zero_when_online(self):
        """Online sensor with raw=0 and zero_is_unavailable=False should return 0.0."""
        desc = next(d for d in WTP_SENSORS if d.source == "wtp" and not d.is_text)
        assert desc.zero_is_unavailable is False
        coordinator = MagicMock()
        coordinator.wtp_devices = {1: {"id": 1, "name": "T", "status": "online", desc.api_key: 0}}
        entity = SinumSensor(coordinator, 1, desc, "test_entry")
        assert entity.native_value == 0.0

    def test_offline_sensor_with_zero_returns_none(self):
        """Offline sensor with raw=0 should return None (disconnected probe)."""
        desc = next(d for d in WTP_SENSORS if d.source == "wtp" and not d.is_text)
        coordinator = MagicMock()
        coordinator.wtp_devices = {1: {"id": 1, "name": "T", "status": "offline", desc.api_key: 0}}
        entity = SinumSensor(coordinator, 1, desc, "test_entry")
        assert entity.native_value is None

    def test_sbus_source_reads_sbus_store(self):
        desc = next(d for d in SBUS_SENSORS if d.source == "sbus")
        coordinator = MagicMock()
        coordinator.sbus_devices = {10: {"id": 10, "name": "T", desc.api_key: 200}}
        coordinator.wtp_devices = {}
        entity = SinumSensor(coordinator, 10, desc, "test_entry")
        assert entity.native_value == pytest.approx(200 * desc.scale)


class TestSinumWeatherSensor:
    def test_native_value(self):
        desc = WEATHER_SENSORS[0]
        client = MagicMock()
        data = {desc.api_key: 220}
        entity = SinumWeatherSensor(client, data, desc, "entry")
        assert entity.native_value == pytest.approx(220 * desc.scale)

    def test_sentinel_returns_none(self):
        desc = WEATHER_SENSORS[0]
        client = MagicMock()
        data = {desc.api_key: -32768}
        entity = SinumWeatherSensor(client, data, desc, "entry")
        assert entity.native_value is None

    @pytest.mark.asyncio
    async def test_async_update_refreshes_data(self):
        desc = WEATHER_SENSORS[0]
        client = MagicMock()
        client.get_weather = AsyncMock(return_value={desc.api_key: 300})
        entity = SinumWeatherSensor(client, {desc.api_key: 200}, desc, "entry")
        await entity.async_update()
        assert entity._data[desc.api_key] == 300

    @pytest.mark.asyncio
    async def test_async_update_connection_error_silenced(self):
        desc = WEATHER_SENSORS[0]
        client = MagicMock()
        client.get_weather = AsyncMock(side_effect=SinumConnectionError("fail"))
        entity = SinumWeatherSensor(client, {desc.api_key: 200}, desc, "entry")
        await entity.async_update()  # Should not raise


class TestSinumHubSensors:
    def test_uptime_sensor_value(self):
        coordinator = MagicMock()
        coordinator.hub_info = {"uptime": 99999}
        entity = SinumHubUptimeSensor(coordinator, "entry")
        assert entity.native_value == 99999

    def test_wifi_sensor_signal(self):
        coordinator = MagicMock()
        coordinator.hub_info = {"wifi": {"signal": -72, "ssid": "HomeNet", "ip": "192.168.1.1"}}
        entity = SinumHubWifiSensor(coordinator, "entry")
        assert entity.native_value == -72
        attrs = entity.extra_state_attributes
        assert attrs["ssid"] == "HomeNet"
        assert attrs["ip"] == "192.168.1.1"


class TestSinumScheduleAssociationCountSensor:
    def test_native_value_counts_thermostats_and_fan_coils(self):
        schedule = {
            "id": 1,
            "name": "Test",
            "associations": {
                "thermostats": [{"id": 1}, {"id": 2}],
                "fan_coils": [{"id": 3}],
            },
        }
        coordinator = MagicMock()
        coordinator.schedules = [schedule]
        entity = SinumScheduleAssociationCountSensor(coordinator, schedule, "entry")
        assert entity.native_value == 3

    def test_extra_state_attributes(self):
        schedule = {
            "id": 2,
            "name": "S",
            "associations": {"thermostats": [1], "fan_coils": [2, 3]},
        }
        coordinator = MagicMock()
        coordinator.schedules = [schedule]
        entity = SinumScheduleAssociationCountSensor(coordinator, schedule, "entry")
        attrs = entity.extra_state_attributes
        assert attrs["thermostats"] == [1]
        assert attrs["fan_coils"] == [2, 3]


class TestSinumScheduleActivePeriodSensor:
    def test_fallback_when_empty_schedule(self):
        schedule = {"id": 1, "name": "S"}
        coordinator = MagicMock()
        coordinator.schedules = [schedule]
        entity = SinumScheduleActivePeriodSensor(coordinator, schedule, "entry")
        assert entity.native_value == "Fallback"

    def test_extra_state_attributes_today_key(self):
        schedule = {"id": 1, "name": "S"}
        coordinator = MagicMock()
        coordinator.schedules = [schedule]
        entity = SinumScheduleActivePeriodSensor(coordinator, schedule, "entry")
        attrs = entity.extra_state_attributes
        assert "entries_today" in attrs
        assert "schedule_entries" in attrs


class TestSinumButtonSensor:
    def test_buzzer_attribute_when_present(self):
        coordinator = MagicMock()
        coordinator.wtp_devices = {
            1: {
                "id": 1,
                "type": WTYPE_BUTTON,
                "name": "Btn",
                "action": "1",
                "buttons_count": 2,
                "buzzer": True,
            }
        }
        entity = SinumButtonSensor(coordinator, 1, "entry", "wtp")
        attrs = entity.extra_state_attributes
        assert attrs["buttons_count"] == 2
        assert attrs["buzzer"] is True

    def test_no_buzzer_key_when_absent(self):
        coordinator = MagicMock()
        coordinator.wtp_devices = {1: {"id": 1, "type": WTYPE_BUTTON, "name": "Btn", "action": "1"}}
        entity = SinumButtonSensor(coordinator, 1, "entry", "wtp")
        attrs = entity.extra_state_attributes
        assert "buzzer" not in attrs


class TestLoRaSensorDeviceInfo:
    """Device-info enrichment for LoRa sensors (EUI + software_version)."""

    def _make_lora_sensor(self, device: dict) -> SinumSensor:
        from custom_components.sinum.sensor_bus_descriptions import LORA_SENSORS

        desc = next(d for d in LORA_SENSORS if d.api_key == "temperature")
        coordinator = MagicMock()
        coordinator.lora_devices = {2: device}
        return SinumSensor(coordinator, 2, desc, "entry")

    def test_eui_appears_as_serial_number(self):
        device = {
            "id": 2,
            "type": "temperature_sensor",
            "name": "Temperature sensor 1",
            "temperature": 231,
            "eui": "70B3D59BA000A200",
            "software_version": "ACW THO v4.x/v5.x",
        }
        entity = self._make_lora_sensor(device)
        assert entity._attr_device_info["serial_number"] == "70B3D59BA000A200"

    def test_software_version_appears_as_sw_version(self):
        device = {
            "id": 2,
            "type": "temperature_sensor",
            "name": "Temperature sensor 1",
            "temperature": 231,
            "eui": "70B3D59BA000A200",
            "software_version": "ACW THO v4.x/v5.x",
        }
        entity = self._make_lora_sensor(device)
        assert entity._attr_device_info["sw_version"] == "ACW THO v4.x/v5.x"

    def test_no_eui_serial_number_is_none(self):
        device = {
            "id": 2,
            "type": "temperature_sensor",
            "name": "Temperature sensor 1",
            "temperature": 231,
        }
        entity = self._make_lora_sensor(device)
        assert entity._attr_device_info.get("serial_number") is None

    def test_lora_values_scale_correctly(self):
        from custom_components.sinum.sensor_bus_descriptions import LORA_SENSORS

        temp_desc = next(d for d in LORA_SENSORS if d.api_key == "temperature")
        hum_desc = next(d for d in LORA_SENSORS if d.api_key == "humidity")
        bat_desc = next(d for d in LORA_SENSORS if d.api_key == "battery")
        assert temp_desc.scale == 0.1
        assert hum_desc.scale == 0.1
        assert bat_desc.scale == 1.0
