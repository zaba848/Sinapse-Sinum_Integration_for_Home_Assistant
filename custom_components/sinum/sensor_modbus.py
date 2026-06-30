"""Sensor entities for Modbus devices (e.g. DSMR P1 energy meters)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SinumCoordinator, SinumDeviceAvailableMixin


@dataclass(frozen=True, kw_only=True)
class SinumModbusSensorDescription(SensorEntityDescription):
    """Description for a single field on a Modbus device."""

    # Dot-path into the device dict, e.g. "phase_1.voltage" or "total_active_power"
    field_path: str
    scale: float = 1.0


# ── DSMR P1 energy meter sensor descriptions ──────────────────────────────────
# Values from the hub are already in SI units (W, V, A, Wh) — no scaling needed.
# The device is read-only; all sensors are disabled by default since the modbus
# controller may be offline on installations that don't use it.

_MODBUS_ENERGY_METER_SENSORS: tuple[SinumModbusSensorDescription, ...] = (
    SinumModbusSensorDescription(
        key="total_active_power",
        field_path="total_active_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        translation_key="active_power",
    ),
    SinumModbusSensorDescription(
        key="power_from_grid",
        field_path="power_from_grid",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        translation_key="power_from_grid",
    ),
    SinumModbusSensorDescription(
        key="power_to_grid",
        field_path="power_to_grid",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        translation_key="power_to_grid",
    ),
    SinumModbusSensorDescription(
        key="energy_consumed_total",
        field_path="energy_consumed_total",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        translation_key="energy_consumed_total",
    ),
    SinumModbusSensorDescription(
        key="energy_fed_total",
        field_path="energy_fed_total",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        translation_key="energy_fed_total",
    ),
    # Per-phase sensors — unique translation_key per phase to avoid entity_id collision
    SinumModbusSensorDescription(
        key="phase_1_voltage",
        field_path="phase_1.voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        translation_key="phase_1_voltage",
    ),
    SinumModbusSensorDescription(
        key="phase_2_voltage",
        field_path="phase_2.voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        translation_key="phase_2_voltage",
    ),
    SinumModbusSensorDescription(
        key="phase_3_voltage",
        field_path="phase_3.voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        translation_key="phase_3_voltage",
    ),
    SinumModbusSensorDescription(
        key="phase_1_current",
        field_path="phase_1.current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        translation_key="phase_1_current",
    ),
    SinumModbusSensorDescription(
        key="phase_2_current",
        field_path="phase_2.current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        translation_key="phase_2_current",
    ),
    SinumModbusSensorDescription(
        key="phase_3_current",
        field_path="phase_3.current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        translation_key="phase_3_current",
    ),
    SinumModbusSensorDescription(
        key="phase_1_active_power",
        field_path="phase_1.active_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        translation_key="phase_1_active_power",
    ),
    SinumModbusSensorDescription(
        key="phase_2_active_power",
        field_path="phase_2.active_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        translation_key="phase_2_active_power",
    ),
    SinumModbusSensorDescription(
        key="phase_3_active_power",
        field_path="phase_3.active_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        translation_key="phase_3_active_power",
    ),
    SinumModbusSensorDescription(
        key="tariff_indicator",
        field_path="tariff_indicator",
        device_class=None,
        state_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:cash-clock",
        translation_key="tariff_indicator",
    ),
)

# ── Heat pump sensor descriptions ─────────────────────────────────────────────
# Temperatures from TECH modbus are in 0.1 °C (scale=0.1). Frequencies in Hz.

_MODBUS_HEAT_PUMP_SENSORS: tuple[SinumModbusSensorDescription, ...] = (
    SinumModbusSensorDescription(
        key="temperature_outdoor",
        field_path="temperature_outdoor",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        scale=0.1,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        translation_key="temperature_outdoor",
    ),
    SinumModbusSensorDescription(
        key="heating_supply",
        field_path="heating_supply",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        scale=0.1,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        translation_key="heating_supply",
    ),
    SinumModbusSensorDescription(
        key="heating_return",
        field_path="heating_return",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        scale=0.1,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        translation_key="heating_return",
    ),
    SinumModbusSensorDescription(
        key="buffer_temperature",
        field_path="buffer_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        scale=0.1,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        translation_key="buffer_temperature",
    ),
    SinumModbusSensorDescription(
        key="hot_gas_temperature",
        field_path="hot_gas_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        scale=0.1,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        translation_key="hot_gas_temperature",
    ),
    SinumModbusSensorDescription(
        key="compressor_percentage",
        field_path="compressor_percentage",
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        icon="mdi:heat-pump",
        translation_key="compressor_percentage",
    ),
    SinumModbusSensorDescription(
        key="running_hours",
        field_path="running_hours",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        translation_key="running_hours",
    ),
)

# ── Inverter sensor descriptions ───────────────────────────────────────────────

_MODBUS_INVERTER_SENSORS: tuple[SinumModbusSensorDescription, ...] = (
    SinumModbusSensorDescription(
        key="pv_total_active_power",
        field_path="pv_total_active_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        translation_key="pv_total_active_power",
    ),
    SinumModbusSensorDescription(
        key="grid_total_active_power",
        field_path="grid_total_active_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        translation_key="grid_total_active_power",
    ),
    SinumModbusSensorDescription(
        key="energy_produced_total",
        field_path="energy_produced_total",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        translation_key="energy_produced_total",
    ),
    SinumModbusSensorDescription(
        key="energy_produced_today",
        field_path="energy_produced_today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        translation_key="energy_produced_today",
    ),
    SinumModbusSensorDescription(
        key="energy_fed_today",
        field_path="energy_fed_today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        translation_key="energy_fed_today",
    ),
)

# ── Battery sensor descriptions ────────────────────────────────────────────────

_MODBUS_BATTERY_SENSORS: tuple[SinumModbusSensorDescription, ...] = (
    SinumModbusSensorDescription(
        key="soc",
        field_path="soc",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
    ),
    SinumModbusSensorDescription(
        key="charge_power",
        field_path="charge_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        translation_key="charge_power",
    ),
    SinumModbusSensorDescription(
        key="energy_charged_total",
        field_path="energy_charged_total",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        translation_key="energy_charged_total",
    ),
    SinumModbusSensorDescription(
        key="energy_discharged_total",
        field_path="energy_discharged_total",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        translation_key="energy_discharged_total",
    ),
)

# ── Car charger sensor descriptions ───────────────────────────────────────────

_MODBUS_CAR_CHARGER_SENSORS: tuple[SinumModbusSensorDescription, ...] = (
    SinumModbusSensorDescription(
        key="charge_power",
        field_path="charge_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        translation_key="charge_power",
    ),
    SinumModbusSensorDescription(
        key="current",
        field_path="current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
    ),
    SinumModbusSensorDescription(
        key="voltage",
        field_path="voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
    ),
    SinumModbusSensorDescription(
        key="energy_charged_total",
        field_path="energy_charged_total",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        translation_key="energy_charged_total",
    ),
    SinumModbusSensorDescription(
        key="energy_charged_today",
        field_path="energy_charged_today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        translation_key="energy_charged_today",
    ),
)

# ── DHW (domestic hot water) sensor descriptions ───────────────────────────────

_MODBUS_DHW_SENSORS: tuple[SinumModbusSensorDescription, ...] = (
    SinumModbusSensorDescription(
        key="temperature_domestic_hot_water",
        field_path="temperature_domestic_hot_water",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        scale=0.1,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        translation_key="temperature_domestic_hot_water",
    ),
    SinumModbusSensorDescription(
        key="target_temperature",
        field_path="target_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        scale=0.1,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        translation_key="target_temperature_dhw",
    ),
)

# Map device type → applicable sensor descriptions
_SENSOR_MAP: dict[str, tuple[SinumModbusSensorDescription, ...]] = {
    "energy_meter": _MODBUS_ENERGY_METER_SENSORS,
    "heat_pump": _MODBUS_HEAT_PUMP_SENSORS,
    "inverter": _MODBUS_INVERTER_SENSORS,
    "battery": _MODBUS_BATTERY_SENSORS,
    "car_charger": _MODBUS_CAR_CHARGER_SENSORS,
    "common_dhw_main": _MODBUS_DHW_SENSORS,
}


def _get_field(device: dict[str, Any], path: str) -> Any:
    """Read a dot-separated path from device dict, e.g. 'phase_1.voltage'."""
    parts = path.split(".")
    val: Any = device
    for part in parts:
        if not isinstance(val, dict):
            return None
        val = val.get(part)
    return val


class SinumModbusSensor(SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator]):
    """A single sensor field on a Modbus device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SinumCoordinator,
        device_id: int,
        entry_id: str,
        description: SinumModbusSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_modbus_{device_id}_{description.key}"
        device = coordinator.modbus_devices.get(device_id, {})
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_modbus_{device_id}")},
            name=device.get("name", f"Modbus {device_id}"),
            manufacturer="TECH Sterowniki",
            model="Sinum Modbus Energy Meter",
            sw_version=device.get("software_version"),
        )

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.modbus_devices.get(self._device_id, {})

    @property
    def native_value(self) -> float | int | str | None:
        val = _get_field(self._device, self.entity_description.field_path)
        if val is None:
            return None
        scale = self.entity_description.scale
        if scale != 1.0 and isinstance(val, (int, float)):
            return round(val * scale, 6)
        return val


