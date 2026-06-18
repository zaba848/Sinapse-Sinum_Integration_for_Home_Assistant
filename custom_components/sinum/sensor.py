from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    DEGREE,
    LIGHT_LUX,
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfIrradiance,
    UnitOfPower,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SinumConfigEntry
from .api import SinumConnectionError
from .const import DOMAIN, LTYPE_HUMIDITY_SENSOR, LTYPE_TEMP_SENSOR, STYPE_BUTTON, WTYPE_BUTTON
from .coordinator import SinumCoordinator

_LOGGER = logging.getLogger(__name__)

# Sinum hub encodes "no value / sensor error" as signed 16-bit minimum (-32768).
# Multiply by 0.1 scale → -3276.8°C. Treat this as unavailable.
_SENTINEL_INT16 = -32768


@dataclass(frozen=True, kw_only=True)
class SinumSensorDescription(SensorEntityDescription):
    api_key: str
    scale: float = 1.0
    source: str = "virtual"
    is_text: bool = False


# ── Virtual thermostat sensors ─────────────────────────────────────────────────

VIRTUAL_SENSORS: tuple[SinumSensorDescription, ...] = (
    SinumSensorDescription(
        key="temperature",
        api_key="temperature",
        source="virtual",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        scale=0.1,
        suggested_display_precision=1,
    ),
    SinumSensorDescription(
        key="humidity",
        api_key="humidity",
        source="virtual",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        scale=0.1,
        suggested_display_precision=0,
    ),
    SinumSensorDescription(
        key="room_temperature",
        api_key="room_temperature",
        source="virtual",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        scale=0.1,
        suggested_display_precision=1,
        translation_key="room_temperature",
    ),
    SinumSensorDescription(
        key="dew_point",
        api_key="dew_point",
        source="virtual",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        scale=0.1,
        suggested_display_precision=1,
        translation_key="dew_point",
    ),
)

# ── WTP device sensors ─────────────────────────────────────────────────────────

