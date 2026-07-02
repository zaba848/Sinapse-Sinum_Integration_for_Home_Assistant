from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SinumConfigEntry
from .api import SinumConnectionError, SinumNotSupportedError
from .const import STYPE_BUTTON, VTYPE_THERMOSTAT_OUTPUT_GROUP, WTYPE_BUTTON
from .coordinator import SinumCoordinator
from .sensor_bus import (
    _SENTINEL_INT16,
    LORA_SENSORS,
    SBUS_REGULATOR_SENSORS,
    SBUS_SENSORS,
    WTP_SENSORS,
    SinumButtonSensor,
    SinumSensor,
    SinumSensorDescription,
    SinumTemperatureRegulatorSensor,
)
from .sensor_modbus import build_modbus_sensor_entities, build_slink_sensor_entities
from .sensor_schedule import (
    SinumScheduleActivePeriodSensor,
    SinumScheduleAssociationCountSensor,
    SinumScheduleFallbackTempSensor,
    SinumScheduleSensor,
    SinumScheduleTargetTempSensor,
)
from .sensor_virtual import (
    ENERGY_SENSORS,
    STORAGE_SENSORS,
    VIRTUAL_SENSORS,
    WEATHER_SENSORS,
    SinumAutomationStatusSensor,
    SinumEnergyCenterDataSensor,
    SinumEnergyCenterFlowSensor,
    SinumEnergyCenterStatusSensor,
    SinumEnergySensor,
    SinumEnergyStorageSensor,
    SinumEnergyStorageStatusSensor,
    SinumHubFirmwareSensor,
    SinumHubUptimeSensor,
    SinumHubWifiSensor,
    SinumThermostatOutputGroupSensor,
    SinumWeatherSensor,
)

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


def _add_virtual_sensors(
    coordinator: SinumCoordinator,
    entities: list[SensorEntity],
    entry_id: str,
) -> None:
    for device_id, device in coordinator.virtual_devices.items():
        if device.get("type") == VTYPE_THERMOSTAT_OUTPUT_GROUP:
            entities.append(SinumThermostatOutputGroupSensor(coordinator, device_id, entry_id))
        _append_sinum_sensors(coordinator, entities, entry_id, device_id, device, VIRTUAL_SENSORS)


_WTP_REGULATOR_SENSORS = tuple(d for d in WTP_SENSORS if d.source == "wtp_regulator")
_WTP_NORMAL_SENSORS = tuple(d for d in WTP_SENSORS if d.source == "wtp")


def _append_sinum_sensors(
    coordinator: SinumCoordinator,
    entities: list[SensorEntity],
    entry_id: str,
    device_id: int,
    device: dict,
    descriptions,
) -> None:
    for desc in descriptions:
        if desc.api_key not in device:
            continue
        entities.append(SinumSensor(coordinator, device_id, desc, entry_id))


def _append_regulator_sensors(
    coordinator: SinumCoordinator,
    entities: list[SensorEntity],
    entry_id: str,
    device_id: int,
    device: dict,
    descriptions,
) -> None:
    for desc in descriptions:
        if desc.api_key not in device:
            continue
        entities.append(SinumTemperatureRegulatorSensor(coordinator, device_id, desc, entry_id))


def _add_wtp_sensors(
    coordinator: SinumCoordinator,
    entities: list[SensorEntity],
    entry_id: str,
) -> None:
    for device_id, device in coordinator.wtp_devices.items():
        if device.get("type") == "temperature_regulator":
            _append_regulator_sensors(
                coordinator,
                entities,
                entry_id,
                device_id,
                device,
                _WTP_REGULATOR_SENSORS,
            )
        _append_sinum_sensors(
            coordinator,
            entities,
            entry_id,
            device_id,
            device,
            _WTP_NORMAL_SENSORS,
        )
        if device.get("type") == WTYPE_BUTTON:
            entities.append(SinumButtonSensor(coordinator, device_id, entry_id, "wtp"))


