from __future__ import annotations

from typing import Any

from homeassistant.components.update import UpdateDeviceClass, UpdateEntity, UpdateEntityFeature
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SinumConfigEntry
from .const import DOMAIN
from .coordinator import SinumCoordinator, hub_prefixed_name

_UPDATING_STATUSES = {"downloading", "updating"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinumCoordinator = entry.runtime_data
    entities: list[UpdateEntity] = []

    for parent in coordinator.parent_devices:
        if parent.get("software_status") is not None or parent.get("version") is not None:
            entities.append(SinumParentDeviceUpdate(coordinator, parent, entry.entry_id))

    async_add_entities(entities)


class SinumParentDeviceUpdate(CoordinatorEntity[SinumCoordinator], UpdateEntity):
    """Firmware update tracker for a Sinum parent device."""

    _attr_has_entity_name = True
    _attr_translation_key = "parent_firmware"
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_supported_features = UpdateEntityFeature.PROGRESS

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
        self._attr_unique_id = f"{unique_key}_update"
        label = parent.get("name") or f"{parent_class} {self._parent_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unique_key)},
            name=hub_prefixed_name(coordinator, label),
            manufacturer="TECH Sterowniki",
            model=parent.get("model") or parent_class.replace("_", " ").title(),
            sw_version=parent.get("version"),
        )

    def _current(self) -> dict[str, Any]:
        for p in self.coordinator.parent_devices:
            if p.get("id") == self._parent_id:
                return p
        return {}

    @property
    def installed_version(self) -> str | None:
        return self._current().get("version")

    @property
    def latest_version(self) -> str | None:
        p = self._current()
        sw_status = p.get("software_status", "")
        if sw_status == "update_available":
            return p.get("update_version") or p.get("version")
        return p.get("version")

    @property
    def in_progress(self) -> bool | int:
        p = self._current()
        if p.get("software_status") in _UPDATING_STATUSES:
            progress = p.get("update_progress")
            if isinstance(progress, int):
                return progress
            return True
        return False