WTP_SENSORS: tuple[SinumSensorDescription, ...] = (
    SinumSensorDescription(
        key="temperature",
        api_key="temperature",
        source="wtp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        scale=0.1,
        suggested_display_precision=1,
    ),
    SinumSensorDescription(
        key="humidity",
        api_key="humidity",
        source="wtp",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        scale=0.1,
        suggested_display_precision=0,
    ),
    SinumSensorDescription(
        key="co2",
        api_key="co2",
        source="wtp",
        device_class=SensorDeviceClass.CO2,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        suggested_display_precision=0,
    ),
    SinumSensorDescription(
        key="pm1",
        api_key="pm1p0",
        source="wtp",
        device_class=SensorDeviceClass.PM1,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="µg/m³",
        suggested_display_precision=1,
    ),
    SinumSensorDescription(
        key="pm25",
        api_key="pm2p5",
        source="wtp",
        device_class=SensorDeviceClass.PM25,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="µg/m³",
        suggested_display_precision=1,
    ),
    SinumSensorDescription(
        key="pm4",
        api_key="pm4p0",
        source="wtp",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="µg/m³",
        icon="mdi:air-filter",
        suggested_display_precision=1,
    ),
    SinumSensorDescription(
        key="pm10",
        api_key="pm10p0",
        source="wtp",
        device_class=SensorDeviceClass.PM10,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="µg/m³",
        suggested_display_precision=1,
    ),
    SinumSensorDescription(
        key="illuminance",
        api_key="illuminance",
        source="wtp",
        device_class=SensorDeviceClass.ILLUMINANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=LIGHT_LUX,
        suggested_display_precision=0,
    ),
    SinumSensorDescription(
        key="pressure",
        api_key="pressure",
        source="wtp",
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.HPA,
        scale=0.1,
        suggested_display_precision=1,
    ),
    SinumSensorDescription(
        key="iaq",
        api_key="iaq",
        source="wtp",
        device_class=SensorDeviceClass.AQI,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    SinumSensorDescription(
        key="air_quality",
        api_key="air_quality",
        source="wtp",
        icon="mdi:air-filter",
        is_text=True,
    ),
    SinumSensorDescription(
        key="active_power",
        api_key="active_power",
        source="wtp",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        scale=0.001,
        suggested_display_precision=1,
    ),
    SinumSensorDescription(
        key="voltage",
        api_key="voltage",
        source="wtp",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        scale=0.001,
        suggested_display_precision=1,
    ),
    SinumSensorDescription(
        key="current",
        api_key="current",
        source="wtp",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        scale=0.001,
        suggested_display_precision=3,
    ),
    SinumSensorDescription(
        key="energy_consumed_total",
        api_key="energy_consumed_total",
        source="wtp",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_display_precision=0,
    ),
    SinumSensorDescription(
        key="energy_consumed_today",
        api_key="energy_consumed_today",
        source="wtp",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_display_precision=0,
        translation_key="energy_consumed_today",
    ),
    SinumSensorDescription(
        key="energy_consumed_yesterday",
        api_key="energy_consumed_yesterday",
        source="wtp",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_display_precision=0,
        translation_key="energy_consumed_yesterday",
    ),
    SinumSensorDescription(
        key="room_temperature",
        api_key="room_temperature",
        source="wtp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        scale=0.1,
        suggested_display_precision=1,
        translation_key="room_temperature",
    ),
    SinumSensorDescription(
        key="dew_point",
        api_key="dew_point",
        source="wtp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        scale=0.1,
        suggested_display_precision=1,
        translation_key="dew_point",
    ),
    SinumSensorDescription(
        key="battery",
        api_key="battery",
        source="wtp",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
    ),
    SinumSensorDescription(
        key="signal",
        api_key="signal",
        source="wtp",
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
        icon="mdi:signal",
        translation_key="signal_strength",
    ),
    # Temperature regulator sensors (Phase 7B)
    SinumSensorDescription(
        key="temperature",
        api_key="temperature",
        source="wtp_regulator",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        scale=0.1,
        suggested_display_precision=1,
        translation_key="regulator_temperature",
    ),
    SinumSensorDescription(
        key="target_temperature",
        api_key="target_temperature",
        source="wtp_regulator",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        scale=0.1,
        suggested_display_precision=1,
        translation_key="regulator_target_temperature",
    ),
)

# ── SBUS device sensors ────────────────────────────────────────────────────────

SBUS_SENSORS: tuple[SinumSensorDescription, ...] = (
    SinumSensorDescription(
        key="temperature",
        api_key="temperature",
        source="sbus",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        scale=0.1,
        suggested_display_precision=1,
    ),
    SinumSensorDescription(
        key="humidity",
        api_key="humidity",
        source="sbus",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        scale=0.1,
        suggested_display_precision=0,
    ),
    SinumSensorDescription(
        key="illuminance",
        api_key="illuminance",
        source="sbus",
        device_class=SensorDeviceClass.ILLUMINANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=LIGHT_LUX,
        suggested_display_precision=0,
    ),
    SinumSensorDescription(
        key="analog_value",
        api_key="value",
        source="sbus",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge",
    ),
    SinumSensorDescription(
        key="impulse_total_count",
        api_key="total_count",
        source="sbus",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
        translation_key="impulse_total_count",
    ),
    SinumSensorDescription(
        key="impulse_window_count",
        api_key="window_count",
        source="sbus",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:counter",
        translation_key="impulse_window_count",
    ),
    SinumSensorDescription(
        key="impulse_total_value",
        api_key="total_value",
        source="sbus",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:sigma",
        translation_key="impulse_total_value",
    ),
    SinumSensorDescription(
        key="impulse_window_value",
        api_key="window_value",
        source="sbus",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:sigma",
        translation_key="impulse_window_value",
    ),
    SinumSensorDescription(
        key="pwm_duty_cycle",
        api_key="duty_cycle",
        source="sbus",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:pulse",
        suggested_display_precision=0,
    ),
    SinumSensorDescription(
        key="pwm_frequency",
        api_key="frequency",
        source="sbus",
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="Hz",
        suggested_display_precision=0,
    ),
    SinumSensorDescription(
        key="valve_temperature",
        api_key="temperature_valve",
        source="sbus",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        scale=0.1,
        suggested_display_precision=1,
        translation_key="valve_temperature",
    ),
    SinumSensorDescription(
        key="valve_position",
        api_key="open_percent",
        source="sbus",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        scale=0.01,
        suggested_display_precision=1,
        icon="mdi:valve",
        translation_key="valve_position",
    ),
    SinumSensorDescription(
        key="active_power",
        api_key="active_power",
        source="sbus",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        scale=0.001,
        suggested_display_precision=1,
    ),
    SinumSensorDescription(
        key="voltage",
        api_key="voltage",
        source="sbus",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        scale=0.001,
        suggested_display_precision=1,
    ),
    SinumSensorDescription(
        key="current",
        api_key="current",
        source="sbus",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        scale=0.001,
        suggested_display_precision=3,
    ),
    SinumSensorDescription(
        key="energy_consumed_total",
        api_key="energy_consumed_total",
        source="sbus",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_display_precision=0,
    ),
    SinumSensorDescription(
        key="energy_consumed_today",
        api_key="energy_consumed_today",
        source="sbus",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_display_precision=0,
        translation_key="energy_consumed_today",
    ),
    SinumSensorDescription(
        key="energy_consumed_yesterday",
        api_key="energy_consumed_yesterday",
        source="sbus",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_display_precision=0,
        translation_key="energy_consumed_yesterday",
    ),
)

# ── SBUS temperature_regulator sensors ────────────────────────────────────────

SBUS_REGULATOR_SENSORS: tuple[SinumSensorDescription, ...] = (
    SinumSensorDescription(
        key="target_temperature",
        api_key="target_temperature",
        source="sbus_regulator",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        scale=0.1,
        suggested_display_precision=1,
        translation_key="regulator_target_temperature",
    ),
)

# ── LoRa device sensors ────────────────────────────────────────────────────────

LORA_SENSORS: tuple[SinumSensorDescription, ...] = (
    SinumSensorDescription(
        key="temperature",
        api_key="temperature",
        source="lora",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        scale=0.1,
        suggested_display_precision=1,
    ),
    SinumSensorDescription(
        key="humidity",
        api_key="humidity",
        source="lora",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        scale=0.1,
        suggested_display_precision=0,
    ),
    SinumSensorDescription(
        key="battery",
        api_key="battery",
        source="lora",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
    ),
    SinumSensorDescription(
        key="signal",
        api_key="signal",
        source="lora",
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
        icon="mdi:signal",
        translation_key="signal_strength",
    ),
)

# ── Weather sensors ────────────────────────────────────────────────────────────

WEATHER_SENSORS: tuple[SinumSensorDescription, ...] = (
    SinumSensorDescription(
        key="weather_temperature",
        api_key="temperature",
        source="weather",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        scale=0.1,
        suggested_display_precision=1,
        translation_key="weather_temperature",
    ),
    SinumSensorDescription(
        key="weather_humidity",
        api_key="humidity",
        source="weather",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        scale=0.1,
        suggested_display_precision=0,
        translation_key="weather_humidity",
    ),
    SinumSensorDescription(
        key="weather_pressure",
        api_key="pressure",
        source="weather",
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.HPA,
        scale=0.1,
        suggested_display_precision=1,
        translation_key="weather_pressure",
    ),
    SinumSensorDescription(
        key="weather_wind_speed",
        api_key="wind_speed",
        source="weather",
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        scale=0.1,
        suggested_display_precision=1,
        translation_key="weather_wind_speed",
    ),
    SinumSensorDescription(
        key="weather_uv_index",
        api_key="uv_index",
        source="weather",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="UV index",
        icon="mdi:sun-wireless",
        translation_key="weather_uv_index",
    ),
    SinumSensorDescription(
        key="weather_solar_irradiance",
        api_key="solar_irradiance",
        source="weather",
        device_class=SensorDeviceClass.IRRADIANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        scale=0.1,
        suggested_display_precision=1,
        translation_key="weather_solar_irradiance",
    ),
    SinumSensorDescription(
        key="weather_cloud_coverage",
        api_key="cloud_coverage",
        source="weather",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:cloud-percent",
        translation_key="weather_cloud_coverage",
    ),
    SinumSensorDescription(
        key="weather_wind_degrees",
        api_key="wind_degrees",
        source="weather",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=DEGREE,
        icon="mdi:compass",
        translation_key="weather_wind_degrees",
    ),
)

# ── Energy Center sensors ──────────────────────────────────────────────────────

ENERGY_SENSORS: tuple[SinumSensorDescription, ...] = (
    SinumSensorDescription(
        key="energy_consumption",
        api_key="consumption",
        source="energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_display_precision=0,
        translation_key="energy_consumption",
    ),
    SinumSensorDescription(
        key="energy_production",
        api_key="production",
        source="energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_display_precision=0,
        translation_key="energy_production",
    ),
    SinumSensorDescription(
        key="energy_storage",
        api_key="storage",
        source="energy",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_display_precision=0,
        translation_key="energy_storage",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinumCoordinator = entry.runtime_data
    entities: list[SensorEntity] = []

    # Virtual thermostat sensors
    for device_id, device in coordinator.virtual_devices.items():
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

    # Hub diagnostic sensors (from /api/v1/info — always available)
    if coordinator.hub_info:
        entities.append(SinumHubUptimeSensor(coordinator, entry.entry_id))
        # Wi-Fi sensor requires sinapse_api.lua Lua extension (optional)
        wifi = coordinator.hub_info.get("wifi", {})
        if isinstance(wifi, dict) and wifi.get("signal") is not None:
            entities.append(SinumHubWifiSensor(coordinator, entry.entry_id))

    # Thermal schedule sensors are coordinator-backed, so values refresh with polling/MQTT updates.
    for schedule in coordinator.schedules:
        schedule_id = schedule.get("id")
        if schedule_id is None:
            continue
        entities.append(SinumScheduleTargetTempSensor(coordinator, schedule, entry.entry_id))
        entities.append(SinumScheduleFallbackTempSensor(coordinator, schedule, entry.entry_id))
        entities.append(SinumScheduleActivePeriodSensor(coordinator, schedule, entry.entry_id))
        entities.append(SinumScheduleAssociationCountSensor(coordinator, schedule, entry.entry_id))

    async_add_entities(entities)


# ── Entity classes ─────────────────────────────────────────────────────────────


class SinumSensor(CoordinatorEntity[SinumCoordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: SinumSensorDescription

    def __init__(
        self,
        coordinator: SinumCoordinator,
        device_id: int,
        description: SinumSensorDescription,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._source = description.source
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{self._source}_{device_id}_{description.key}"

        device = self._get_device_dict(coordinator)
        if not description.native_unit_of_measurement:
            device_unit = device.get("unit") or None  # "" → None
            if device_unit:
                self._attr_native_unit_of_measurement = device_unit

        label = device.get("_device_name") or device.get("name", str(device_id))
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{self._source}_{device_id}")},
            name=label,
            manufacturer="TECH Sterowniki",
            model=device.get("_parent_model") or _model_for_source(self._source),
            suggested_area=device.get("_area") or None,
        )

    def _get_device_dict(self, coordinator: SinumCoordinator) -> dict[str, Any]:
        if self._source == "virtual":
            return coordinator.virtual_devices.get(self._device_id, {})
        if self._source in ("sbus", "sbus_regulator"):
            return coordinator.sbus_devices.get(self._device_id, {})
        if self._source == "lora":
            return coordinator.lora_devices.get(self._device_id, {})
        return coordinator.wtp_devices.get(self._device_id, {})

    @property
    def _device(self) -> dict[str, Any]:
        return self._get_device_dict(self.coordinator)

    @property
    def native_value(self) -> float | str | None:
        raw = self._device.get(self.entity_description.api_key)
        if raw is None:
            return None
        if self.entity_description.is_text:
            return str(raw)
        if not isinstance(raw, (int, float)):
            return None
        if raw == _SENTINEL_INT16:
            return None
        return raw * self.entity_description.scale


def _model_for_source(source: str) -> str:
    if source == "virtual":
        return "Sinum Virtual Device"
    if source == "sbus":
        return "Sinum SBUS Sensor"
    if source in ("wtp_regulator", "sbus_regulator"):
        return "Sinum Temperature Regulator"
    if source == "lora":
        return "Sinum LoRa Sensor"
    return "Sinum WTP Sensor"


class SinumTemperatureRegulatorSensor(SinumSensor):
    """Temperature regulator sensor with attributes for mode and control state (Phase 7B)."""

    def __init__(
        self,
        coordinator: SinumCoordinator,
        device_id: int,
        description: SinumSensorDescription,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator, device_id, description, entry_id)
        # _source stays as "wtp_regulator" or "sbus_regulator" — _get_device_dict handles both

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Show regulator mode and control state as attributes."""
        device = self._device
        attrs: dict[str, Any] = {}

        if "system_mode" in device:
            attrs["system_mode"] = device["system_mode"]
        if "target_temperature_mode" in device:
            ttm = device["target_temperature_mode"]
            attrs["target_temperature_mode"] = (
                ttm.get("current") or ttm.get("mode") if isinstance(ttm, dict) else ttm
            )
        if "mode_mutable" in device:
            attrs["mode_mutable"] = device["mode_mutable"]
        if "parent_id" in device:
            attrs["parent_id"] = device["parent_id"]

        return attrs


class SinumWeatherSensor(SensorEntity):
    """Weather sensor — polled once at startup; not coordinator-backed (hub fetches from API)."""

    _attr_has_entity_name = True
    entity_description: SinumSensorDescription

    def __init__(
        self,
        client: Any,
        initial: dict[str, Any],
        description: SinumSensorDescription,
        entry_id: str,
    ) -> None:
        self._client = client
        self._data = initial
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_weather_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_weather")},
            name="Sinum Weather",
            manufacturer="TECH Sterowniki",
            model="Sinum EH-01 Weather",
        )

    @property
    def native_value(self) -> float | None:
        raw = self._data.get(self.entity_description.api_key)
        if raw is None or raw == _SENTINEL_INT16:
            return None
        return raw * self.entity_description.scale

    async def async_update(self) -> None:
        try:
            self._data = await self._client.get_weather()
        except SinumConnectionError as err:
            _LOGGER.warning("Weather update failed: %s", err)


class SinumEnergySensor(SensorEntity):
    """Energy Center sensor."""

    _attr_has_entity_name = True
    entity_description: SinumSensorDescription

    def __init__(
        self,
        client: Any,
        initial: dict[str, Any],
        description: SinumSensorDescription,
        entry_id: str,
    ) -> None:
        self._client = client
        self._data = initial
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_energy_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_energy")},
            name="Sinum Energy Center",
            manufacturer="TECH Sterowniki",
            model="Sinum EH-01 Energy",
        )

    @property
    def native_value(self) -> float | None:
        raw = self._data.get(self.entity_description.api_key)
        if raw is None or raw == _SENTINEL_INT16:
            return None
        return raw * self.entity_description.scale

    async def async_update(self) -> None:
        try:
            self._data = await self._client.get_energy()
        except SinumConnectionError as err:
            _LOGGER.warning("Energy update failed: %s", err)


# ── Hub diagnostic sensors ─────────────────────────────────────────────────────


def _hub_device_info(entry_id: str, hub_info: dict[str, Any]) -> DeviceInfo:
    # device_type field: "sinum", "sinum_pro", "sinum_lite" or similar
    device_type = hub_info.get("device_type", "")
    name = hub_info.get("name", "Sinum Hub")
    model_map = {
        "sinum_pro": "Sinum Pro",
        "sinum_lite": "Sinum Lite",
        "sinum": "Sinum EH-01",
    }
    model = model_map.get(device_type, "Sinum EH-01")
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_hub")},
        name=name or "Sinum Hub",
        manufacturer="TECH Sterowniki",
        model=model,
        sw_version=hub_info.get("version"),
        hw_version=hub_info.get("uid"),
        configuration_url=f"http://{hub_info.get('ip', '')}" if hub_info.get("ip") else None,
    )


class SinumHubUptimeSensor(CoordinatorEntity[SinumCoordinator], SensorEntity):
    """Hub uptime sensor — seconds since last reboot."""

    _attr_has_entity_name = True
    _attr_translation_key = "hub_uptime"
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator: SinumCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_hub_uptime"
        self._attr_device_info = _hub_device_info(entry_id, coordinator.hub_info)

    @property
    def native_value(self) -> int | None:
        return self.coordinator.hub_info.get("uptime")


class SinumHubWifiSensor(CoordinatorEntity[SinumCoordinator], SensorEntity):
    """Hub Wi-Fi signal strength sensor."""

    _attr_has_entity_name = True
    _attr_translation_key = "hub_wifi_signal"
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: SinumCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_hub_wifi_signal"
        self._attr_device_info = _hub_device_info(entry_id, coordinator.hub_info)

    @property
    def native_value(self) -> int | None:
        return self.coordinator.hub_info.get("wifi", {}).get("signal")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        wifi = self.coordinator.hub_info.get("wifi", {})
        attrs: dict[str, Any] = {}
        if ssid := wifi.get("ssid"):
            attrs["ssid"] = ssid
        if ip := wifi.get("ip"):
            attrs["ip"] = ip
        return attrs


# ── Schedule sensors ──────────────────────────────────────────────────────────


class SinumScheduleSensor(CoordinatorEntity[SinumCoordinator], SensorEntity):
    """Base class for coordinator-backed schedule sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SinumCoordinator,
        schedule: dict[str, Any],
        entry_id: str,
        unique_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._initial_schedule = schedule
        self._schedule_id = schedule.get("id")
        self._attr_unique_id = f"{entry_id}_schedule_{self._schedule_id}_{unique_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"schedule_{self._schedule_id}_{entry_id}")},
            name=f"Sinum Schedule {schedule.get('name', self._schedule_id)}",
            manufacturer="TECH Sterowniki",
            model="Thermal Schedule",
        )

    @property
    def _schedule(self) -> dict[str, Any]:
        schedules = getattr(self.coordinator, "schedules", [])
        for schedule in schedules:
            if str(schedule.get("id")) == str(self._schedule_id):
                return schedule
        return self._initial_schedule


class SinumScheduleTargetTempSensor(SinumScheduleSensor):
    """Current target temperature from schedule."""

    _attr_name = "Current Target Temperature"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:thermometer"

    def __init__(
        self,
        coordinator: SinumCoordinator,
        schedule: dict[str, Any],
        entry_id: str,
    ) -> None:
        super().__init__(coordinator, schedule, entry_id, "target_temp")

    @property
    def native_value(self) -> float | None:
        raw = self._schedule.get("current_target_temperature")
        return raw / 10 if raw is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "schedule_id": self._schedule.get("id"),
            "schedule_name": self._schedule.get("name"),
            "modes": self._schedule.get("modes", []),
        }


class SinumScheduleFallbackTempSensor(SinumScheduleSensor):
    """Fallback temperature for schedule."""

    _attr_name = "Fallback Temperature"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:thermometer-low"

    def __init__(
        self,
        coordinator: SinumCoordinator,
        schedule: dict[str, Any],
        entry_id: str,
    ) -> None:
        super().__init__(coordinator, schedule, entry_id, "fallback_temp")

    @property
    def native_value(self) -> float | None:
        raw = self._schedule.get("fallback")
        return raw / 10 if raw is not None else None


class SinumScheduleActivePeriodSensor(SinumScheduleSensor):
    """Active schedule period (current time entry)."""

    _attr_name = "Active Period"
    _attr_icon = "mdi:calendar-clock"

    def __init__(
        self,
        coordinator: SinumCoordinator,
        schedule: dict[str, Any],
        entry_id: str,
    ) -> None:
        super().__init__(coordinator, schedule, entry_id, "active_period")

    @property
    def native_value(self) -> str:
        """Return 'Active' if in scheduled period, else 'Fallback'."""
        from datetime import datetime

        now = datetime.now()
        current_minutes = now.hour * 60 + now.minute
        weekday_names = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        weekday = weekday_names[now.weekday()]

        day_schedule = self._schedule.get(weekday, [])
        for entry in day_schedule:
            if not isinstance(entry, dict):
                continue
            if entry.get("start", 0) <= current_minutes < entry.get("end", 0):
                return "Active"

        return "Fallback"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        from datetime import datetime

        now = datetime.now()
        weekday_names = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        weekday = weekday_names[now.weekday()]
        day_schedule = self._schedule.get(weekday, [])

        return {
            "entries_today": len(day_schedule),
            "schedule_entries": [
                {
                    "start": e.get("start"),
                    "end": e.get("end"),
                    "target_temp": e.get("target_temperature", 0) / 10,
                }
                for e in day_schedule
                if isinstance(e, dict)
            ],
        }


class SinumScheduleAssociationCountSensor(SinumScheduleSensor):
    """Count of devices associated with schedule."""

    _attr_name = "Associated Devices"
    _attr_icon = "mdi:link"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: SinumCoordinator,
        schedule: dict[str, Any],
        entry_id: str,
    ) -> None:
        super().__init__(coordinator, schedule, entry_id, "assoc_count")

    @property
    def native_value(self) -> int:
        """Return count of associated thermostats and fan coils."""
        assoc = self._schedule.get("associations", {})
        return len(assoc.get("thermostats", [])) + len(assoc.get("fan_coils", []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        assoc = self._schedule.get("associations", {})
        return {
            "thermostats": assoc.get("thermostats", []),
            "fan_coils": assoc.get("fan_coils", []),
        }


class SinumButtonSensor(CoordinatorEntity[SinumCoordinator], SensorEntity):
    """Last-action sensor for WTP/SBUS button devices (diagnostic fallback)."""

    _attr_has_entity_name = True
    _attr_translation_key = "button_last_action"
    _attr_icon = "mdi:gesture-tap-button"
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: SinumCoordinator,
        device_id: int,
        entry_id: str,
        bus: str,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._bus = bus
        self._attr_unique_id = f"{entry_id}_{bus}_{device_id}_last_action"
        store = coordinator.wtp_devices if bus == "wtp" else coordinator.sbus_devices
        device = store.get(device_id, {})
        label = device.get("_device_name") or device.get("name", str(device_id))
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{bus}_{device_id}")},
            name=label,
            manufacturer="TECH Sterowniki",
            model=device.get("_parent_model") or f"Sinum {bus.upper()} Button",
            suggested_area=device.get("_area") or None,
        )

    @property
    def _device(self) -> dict[str, Any]:
        store = (
            self.coordinator.wtp_devices if self._bus == "wtp" else self.coordinator.sbus_devices
        )
        return store.get(self._device_id, {})

    @property
    def native_value(self) -> str | None:
        action = self._device.get("action")
        if action is None:
            return None
        return str(action) if action != "" else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self._device
        attrs: dict[str, Any] = {"buttons_count": d.get("buttons_count", 1)}
        if "buzzer" in d:
            attrs["buzzer"] = d["buzzer"]
        return attrs