def build_modbus_sensor_entities(
    coordinator: SinumCoordinator, entry_id: str
) -> list[SinumModbusSensor]:
    """Create sensor entities for all Modbus devices in the coordinator."""
    entities: list[SinumModbusSensor] = []
    for device_id, device in coordinator.modbus_devices.items():
        dev_type = device.get("type", "")
        descriptions = _SENSOR_MAP.get(dev_type)
        if descriptions is None:
            continue
        for desc in descriptions:
            entities.append(SinumModbusSensor(coordinator, device_id, entry_id, desc))
    return entities


# ── SLINK energy_meter sensor descriptions ────────────────────────────────────

_SLINK_ENERGY_METER_SENSORS: tuple[SinumModbusSensorDescription, ...] = (
    SinumModbusSensorDescription(
        key="active_power",
        field_path="active_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
    ),
    SinumModbusSensorDescription(
        key="current",
        field_path="current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=2,
    ),
    SinumModbusSensorDescription(
        key="energy_consumed_total",
        field_path="energy_consumed_total",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_display_precision=0,
    ),
    SinumModbusSensorDescription(
        key="energy_consumed_today",
        field_path="energy_consumed_today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_display_precision=0,
        translation_key="energy_consumed_today",
    ),
    SinumModbusSensorDescription(
        key="energy_consumed_yesterday",
        field_path="energy_consumed_yesterday",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_display_precision=0,
        translation_key="energy_consumed_yesterday",
    ),
)

