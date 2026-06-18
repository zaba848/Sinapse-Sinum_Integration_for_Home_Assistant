"""Sinum notify platform — sends push notifications to the hub display."""
from __future__ import annotations

from typing import Any

from homeassistant.components.notify import NotifyEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SinumConfigEntry
from .const import DOMAIN
from .coordinator import SinumCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinumCoordinator = entry.runtime_data
    async_add_entities([SinumNotifyEntity(coordinator, entry.entry_id)])


class SinumNotifyEntity(CoordinatorEntity[SinumCoordinator], NotifyEntity):
    """Push notification entity — sends messages to the Sinum hub."""

    _attr_has_entity_name = True
    _attr_name = "Notification"
    _attr_icon = "mdi:bell-ring"
    _attr_unique_id: str

    def __init__(self, coordinator: SinumCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_notify"
        hub = coordinator.hub_info or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=hub.get("name", "Sinum Hub"),
            manufacturer="TECH Sterowniki",
            model=hub.get("model") or "Sinum Hub",
        )

    async def async_send_message(self, message: str, title: str | None = None, **kwargs: Any) -> None:
        await self.coordinator.client.send_notification(
            title=title or "Sinum",
            message=message,
        )
