"""Pure utility functions for SinumCoordinator data processing.

These functions operate on dicts/lists and have no runtime dependency on
SinumCoordinator itself, so they can be tested in isolation and imported
without triggering any HA or API initialisation.
"""

from __future__ import annotations

import logging
from typing import Any

from .api import SinumAuthError

_LOGGER = logging.getLogger(__name__)

# Device classes present in the rooms device list
_WTP_CLASSES = {"wtp"}
_SBUS_CLASSES = {"sbus"}
_VIRTUAL_CLASSES = {"virtual"}
_LORA_CLASSES = {"lora"}

_CLASS_BUCKET_INDEX: dict[str, int] = {
    **{cls: 0 for cls in _VIRTUAL_CLASSES},
    **{cls: 1 for cls in _WTP_CLASSES},
    **{cls: 2 for cls in _SBUS_CLASSES},
    **{cls: 3 for cls in _LORA_CLASSES},
}

_KNOWN_CLASSES = ("virtual", "wtp", "sbus", "lora")


# ── Index helpers ──────────────────────────────────────────────────────────────


def _index_by_id(lst: list[Any]) -> dict[int, dict[str, Any]]:
    return {int(d["id"]): d for d in lst if "id" in d}


def _maybe_index_list(lst: list[Any] | None) -> dict[int, dict[str, Any]] | None:
    if not lst:
        return None
    return {int(d["id"]): d for d in lst if "id" in d}


def _apply_optional_stores(
    coordinator: Any,
    alarm: list[Any] | None,
    modbus: list[Any] | None,
    video: list[Any] | None,
    slink: list[Any] | None = None,
) -> None:
    updates = {
        "alarm_zones": alarm,
        "modbus_devices": modbus,
        "video_devices": video,
        "slink_devices": slink,
    }
    for attr, raw in updates.items():
        indexed = _maybe_index_list(raw)
        if indexed is not None:
            setattr(coordinator, attr, indexed)


# ── Async fetch helper ─────────────────────────────────────────────────────────


async def _safe_fetch(coro_fn: Any, label: str, default: Any = None) -> Any:
    """Call an async API method; returns default on errors, re-raises SinumAuthError."""
    try:
        return await coro_fn()
    except SinumAuthError:
        raise
    except Exception as err:
        _LOGGER.debug("Failed to fetch %s: %s", label, err)
        return default


# ── Device ID / class helpers ──────────────────────────────────────────────────


def _device_id_as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _device_class(device: dict[str, Any]) -> str:
    cls = _first_device_class_field(device)
    return next((p for p in _KNOWN_CLASSES if cls.startswith(p)), cls)


def _first_device_class_field(device: dict[str, Any]) -> str:
    for key in ("class", "source", "bus"):
        val = device.get(key)
        if val:
            return str(val).lower()
    return ""


def _source_from_label(label: str) -> str:
    return "lora" if label.lower() == "lora" else label.lower()


def _unique_ids(values: list[int]) -> list[int]:
    ids: list[int] = []
    seen: set[int] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ids.append(value)
    return ids


# ── Room traversal ─────────────────────────────────────────────────────────────


def _iter_room_devices(rooms: list[dict[str, Any]]):
    for room in rooms:
        yield from _room_devices(room)


def _iter_room_device_pairs(rooms: list[dict[str, Any]]):
    for room in rooms:
        for device in _room_devices(room):
            yield room, device


def _room_devices(room: Any):
    if not isinstance(room, dict):
        return ()
    devices = room.get("devices", [])
    if not isinstance(devices, list):
        return ()
    return _filter_dicts(devices)


def _filter_dicts(lst: list[Any]):
    return (item for item in lst if isinstance(item, dict))


# ── Device-to-room classification ─────────────────────────────────────────────


def _add_device_to_bucket(
    device: dict[str, Any],
    seen: set[tuple[str, int]],
    buckets: list[list[int]],
) -> None:
    cls = _device_class(device)
    dev_id = _device_id_as_int(device.get("id"))
    if dev_id is None:
        return
    key = (cls, dev_id)
    if key in seen:
        return
    seen.add(key)
    bucket = _CLASS_BUCKET_INDEX.get(cls)
    if bucket is not None:
        buckets[bucket].append(dev_id)


def _collect_device_ids(
    rooms: list[dict[str, Any]],
) -> tuple[list[int], list[int], list[int], list[int]]:
    """Return (virtual_ids, wtp_ids, sbus_ids, lora_ids) from rooms device listings."""
    buckets: list[list[int]] = [[], [], [], []]
    seen: set[tuple[str, int]] = set()
    for device in _iter_room_devices(rooms):
        _add_device_to_bucket(device, seen, buckets)
    return buckets[0], buckets[1], buckets[2], buckets[3]


# ── Room key injection ─────────────────────────────────────────────────────────


def _find_room_by_id(rooms: list[dict[str, Any]], room_id: Any) -> dict[str, Any] | None:
    target = int(room_id)
    for room in rooms:
        if int(room.get("id", -1)) == target:
            return room
    return None


def _find_room_containing_device(
    rooms: list[dict[str, Any]], device_id: int, device_class: str
) -> tuple[dict[str, Any] | None, str]:
    """Return (room, device_name_in_room) or (None, '') if not found."""
    for room, dev in _iter_room_device_pairs(rooms):
        if _device_matches(dev, device_id, device_class):
            return room, (dev.get("name") or "")
    return None, ""


