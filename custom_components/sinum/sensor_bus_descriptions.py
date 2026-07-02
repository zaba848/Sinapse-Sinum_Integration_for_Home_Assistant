"""Sensor entity descriptions for WTP, SBUS and LoRa bus devices.

Pure data — no HA entity classes here.  To add a new sensor field, extend one
of the *_SENSORS tuples below.  The matching entity class in sensor_bus.py
picks it up automatically via the `api_key in device` field-presence check.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    LIGHT_LUX,
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfPressure,
    UnitOfTemperature,
)

# Sinum hub encodes "no value / sensor error" as signed 16-bit minimum (-32768).
# Multiply by 0.1 scale → -3276.8°C. Treat this as unavailable.
_SENTINEL_INT16 = -32768


@dataclass(frozen=True, kw_only=True)
class SinumSensorDescription(SensorEntityDescription):
    api_key: str
    scale: float = 1.0
    source: str = "virtual"
    is_text: bool = False
    zero_is_unavailable: bool = False


# ── Shared WTP+SBUS sensor kwargs (source injected by _with_source) ────────────

_COMMON_SENSOR_KWARGS: tuple[dict, ...] = (
    dict(
        key="temperature",
        api_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        scale=0.1,
        suggested_display_precision=1,
    ),
    dict(
        key="humidity",
        api_key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        scale=0.1,
        suggested_display_precision=0,
    ),
    dict(
        key="illuminance",
        api_key="illuminance",
        device_class=SensorDeviceClass.ILLUMINANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=LIGHT_LUX,
        suggested_display_precision=0,
    ),
    dict(
        key="active_power",
        api_key="active_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        scale=0.001,
        suggested_display_precision=1,
    ),
    dict(
        key="voltage",
        api_key="voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        scale=0.001,
        suggested_display_precision=1,
    ),
    dict(
        key="current",
        api_key="current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        scale=0.001,
        suggested_display_precision=3,
    ),
    dict(
        key="energy_consumed_total",
        api_key="energy_consumed_total",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_display_precision=0,
    ),
    dict(
        key="energy_consumed_today",
        api_key="energy_consumed_today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_display_precision=0,
        translation_key="energy_consumed_today",
    ),
    dict(
        key="energy_consumed_yesterday",
        api_key="energy_consumed_yesterday",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_display_precision=0,
        translation_key="energy_consumed_yesterday",
    ),
)


def _with_source(source: str) -> tuple[SinumSensorDescription, ...]:
    return tuple(SinumSensorDescription(source=source, **kw) for kw in _COMMON_SENSOR_KWARGS)


# ── WTP device sensors ─────────────────────────────────────────────────────────

WTP_SENSORS: tuple[SinumSensorDescription, ...] = _with_source("wtp") + (
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
    # Temperature regulator sensors
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
        zero_is_unavailable=True,
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

SBUS_SENSORS: tuple[SinumSensorDescription, ...] = _with_source("sbus") + (
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
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SinumSensorDescription(
        key="pwm_frequency",
        api_key="frequency",
        source="sbus",
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="Hz",
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
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
