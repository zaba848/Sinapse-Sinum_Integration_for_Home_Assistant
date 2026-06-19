from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SinumConfigEntry
from .api import SinumConnectionError
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
from .sensor_schedule import (
    SinumScheduleActivePeriodSensor,
    SinumScheduleAssociationCountSensor,
    SinumScheduleFallbackTempSensor,
    SinumScheduleSensor,
    SinumScheduleTargetTempSensor,
)
from .sensor_virtual import (
    ENERGY_SENSORS,
    VIRTUAL_SENSORS,
    WEATHER_SENSORS,
    SinumAutomationStatusSensor,
    SinumEnergyCenterStatusSensor,
    SinumEnergySensor,
    SinumHubUptimeSensor,
    SinumHubWifiSensor,
    SinumThermostatOutputGroupSensor,
    SinumWeatherSensor,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinumCoordinator = entry.runtime_data
    entities: list[SensorEntity] = []

    # Virtual thermostat sensors
    for device_id, device in coordinator.virtual_devices.items():
        if device.get("type") == VTYPE_THERMOSTAT_OUTPUT_GROUP:
            entities.append(
                SinumThermostatOutputGroupSensor(coordinator, device_id, entry.entry_id)
            )
        for desc in VIRTUAL_SENSORS:
            if desc.api_key in device:
                entities.append(SinumSensor(coordinator, device_id, desc, entry.entry_id))

    # WTP device sensors
    for device_id, device in coordinator.wtp_devices.items():
        # Temperature regulator sensors (Phase 7B)
        if device.get("type") == "temperature_regulator":
            for desc in WTP_SENSORS:
                if desc.source == "wtp_regulator" and desc.api_key in device:
                    entities.append(
                        SinumTemperatureRegulatorSensor(
                            coordinator, device_id, desc, entry.entry_id
                        )
                    )
        # Generic WTP device sensors
        for desc in WTP_SENSORS:
            if desc.source == "wtp" and desc.api_key in device:
                entities.append(SinumSensor(coordinator, device_id, desc, entry.entry_id))

    # WTP button sensors
    for device_id, device in coordinator.wtp_devices.items():
        if device.get("type") == WTYPE_BUTTON:
            entities.append(SinumButtonSensor(coordinator, device_id, entry.entry_id, "wtp"))

    # SBUS device sensors
    for device_id, device in coordinator.sbus_devices.items():
        if device.get("type") == "temperature_regulator":
            for desc in SBUS_REGULATOR_SENSORS:
                if desc.api_key in device:
                    entities.append(
                        SinumTemperatureRegulatorSensor(
                            coordinator, device_id, desc, entry.entry_id
                        )
                    )
        else:
            for desc in SBUS_SENSORS:
                if desc.api_key in device:
                    entities.append(SinumSensor(coordinator, device_id, desc, entry.entry_id))
            if device.get("type") == STYPE_BUTTON:
                entities.append(SinumButtonSensor(coordinator, device_id, entry.entry_id, "sbus"))

    # LoRa device sensors
    for device_id, device in coordinator.lora_devices.items():
        for desc in LORA_SENSORS:
            if desc.api_key in device:
                entities.append(SinumSensor(coordinator, device_id, desc, entry.entry_id))

    # Weather sensors (best-effort)
    try:
        weather = await coordinator.client.get_weather()
        for desc in WEATHER_SENSORS:
            if desc.api_key in weather:
                entities.append(
                    SinumWeatherSensor(coordinator.client, weather, desc, entry.entry_id)
                )
    except SinumConnectionError:
        _LOGGER.debug("Weather endpoint not available on this hub")

    # Energy Center sensors (best-effort)
    try:
        energy = await coordinator.client.get_energy()
        for desc in ENERGY_SENSORS:
            if desc.api_key in energy:
                entities.append(SinumEnergySensor(coordinator.client, energy, desc, entry.entry_id))
    except SinumConnectionError:
        _LOGGER.debug("Energy endpoint not available on this hub")

    # Energy Center diagnostic endpoint coverage (best-effort)
    try:
        energy_center = await coordinator.client.get_energy_center_summary()
        entities.append(
            SinumEnergyCenterStatusSensor(coordinator.client, energy_center, entry.entry_id)
        )
    except SinumConnectionError:
        _LOGGER.debug("Energy Center endpoints not available on this hub")

    # Hub diagnostic sensors (from /api/v1/info — always available)
    if coordinator.hub_info:
        entities.append(SinumHubUptimeSensor(coordinator, entry.entry_id))
        # Wi-Fi sensor requires sinapse_api.lua Lua extension (optional)
        wifi = coordinator.hub_info.get("wifi", {})
        if isinstance(wifi, dict) and wifi.get("signal") is not None:
            entities.append(SinumHubWifiSensor(coordinator, entry.entry_id))

    # Schedule sensors (all schedules get active period + association count).
    # Temperature sensors only for thermal schedules; relay/boolean schedules lack those fields.
    for schedule in coordinator.schedules:
        schedule_id = schedule.get("id")
        if schedule_id is None:
            continue
        is_thermal = schedule.get("type") == "thermal"
        if is_thermal:
            entities.append(SinumScheduleTargetTempSensor(coordinator, schedule, entry.entry_id))
            entities.append(SinumScheduleFallbackTempSensor(coordinator, schedule, entry.entry_id))
        entities.append(SinumScheduleActivePeriodSensor(coordinator, schedule, entry.entry_id))
        entities.append(SinumScheduleAssociationCountSensor(coordinator, schedule, entry.entry_id))

    # Automation diagnostics are read-only and disabled by default in the entity registry.
    for automation in coordinator.automations:
        if automation.get("id") is not None:
            entities.append(SinumAutomationStatusSensor(coordinator, automation, entry.entry_id))

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
