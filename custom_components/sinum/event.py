from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SinumConfigEntry
from .const import DOMAIN, STYPE_BUTTON, WTYPE_BUTTON
from .coordinator import SinumCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinumCoordinator = entry.runtime_data
    entities: list[EventEntity] = []

    for device_id, device in coordinator.wtp_devices.items():
        if device.get("type") == WTYPE_BUTTON:
            entities.append(SinumButtonEvent(coordinator, device_id, entry.entry_id, "wtp"))

    for device_id, device in coordinator.sbus_devices.items():
        if device.get("type") == STYPE_BUTTON:
            entities.append(SinumButtonEvent(coordinator, device_id, entry.entry_id, "sbus"))

    async_add_entities(entities)


class SinumButtonEvent(CoordinatorEntity[SinumCoordinator], EventEntity):
    """Button press event entity — fires 'pressed' on each action change."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "button_press"
    _attr_icon = "mdi:gesture-tap-button"
    _attr_event_types = ["pressed"]

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
        self._attr_unique_id = f"{entry_id}_{bus}_{device_id}_event"
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
        self._prev_action: str | None = device.get("action")

    @property
    def _device(self) -> dict[str, Any]:
        store = (
            self.coordinator.wtp_devices if self._bus == "wtp" else self.coordinator.sbus_devices
        )
        return store.get(self._device_id, {})

    @callback
    def _handle_coordinator_update(self) -> None:
        action = self._device.get("action")
        if action is not None and action != "" and action != self._prev_action:
            self._prev_action = action
            self._trigger_event("pressed", {"action": action})
        self.async_write_ha_state()
