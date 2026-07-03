"""Hub diagnostic sensors (uptime, Wi-Fi, firmware version)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfTime,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SinumCoordinator

_MODEL_MAP: dict[str, str] = {
    "sinum_pro": "Sinum Pro",
    "sinum_lite": "Sinum Lite",
    "sinum": "Sinum EH-01",
}


def _hub_device_info(entry_id: str, hub_info: dict[str, Any]) -> DeviceInfo:
    device_type = hub_info.get("device_type", "")
    name = hub_info.get("name", "Sinum Hub")
    model = _MODEL_MAP.get(device_type, "Sinum EH-01")
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


class SinumHubFirmwareSensor(CoordinatorEntity[SinumCoordinator], SensorEntity):
    """Hub firmware version sensor."""

    _attr_has_entity_name = True
    _attr_translation_key = "hub_firmware"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:chip"

    def __init__(self, coordinator: SinumCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_hub_firmware"
        self._attr_device_info = _hub_device_info(entry_id, coordinator.hub_info)

    @property
    def native_value(self) -> str | None:
        return self.coordinator.hub_info.get("version")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        info = self.coordinator.hub_info
        attrs: dict[str, Any] = {}
        if dev_type := info.get("device_type"):
            attrs["device_type"] = dev_type
        if api_ver := info.get("api"):
            attrs["api_version"] = api_ver
        return attrs
