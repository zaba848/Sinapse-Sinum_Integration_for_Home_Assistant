"""Energy Center detail sensors (flow, consumption, production, storage, status)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.helpers.device_registry import DeviceInfo

from .api import SinumConnectionError, SinumNotSupportedError
from .const import DOMAIN, MANUFACTURER

_LOGGER = logging.getLogger(__name__)

_EC_CANDIDATE_FIELDS: tuple[str, ...] = (
    "power",
    "power_kw",
    "value",
    "value_kwh",
    "total",
    "total_kwh",
    "energy_kwh",
    "current_power",
)


def _ec_first_numeric(data: dict[str, Any]) -> float | None:
    for field in _EC_CANDIDATE_FIELDS:
        v = data.get(field)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def _ec_traverse(data: Any, path: tuple[str, ...]) -> Any:
    for key in path:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def _energy_center_device_info(entry_id: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_energy")},
        name="Sinum Energy Center",
        manufacturer=MANUFACTURER,
        model="Sinum EH-01 Energy",
    )


class SinumEnergyCenterStatusSensor(SensorEntity):
    """Diagnostic summary for /energy-center endpoints."""

    _attr_has_entity_name = True
    _attr_translation_key = "energy_center_status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:transmission-tower"

    def __init__(self, client: Any, initial: dict[str, Any], entry_id: str) -> None:
        self._client = client
        self._data = initial
        self._attr_unique_id = f"{entry_id}_energy_center_status"
        self._attr_device_info = _energy_center_device_info(entry_id)

    @property
    def native_value(self) -> int:
        available = self._data.get("available_endpoints", [])
        return len(available) if isinstance(available, list) else 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "available_endpoints": self._data.get("available_endpoints", []),
            "missing_endpoints": self._data.get("missing_endpoints", []),
        }

    async def async_update(self) -> None:
        try:
            self._data = await self._client.get_energy_center_summary()
        except (SinumConnectionError, SinumNotSupportedError) as err:
            _LOGGER.warning("Energy Center status update failed: %s", err)


class SinumEnergyCenterFlowSensor(SensorEntity):
    """Current power from the Energy Center flow monitor endpoint."""

    _attr_has_entity_name = True
    _attr_translation_key = "energy_center_flow_power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_suggested_display_precision = 0

    def __init__(self, client: Any, initial: dict[str, Any], entry_id: str) -> None:
        self._client = client
        self._data = initial
        self._attr_unique_id = f"{entry_id}_energy_center_flow_power"
        self._attr_device_info = _energy_center_device_info(entry_id)

    @property
    def native_value(self) -> float | None:
        v = self._data.get("summary", {}).get("building", {}).get("value")
        return float(v) if isinstance(v, (int, float)) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self._data
        return {
            "pv_power": _ec_traverse(d, ("summary", "pv", "value")),
            "grid_power": _ec_traverse(d, ("summary", "grid", "value")),
            "battery_power": _ec_traverse(d, ("summary", "battery", "value")),
            "battery_soc": _ec_traverse(d, ("summary", "battery", "state_of_charge", "value")),
        }

    async def async_update(self) -> None:
        try:
            self._data = await self._client.get_energy_center_flow_monitor()
        except (SinumConnectionError, SinumNotSupportedError) as err:
            _LOGGER.warning("Energy Center flow update failed: %s", err)


class SinumEnergyCenterDataSensor(SensorEntity):
    """Sensor for energy-center consumption / production endpoint data.

    value_path navigates nested keys to find the primary numeric value;
    extra_state_attributes exposes the full raw response for inspection.
    Falls back to _ec_first_numeric when no value_path is given.
    """

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        client: Any,
        initial: dict[str, Any],
        entry_id: str,
        unique_suffix: str,
        translation_key: str,
        icon: str,
        getter: Any,
        value_path: tuple[str, ...] = (),
    ) -> None:
        self._client = client
        self._data = initial
        self._getter = getter
        self._value_path = value_path
        self._attr_translation_key = translation_key
        self._attr_icon = icon
        self._attr_unique_id = f"{entry_id}_energy_center_{unique_suffix}"
        self._attr_device_info = _energy_center_device_info(entry_id)

    @property
    def native_value(self) -> float | None:
        if not self._value_path:
            return _ec_first_numeric(self._data)
        v = _ec_traverse(self._data, self._value_path)
        return float(v) if isinstance(v, (int, float)) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return dict(self._data)

    async def async_update(self) -> None:
        try:
            self._data = await self._getter()
        except (SinumConnectionError, SinumNotSupportedError) as err:
            _LOGGER.warning("Energy Center data update failed: %s", err)


# ── Energy Storage sensors (battery) ──────────────────────────────────────────

STORAGE_SENSORS: tuple[tuple[str, str, str, tuple[str, ...], Any, Any, Any], ...] = (
    # (unique_suffix, translation_key, icon, value_path, device_class, state_class, unit)
    (
        "storage_soc",
        "energy_storage_soc",
        "mdi:battery",
        ("state_of_charge", "value"),
        SensorDeviceClass.BATTERY,
        SensorStateClass.MEASUREMENT,
        PERCENTAGE,
    ),
    (
        "storage_power",
        "energy_storage_power",
        "mdi:battery-charging",
        ("power",),
        SensorDeviceClass.POWER,
        SensorStateClass.MEASUREMENT,
        UnitOfPower.WATT,
    ),
    (
        "storage_charged_today",
        "energy_storage_charged_today",
        "mdi:battery-plus",
        ("energy_charged_today",),
        SensorDeviceClass.ENERGY,
        SensorStateClass.MEASUREMENT,
        UnitOfEnergy.WATT_HOUR,
    ),
    (
        "storage_discharged_today",
        "energy_storage_discharged_today",
        "mdi:battery-minus",
        ("energy_discharged_today",),
        SensorDeviceClass.ENERGY,
        SensorStateClass.MEASUREMENT,
        UnitOfEnergy.WATT_HOUR,
    ),
)


class SinumEnergyStorageSensor(SensorEntity):
    """Sensor for a single field from the energy-center/energy-storage endpoint."""

    _attr_has_entity_name = True

    def __init__(
        self,
        client: Any,
        initial: dict[str, Any],
        entry_id: str,
        unique_suffix: str,
        translation_key: str,
        icon: str,
        value_path: tuple[str, ...],
        device_class: Any,
        state_class: Any,
        unit: Any,
    ) -> None:
        self._client = client
        self._data = initial
        self._value_path = value_path
        self._attr_translation_key = translation_key
        self._attr_icon = icon
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_native_unit_of_measurement = unit
        self._attr_unique_id = f"{entry_id}_energy_{unique_suffix}"
        self._attr_device_info = _energy_center_device_info(entry_id)

    @property
    def native_value(self) -> float | None:
        v = _ec_traverse(self._data, self._value_path)
        return float(v) if isinstance(v, (int, float)) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        status = self._data.get("status")
        available = self._data.get("available")
        attrs: dict[str, Any] = {}
        if status is not None:
            attrs["status"] = status
        if available is not None:
            attrs["available"] = available
        return attrs

    async def async_update(self) -> None:
        try:
            self._data = await self._client.get_energy_center_storage()
        except (SinumConnectionError, SinumNotSupportedError) as err:
            _LOGGER.warning("Energy Storage update failed: %s", err)


class SinumEnergyStorageStatusSensor(SensorEntity):
    """Text-state status sensor for the battery storage (idle/charging/discharging)."""

    _attr_has_entity_name = True
    _attr_translation_key = "energy_storage_status"
    _attr_icon = "mdi:battery-heart-outline"

    def __init__(self, client: Any, initial: dict[str, Any], entry_id: str) -> None:
        self._client = client
        self._data = initial
        self._attr_unique_id = f"{entry_id}_energy_storage_status"
        self._attr_device_info = _energy_center_device_info(entry_id)

    @property
    def native_value(self) -> str | None:
        return self._data.get("status")

    async def async_update(self) -> None:
        try:
            self._data = await self._client.get_energy_center_storage()
        except (SinumConnectionError, SinumNotSupportedError) as err:
            _LOGGER.warning("Energy Storage status update failed: %s", err)