def _add_sbus_sensors(
    coordinator: SinumCoordinator,
    entities: list[SensorEntity],
    entry_id: str,
) -> None:
    for device_id, device in coordinator.sbus_devices.items():
        if device.get("type") == "temperature_regulator":
            _append_regulator_sensors(
                coordinator,
                entities,
                entry_id,
                device_id,
                device,
                SBUS_REGULATOR_SENSORS,
            )
            continue
        _append_sinum_sensors(coordinator, entities, entry_id, device_id, device, SBUS_SENSORS)
        if device.get("type") == STYPE_BUTTON:
            entities.append(SinumButtonSensor(coordinator, device_id, entry_id, "sbus"))


def _add_lora_sensors(
    coordinator: SinumCoordinator,
    entities: list[SensorEntity],
    entry_id: str,
) -> None:
    for device_id, device in coordinator.lora_devices.items():
        for desc in LORA_SENSORS:
            if desc.api_key in device:
                entities.append(SinumSensor(coordinator, device_id, desc, entry_id))


async def _try_add_weather_sensors(
    coordinator: SinumCoordinator, entities: list[SensorEntity], entry_id: str
) -> None:
    try:
        weather = await coordinator.client.get_weather()
        for desc in WEATHER_SENSORS:
            if desc.api_key in weather:
                entities.append(SinumWeatherSensor(coordinator.client, weather, desc, entry_id))
    except (SinumConnectionError, SinumNotSupportedError):
        _LOGGER.debug("Weather endpoint not available on this hub")


async def _try_add_energy_sensors(
    coordinator: SinumCoordinator, entities: list[SensorEntity], entry_id: str
) -> None:
    try:
        energy = await coordinator.client.get_energy()
        for desc in ENERGY_SENSORS:
            if desc.api_key in energy:
                entities.append(SinumEnergySensor(coordinator.client, energy, desc, entry_id))
    except (SinumConnectionError, SinumNotSupportedError):
        _LOGGER.debug("Energy endpoint not available on this hub")


async def _try_add_energy_center_sensor(
    coordinator: SinumCoordinator, entities: list[SensorEntity], entry_id: str
) -> None:
    try:
        ec = await coordinator.client.get_energy_center_summary()
        entities.append(SinumEnergyCenterStatusSensor(coordinator.client, ec, entry_id))
    except Exception:
        _LOGGER.debug("Energy Center endpoints not available on this hub")


async def _try_add_energy_center_detail_sensors(
    coordinator: SinumCoordinator, entities: list[SensorEntity], entry_id: str
) -> None:
    client = coordinator.client
    try:
        data = await client.get_energy_center_flow_monitor()
        entities.append(SinumEnergyCenterFlowSensor(client, data, entry_id))
    except (SinumConnectionError, SinumNotSupportedError):
        _LOGGER.debug("Energy Center flow monitor not available")
    try:
        data = await client.get_energy_center_consumption()
        sensor = SinumEnergyCenterDataSensor(
            client,
            data,
            entry_id,
            "consumption",
            "energy_center_data_consumption",
            "mdi:lightning-bolt",
            client.get_energy_center_consumption,
            value_path=("total", "total_consumption"),
        )
        entities.append(sensor)
    except (SinumConnectionError, SinumNotSupportedError):
        _LOGGER.debug("Energy Center consumption not available")
    try:
        data = await client.get_energy_center_production()
        sensor = SinumEnergyCenterDataSensor(
            client,
            data,
            entry_id,
            "production",
            "energy_center_data_production",
            "mdi:solar-power",
            client.get_energy_center_production,
            value_path=("total", "all"),
        )
        entities.append(sensor)
    except (SinumConnectionError, SinumNotSupportedError):
        _LOGGER.debug("Energy Center production not available")


async def _try_add_energy_storage_sensors(
    coordinator: SinumCoordinator, entities: list[SensorEntity], entry_id: str
) -> None:
    client = coordinator.client
    try:
        data = await client.get_energy_center_storage()
        for suffix, tkey, icon, path, dc, sc, unit in STORAGE_SENSORS:
            entities.append(
                SinumEnergyStorageSensor(client, data, entry_id, suffix, tkey, icon, path, dc, sc, unit)
            )
        entities.append(SinumEnergyStorageStatusSensor(client, data, entry_id))
    except (SinumConnectionError, SinumNotSupportedError):
        _LOGGER.debug("Energy Center storage not available")


