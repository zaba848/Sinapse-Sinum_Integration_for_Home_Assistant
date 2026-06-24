from __future__ import annotations

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
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SinumCoordinator, SinumDeviceAvailableMixin, via_device_for

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


class SinumSensor(SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator], SensorEntity):
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
        via = via_device_for(device, entry_id)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{self._source}_{device_id}")},
            name=label,
            manufacturer="TECH Sterowniki",
            model=device.get("_parent_model") or _model_for_source(self._source),
            suggested_area=device.get("_area") or None,
            via_device=via,
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
        if raw == 0 and (
            self.entity_description.zero_is_unavailable or self._device.get("status") == "offline"
        ):
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


class SinumButtonSensor(
    SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator], SensorEntity
):
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
