from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import (
    DEGREE,
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfEnergy,
    UnitOfIrradiance,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import SinumConnectionError
from .const import DOMAIN
from .coordinator import SinumCoordinator
from .sensor_bus import _SENTINEL_INT16, SinumSensorDescription

_LOGGER = logging.getLogger(__name__)

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
        zero_is_unavailable=True,
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
        zero_is_unavailable=True,
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


# ── Extended API diagnostics ───────────────────────────────────────────────────

_OUTPUT_GROUP_KEYS = (
    "outputs",
    "devices",
    "associated_devices",
    "associations",
    "output_ids",
    "device_ids",
    "groups",
)


def _count_items(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, dict):
        if not value:
            return 0
        if any(isinstance(item, (dict, list, tuple, set)) for item in value.values()):
            return sum(_count_items(item) for item in value.values())
        return len(value)
    if isinstance(value, (list, tuple, set)):
        return len(value)
    return 1


class SinumThermostatOutputGroupSensor(CoordinatorEntity[SinumCoordinator], SensorEntity):
    """Diagnostic count for thermostat output groups."""

    _attr_has_entity_name = True
    _attr_translation_key = "thermostat_output_group"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:home-thermometer-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: SinumCoordinator,
        device_id: int,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_virtual_{device_id}_output_group"
        device = coordinator.virtual_devices.get(device_id, {})
        label = device.get("_device_name") or device.get("name", str(device_id))
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_virtual_{device_id}")},
            name=label,
            manufacturer="TECH Sterowniki",
            model="Sinum Virtual Device",
        )

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.virtual_devices.get(self._device_id, {})

    @property
    def native_value(self) -> int:
        for key in _OUTPUT_GROUP_KEYS:
            if key in self._device:
                return _count_items(self._device.get(key))
        return 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "device_id": self._device_id,
            "output_count": self.native_value,
        }
        for key in ("name", "room_id", "state", "enabled", "mode", "class", "source"):
            if key in self._device:
                attrs[key] = self._device[key]
        return attrs


class SinumAutomationStatusSensor(CoordinatorEntity[SinumCoordinator], SensorEntity):
    """Read-only automation status from the Sinum automation API."""

    _attr_has_entity_name = True
    _attr_translation_key = "automation_status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:script-text-outline"

    def __init__(
        self,
        coordinator: SinumCoordinator,
        automation: dict[str, Any],
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._initial_automation = automation
        self._automation_id = automation.get("id")
        self._attr_unique_id = f"{entry_id}_automation_{self._automation_id}_status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_automations")},
            name="Sinum Automations",
            manufacturer="TECH Sterowniki",
            model="Sinum Automation API",
        )

    @property
    def _automation(self) -> dict[str, Any]:
        for automation in getattr(self.coordinator, "automations", []):
            if str(automation.get("id")) == str(self._automation_id):
                return automation
        return self._initial_automation

    @property
    def native_value(self) -> str:
        for key in ("enabled", "is_enabled", "active"):
            value = self._automation.get(key)
            if isinstance(value, bool):
                return "enabled" if value else "disabled"
        state = self._automation.get("state") or self._automation.get("status")
        return str(state) if state is not None else "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {"automation_id": self._automation_id}
        for key in ("name", "directory_id", "folder_id", "tags"):
            if key in self._automation:
                attrs[key] = self._automation[key]
        return attrs


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
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_energy")},
            name="Sinum Energy Center",
            manufacturer="TECH Sterowniki",
            model="Sinum EH-01 Energy",
        )

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
        except SinumConnectionError as err:
            _LOGGER.warning("Energy Center status update failed: %s", err)


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
