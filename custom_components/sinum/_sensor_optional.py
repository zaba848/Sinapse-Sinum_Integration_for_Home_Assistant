"""Optional/hub sensor factory functions for async_setup_entry."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity

from .api import SinumConnectionError, SinumNotSupportedError
from .coordinator import SinumCoordinator
from .sensor_energy_center import (
    STORAGE_SENSORS,
    SinumEnergyCenterDataSensor,
    SinumEnergyCenterFlowSensor,
    SinumEnergyCenterStatusSensor,
    SinumEnergyStorageSensor,
    SinumEnergyStorageStatusSensor,
)
from .sensor_hub import SinumHubFirmwareSensor, SinumHubUptimeSensor, SinumHubWifiSensor
from .sensor_virtual import ENERGY_SENSORS, WEATHER_SENSORS, SinumEnergySensor, SinumWeatherSensor

_LOGGER = logging.getLogger(__name__)


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