def _device_matches(dev: dict[str, Any], device_id: int, device_class: str) -> bool:
    return _device_id_as_int(dev.get("id")) == device_id and _device_class(dev) == device_class


def _inject_room_from_explicit_id(
    device: dict[str, Any],
    rooms: list[dict[str, Any]],
    floors: dict[int, dict[str, Any]],
) -> bool:
    room_id = device.get("room_id")
    if room_id is None:
        return False
    room = _find_room_by_id(rooms, room_id)
    if room is None:
        return False
    _apply_room_keys(device, room, floors)
    return True


def _inject_room_from_lookup(
    device: dict[str, Any],
    device_id: int,
    rooms: list[dict[str, Any]],
    floors: dict[int, dict[str, Any]],
) -> bool:
    room, dev_name = _find_room_containing_device(rooms, device_id, _device_class(device))
    if room is None:
        return False
    if dev_name:
        device["_device_name"] = dev_name
    _apply_room_keys(device, room, floors)
    return True


def _inject_room_defaults(device: dict[str, Any], device_id: int) -> None:
    device.setdefault("_room", "")
    device.setdefault("_device_name", device.get("name", str(device_id)))
    device.setdefault("_floor_name", "")
    device.setdefault("_area", "")


def _inject_room_keys(
    device: dict[str, Any],
    device_id: int,
    rooms: list[dict[str, Any]],
    floors: dict[int, dict[str, Any]],
) -> None:
    """Inject _id, _room, _device_name, _floor_name, _area into device dict."""
    device["_id"] = device_id
    if _inject_room_from_explicit_id(device, rooms, floors):
        return
    if _inject_room_from_lookup(device, device_id, rooms, floors):
        return
    _inject_room_defaults(device, device_id)


def _apply_room_keys(
    device: dict[str, Any],
    room: dict[str, Any],
    floors: dict[int, dict[str, Any]],
) -> None:
    room_name: str = room.get("name", "")
    device["_room"] = room_name
    device.setdefault("_device_name", device.get("name", str(device.get("_id", ""))))

    floor_id = room.get("floor_id")
    floor_name = ""
    if floor_id is not None:
        floor = floors.get(int(floor_id))
        if floor:
            floor_name = floor.get("name", "")
    device["_floor_name"] = floor_name
    device["_area"] = f"{floor_name} / {room_name}" if floor_name else room_name


def _room_name_for_device(rooms: list[dict[str, Any]], device_id: int) -> str:
    for room, device in _iter_room_device_pairs(rooms):
        if _device_id_as_int(device.get("id")) == device_id:
            return room.get("name", "")
    return ""


def _device_name_in_room(rooms: list[dict[str, Any]], device_id: int) -> str:
    for _room, device in _iter_room_device_pairs(rooms):
        if _device_id_as_int(device.get("id")) == device_id:
            return device.get("name", str(device_id))
    return str(device_id)


# ── Parent device model injection ──────────────────────────────────────────────


def _parent_id(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _inject_parent_model_for_device(
    device: dict[str, Any],
    bus_map: dict[int, str],
    class_map: dict[int, str],
) -> None:
    pid = _parent_id(device.get("parent_id"))
    if pid is None:
        return
    model = bus_map.get(pid)
    if model:
        device["_parent_model"] = model
    cls = class_map.get(pid)
    if cls:
        device["_parent_class"] = cls
        device["_parent_id"] = pid


def _build_parent_maps(
    parent_devices: list[dict[str, Any]],
) -> tuple[dict[str, dict[int, str]], dict[str, dict[int, str]]]:
    """Build bus-keyed maps from the parent-devices list.

    Returns (model_maps, class_maps) where each is {bus → {parent_id → value}}.
    """
    model_maps: dict[str, dict[int, str]] = {}
    class_maps: dict[str, dict[int, str]] = {}
    for p in parent_devices:
        _accumulate_parent_entry(p, model_maps, class_maps)
    return model_maps, class_maps


def _accumulate_parent_entry(
    p: dict[str, Any],
    model_maps: dict[str, dict[int, str]],
    class_maps: dict[str, dict[int, str]],
) -> None:
    cls = p.get("class", "")
    pid = p.get("id")
    if pid is None or "_parent_device" not in cls:
        return
    bus = cls.split("_parent_device")[0]
    pid = int(pid)
    model = p.get("model")
    if model:
        model_maps.setdefault(bus, {})[pid] = model
    class_maps.setdefault(bus, {})[pid] = cls


def _inject_parent_models(
    devices: dict[int, dict[str, Any]],
    bus: str,
    parent_maps: dict[str, dict[int, str]],
    parent_class_maps: dict[str, dict[int, str]] | None = None,
) -> None:
    """Inject _parent_model and _parent_class from parent device info into child devices."""
    bus_map = parent_maps.get(bus, {})
    class_map = _map_for_bus(parent_class_maps, bus)
    if not bus_map and not class_map:
        return
    for device in devices.values():
        _inject_parent_model_for_device(device, bus_map, class_map)


def _map_for_bus(maps: dict[str, dict[int, str]] | None, bus: str) -> dict[int, str]:
    return maps.get(bus, {}) if maps else {}
