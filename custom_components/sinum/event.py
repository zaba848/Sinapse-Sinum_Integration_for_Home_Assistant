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
        self._prev_count: int | None = device.get("buttons_count")

    @property
    def _device(self) -> dict[str, Any]:
        store = (
            self.coordinator.wtp_devices if self._bus == "wtp" else self.coordinator.sbus_devices
        )
        return store.get(self._device_id, {})

    @callback
    def _handle_coordinator_update(self) -> None:
        device = self._device
        action = device.get("action")
        count = device.get("buttons_count")

        action_valid = action is not None and action != ""
        action_changed = action_valid and action != self._prev_action
        # buttons_count increments on every press regardless of action type.
        count_changed = count is not None and count != self._prev_count

        if action_changed or (count_changed and action_valid):
            # WTP: action field persists → detected by action change or count (same-type repeat)
            self._prev_action = action
            self._prev_count = count
            self._trigger_event("pressed", {"action": action, "buttons_count": count})
        elif count_changed:
            # SBUS: hub resets action to '' before the next poll — count is the only signal.
            # Fire with action=None; use MQTT bridge for real-time action type detection.
            self._prev_count = count
            self._trigger_event("pressed", {"action": None, "buttons_count": count})

        self.async_write_ha_state()
