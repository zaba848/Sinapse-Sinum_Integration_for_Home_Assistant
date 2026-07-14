from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SinumConfigEntry
from ._bus_registry import bus_store as _shared_bus_store
from .const import DOMAIN, MANUFACTURER, STYPE_BUTTON, WTYPE_BUTTON
from .coordinator import SinumCoordinator, hub_prefixed_name

PARALLEL_UPDATES = 0


def _detect_button_press(action: Any, count: Any, prev_action: Any, prev_count: Any) -> str | None:
    """Return the action string if WTP-style press is detected, else None."""
    if not _is_valid_action(action):
        return None
    if _action_or_count_changed(action, count, prev_action, prev_count):
        return action
    return None


def _is_valid_action(action: Any) -> bool:
    return isinstance(action, str) and bool(action)


def _action_or_count_changed(action: Any, count: Any, prev_action: Any, prev_count: Any) -> bool:
    if action != prev_action:
        return True
    return count is not None and count != prev_count


def _count_only_press(count: Any, prev_count: Any) -> bool:
    return count is not None and count != prev_count


def _button_store(coordinator: SinumCoordinator, bus: str) -> dict[int, dict[str, Any]]:
    store = _shared_bus_store(coordinator, bus)
    return coordinator.wtp_devices if store is None else store


def _button_event_device_info(
    device: dict[str, Any],
    entry_id: str,
    bus: str,
    device_id: int,
    coordinator: SinumCoordinator,
) -> DeviceInfo:
    label = device.get("_device_name") or device.get("name", str(device_id))
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_{bus}_{device_id}")},
        name=hub_prefixed_name(coordinator, label),
        manufacturer=MANUFACTURER,
        model=device.get("_parent_model") or f"Sinum {bus.upper()} Button",
        suggested_area=device.get("_area") or None,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinumCoordinator = entry.runtime_data
    entities: list[EventEntity] = []

    _add_button_events(
        coordinator,
        entry.entry_id,
        entities,
        coordinator.wtp_devices,
        WTYPE_BUTTON,
        "wtp",
    )
    _add_button_events(
        coordinator,
        entry.entry_id,
        entities,
        coordinator.sbus_devices,
        STYPE_BUTTON,
        "sbus",
    )

    # Add motion event entities for video cameras
    _add_motion_events(coordinator, entry.entry_id, entities)

    async_add_entities(entities)


def _add_button_events(
    coordinator: SinumCoordinator,
    entry_id: str,
    entities: list[EventEntity],
    device_store: dict[int, dict[str, Any]],
    expected_type: str,
    bus: str,
) -> None:
    for device_id, device in device_store.items():
        if device.get("type") != expected_type:
            continue
        entities.append(SinumButtonEvent(coordinator, device_id, entry_id, bus))


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
        device = _button_store(coordinator, bus).get(device_id, {})
        self._attr_device_info = _button_event_device_info(
            device, entry_id, bus, device_id, coordinator
        )
        self._prev_action: str | None = device.get("action")
        self._prev_count: int | None = device.get("buttons_count")

    @property
    def _device(self) -> dict[str, Any]:
        return _button_store(self.coordinator, self._bus).get(self._device_id, {})

    @callback
    def _handle_coordinator_update(self) -> None:
        device = self._device
        action, count = device.get("action"), device.get("buttons_count")
        fired_action = _detect_button_press(action, count, self._prev_action, self._prev_count)
        if fired_action is not None:
            self._prev_action = action
            self._prev_count = count
            self._trigger_event("pressed", {"action": fired_action, "buttons_count": count})
        elif _count_only_press(count, self._prev_count):
            # SBUS: hub resets action to '' before next poll — count is the only signal.
            self._prev_count = count
            self._trigger_event("pressed", {"action": None, "buttons_count": count})
        self.async_write_ha_state()


def _add_motion_events(
    coordinator: SinumCoordinator,
    entry_id: str,
    entities: list[EventEntity],
) -> None:
    """Add motion event entities for video camera devices."""
    # Check if coordinator has video devices (from virtual device family)
    if hasattr(coordinator, "virtual_devices"):
        for device_id, device in coordinator.virtual_devices.items():
            if device.get("type") in ("ip_camera", "onvif_camera"):
                entities.append(SinumMotionEvent(coordinator, device_id, entry_id))


class SinumMotionEvent(CoordinatorEntity[SinumCoordinator], EventEntity):
    """Motion detection event entity — fires 'motion_detected' on motion events."""

    _attr_has_entity_name = True
    _attr_translation_key = "motion_detected"
    _attr_icon = "mdi:motion-sensor"
    _attr_event_types = ["motion_detected"]

    def __init__(
        self,
        coordinator: SinumCoordinator,
        device_id: int,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_motion_{device_id}"
        device = coordinator.virtual_devices.get(device_id, {})
        label = device.get("_device_name") or device.get("name", str(device_id))
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_video_{device_id}")},
            name=hub_prefixed_name(coordinator, label),
            manufacturer=MANUFACTURER,
            model=device.get("_parent_model") or "Sinum Video Camera",
            suggested_area=device.get("_area") or None,
        )
        self._last_motion_time: float | None = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Check for motion events from WebSocket."""
        motion_event = self.coordinator.get_motion_event(self._device_id)
        if motion_event:
            timestamp = motion_event.get("timestamp")
            self._trigger_event("motion_detected", {"timestamp": timestamp})
            self.async_write_ha_state()
