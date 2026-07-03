"""Shared helpers for cover entity modules."""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import ATTR_CURRENT_POSITION, ATTR_CURRENT_TILT_POSITION
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, MANUFACTURER
from .coordinator import SinumCoordinator


def _label(device: dict[str, Any]) -> str:
    return (device.get("_device_name") or device.get("name", "")).strip()


def _virtual_device_info(
    coordinator: SinumCoordinator, device_id: int, entry_id: str, model: str
) -> DeviceInfo:
    device = coordinator.virtual_devices.get(device_id, {})
    label = _label(device)
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_virtual_{device_id}")},
        name=label,
        manufacturer=MANUFACTURER,
        model=model,
        suggested_area=device.get("_area") or None,
    )


def _apply_restored_position(entity: Any, last: Any) -> None:
    if (v := last.attributes.get(ATTR_CURRENT_POSITION)) is not None:
        entity._attr_current_cover_position = int(v)


def _apply_restored_tilt(entity: Any, last: Any) -> None:
    if (v := last.attributes.get(ATTR_CURRENT_TILT_POSITION)) is not None:
        entity._attr_current_cover_tilt_position = int(v)


async def _restore_cover_from_last_state(entity: Any, restore_tilt: bool) -> None:
    last = await entity.async_get_last_state()
    if last is None or last.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return
    _apply_restored_position(entity, last)
    if restore_tilt:
        _apply_restored_tilt(entity, last)


def _compare_target_current(d: dict[str, Any]) -> int | None:
    """Return (target - current) opening delta, or None if values are missing/invalid."""
    target = d.get("target_opening")
    current = d.get("current_opening")
    if target is None or current is None:
        return None
    try:
        return int(target) - int(current)
    except (TypeError, ValueError):
        return None
