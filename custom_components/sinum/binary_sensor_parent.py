"""Connectivity and problem binary sensors for Sinum parent devices."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import SinumCoordinator, hub_prefixed_name


class SinumParentOnlineSensor(CoordinatorEntity[SinumCoordinator], BinarySensorEntity):
    """Connectivity sensor for a Sinum parent device (WTP, SLINK, SBUS, etc.)."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "parent_online"
    _attr_icon = "mdi:router-network"

    def __init__(
        self,
        coordinator: SinumCoordinator,
        parent: dict[str, Any],
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._parent_id = parent.get("id")
        parent_class = parent.get("class", "device")
        unique_key = f"{entry_id}_parent_{parent_class}_{self._parent_id}"
        self._attr_unique_id = unique_key
        label = parent.get("name") or f"{parent_class} {self._parent_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unique_key)},
            name=hub_prefixed_name(coordinator, label),
            manufacturer=MANUFACTURER,
            model=parent.get("model") or parent_class.replace("_", " ").title(),
            sw_version=parent.get("version"),
        )

    def _current(self) -> dict[str, Any]:
        for p in self.coordinator.parent_devices:
            if p.get("id") == self._parent_id:
                return p
        return {}

    @property
    def is_on(self) -> bool | None:
        p = self._current()
        status = p.get("status")
        if status is None:
            return None
        return str(status).lower() == "online"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        p = self._current()
        return {
            "software_status": p.get("software_status"),
            "has_messages": p.get("has_messages"),
            "firmware_version": p.get("version"),
            "type": p.get("type"),
            "class": p.get("class"),
        }


class SinumParentErrorSensor(CoordinatorEntity[SinumCoordinator], BinarySensorEntity):
    """Problem sensor for a Sinum parent device — on when it has pending messages."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "parent_problem"
    _attr_icon = "mdi:alert-circle"

    def __init__(
        self,
        coordinator: SinumCoordinator,
        parent: dict[str, Any],
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._parent_id = parent.get("id")
        parent_class = parent.get("class", "device")
        unique_key = f"{entry_id}_parent_{parent_class}_{self._parent_id}_problem"
        self._attr_unique_id = unique_key
        label = parent.get("name") or f"{parent_class} {self._parent_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_parent_{parent_class}_{self._parent_id}")},
            name=hub_prefixed_name(coordinator, label),
            manufacturer=MANUFACTURER,
            model=parent.get("model") or parent_class.replace("_", " ").title(),
            sw_version=parent.get("version"),
        )

    def _current(self) -> dict[str, Any]:
        for p in self.coordinator.parent_devices:
            if p.get("id") == self._parent_id:
                return p
        return {}

    @property
    def is_on(self) -> bool | None:
        p = self._current()
        val = p.get("has_messages")
        if val is None:
            return None
        return bool(val)