_SLINK_SENSOR_MAP: dict[str, tuple[SinumModbusSensorDescription, ...]] = {
    "energy_meter": _SLINK_ENERGY_METER_SENSORS,
}


class SinumSlinkSensor(SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator]):
    """A single sensor field on a SLINK device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SinumCoordinator,
        device_id: int,
        entry_id: str,
        description: SinumModbusSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_slink_{device_id}_{description.key}"
        device = coordinator.slink_devices.get(device_id, {})
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_slink_{device_id}")},
            name=device.get("name", f"SLINK {device_id}"),
            manufacturer="TECH Sterowniki",
            model="Sinum SLINK Energy Meter",
            sw_version=device.get("software_version"),
        )

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.slink_devices.get(self._device_id, {})

    @property
    def native_value(self) -> float | int | str | None:
        val = _get_field(self._device, self.entity_description.field_path)
        if val is None:
            return None
        scale = self.entity_description.scale
        if scale != 1.0 and isinstance(val, (int, float)):
            return round(val * scale, 6)
        return val


def build_slink_sensor_entities(
    coordinator: SinumCoordinator, entry_id: str
) -> list[SinumSlinkSensor]:
    """Create sensor entities for all SLINK devices in the coordinator."""
    entities: list[SinumSlinkSensor] = []
    for device_id, device in coordinator.slink_devices.items():
        dev_type = device.get("type", "")
        descriptions = _SLINK_SENSOR_MAP.get(dev_type)
        if descriptions is None:
            continue
        for desc in descriptions:
            entities.append(SinumSlinkSensor(coordinator, device_id, entry_id, desc))
    return entities