def _add_hub_sensors(
    coordinator: SinumCoordinator, entities: list[SensorEntity], entry_id: str
) -> None:
    if not coordinator.hub_info:
        return
    entities.append(SinumHubUptimeSensor(coordinator, entry_id))
    entities.append(SinumHubFirmwareSensor(coordinator, entry_id))
    wifi = coordinator.hub_info.get("wifi", {})
    if isinstance(wifi, dict) and wifi.get("signal") is not None:
        entities.append(SinumHubWifiSensor(coordinator, entry_id))


async def _add_optional_sensors(
    coordinator: SinumCoordinator,
    entities: list[SensorEntity],
    entry_id: str,
) -> None:
    await _try_add_weather_sensors(coordinator, entities, entry_id)
    await _try_add_energy_sensors(coordinator, entities, entry_id)
    await _try_add_energy_center_sensor(coordinator, entities, entry_id)
    await _try_add_energy_center_detail_sensors(coordinator, entities, entry_id)
    await _try_add_energy_storage_sensors(coordinator, entities, entry_id)
    _add_hub_sensors(coordinator, entities, entry_id)


def _add_schedule_sensors(
    coordinator: SinumCoordinator,
    entities: list[SensorEntity],
    entry_id: str,
) -> None:
    for schedule in coordinator.schedules:
        if schedule.get("id") is None:
            continue
        if schedule.get("type") == "thermal":
            entities.append(SinumScheduleTargetTempSensor(coordinator, schedule, entry_id))
            entities.append(SinumScheduleFallbackTempSensor(coordinator, schedule, entry_id))
        entities.append(SinumScheduleActivePeriodSensor(coordinator, schedule, entry_id))
        entities.append(SinumScheduleAssociationCountSensor(coordinator, schedule, entry_id))


def _add_automation_sensors(
    coordinator: SinumCoordinator,
    entities: list[SensorEntity],
    entry_id: str,
) -> None:
    for automation in coordinator.automations:
        if automation.get("id") is not None:
            entities.append(SinumAutomationStatusSensor(coordinator, automation, entry_id))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinumCoordinator = entry.runtime_data
    entities: list[SensorEntity] = []

    _add_virtual_sensors(coordinator, entities, entry.entry_id)
    _add_wtp_sensors(coordinator, entities, entry.entry_id)
    _add_sbus_sensors(coordinator, entities, entry.entry_id)
    _add_lora_sensors(coordinator, entities, entry.entry_id)
    entities.extend(build_modbus_sensor_entities(coordinator, entry.entry_id))
    entities.extend(build_slink_sensor_entities(coordinator, entry.entry_id))
    await _add_optional_sensors(coordinator, entities, entry.entry_id)
    _add_schedule_sensors(coordinator, entities, entry.entry_id)
    _add_automation_sensors(coordinator, entities, entry.entry_id)

    async_add_entities(entities)


__all__ = [
    "ENERGY_SENSORS",
    "LORA_SENSORS",
    "SBUS_REGULATOR_SENSORS",
    "SBUS_SENSORS",
    "VIRTUAL_SENSORS",
    "WEATHER_SENSORS",
    "WTP_SENSORS",
    "SinumAutomationStatusSensor",
    "SinumButtonSensor",
    "SinumEnergyCenterStatusSensor",
    "SinumEnergySensor",
    "SinumHubFirmwareSensor",
    "SinumHubUptimeSensor",
    "SinumHubWifiSensor",
    "SinumScheduleActivePeriodSensor",
    "SinumScheduleAssociationCountSensor",
    "SinumScheduleFallbackTempSensor",
    "SinumScheduleSensor",
    "SinumScheduleTargetTempSensor",
    "SinumSensor",
    "SinumSensorDescription",
    "SinumTemperatureRegulatorSensor",
    "SinumThermostatOutputGroupSensor",
    "SinumWeatherSensor",
    "_SENTINEL_INT16",
    "async_setup_entry",
]
