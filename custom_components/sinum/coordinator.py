from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SinumClient, SinumConnectionError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Device classes present in the rooms device list
_WTP_CLASSES = {"wtp"}
_SBUS_CLASSES = {"sbus"}
_VIRTUAL_CLASSES = {"virtual"}
_LORA_CLASSES = {"lora"}


class SinumCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches all Sinum device state on each refresh cycle."""

    def __init__(self, hass: HomeAssistant, client: SinumClient, scan_interval: int) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.virtual_devices: dict[int, dict[str, Any]] = {}
        self.wtp_devices: dict[int, dict[str, Any]] = {}
        self.sbus_devices: dict[int, dict[str, Any]] = {}
        self.lora_devices: dict[int, dict[str, Any]] = {}
        self.rooms: list[dict[str, Any]] = []
        self.floors: dict[int, dict[str, Any]] = {}  # floor_id → {id, name, level}
        self.hub_info: dict[str, Any] = {}  # from /api/v1/info
        self.parent_devices: list[dict[str, Any]] = []  # flat list from /api/v1/parent-devices
        self.scenes: list[dict[str, Any]] = []  # buttons/scripts from /api/v1/scenes
        self.schedules: list[dict[str, Any]] = []  # thermal schedules from /api/v1/schedules
        self.automations: list[dict[str, Any]] = []  # scripts/automations from /api/v1/automations
        self.variables: list[dict[str, Any]] = []  # global Lua/environment variables
        self.alarm_zones: dict[int, dict[str, Any]] = {}  # alarm_zone id → device dict
        self.mqtt_bridge: Any | None = None  # set by __init__ if MQTT enabled

    def _apply_metadata_results(
        self,
        hub_info: Any,
        lua_info: Any,
        rooms: Any,
        floors_list: Any,
        parent_devices: Any,
        scenes: Any,
        schedules: Any,
        automations: Any,
        variables: Any,
    ) -> list[dict[str, Any]]:
        """Apply parallel metadata fetch results; returns effective rooms list."""
        if hub_info is not None:
            self.hub_info = hub_info
        elif not self.hub_info:
            raise UpdateFailed("Cannot reach Sinum hub: hub info unavailable")
        if lua_info:
            self.hub_info.update(lua_info)

        if rooms is not None:
            self.rooms = rooms

        if floors_list is not None:
            self.floors = {int(f["id"]): f for f in floors_list if "id" in f}

        for attr, value in (
            ("parent_devices", parent_devices),
            ("scenes", scenes),
            ("schedules", schedules),
            ("automations", automations),
            ("variables", variables),
        ):
            if value is not None:
                setattr(self, attr, value)

        return self.rooms

    async def _async_update_data(self) -> dict[str, Any]:
        # ── Group 1: metadata — all fetched in parallel ───────────────────────
        meta = await asyncio.gather(
            _safe_fetch(self.client.get_hub_info, "hub info"),
            _safe_fetch(self.client.get_lua_hub_info, "lua hub info"),
            _safe_fetch(self.client.get_rooms, "rooms", default=[]),
            _safe_fetch(self.client.get_floors, "floors", default=[]),
            _safe_fetch(
                self.client.get_parent_devices, "parent devices", default=self.parent_devices
            ),
            _safe_fetch(self.client.get_scenes, "scenes", default=self.scenes),
            _safe_fetch(self.client.get_schedules, "schedules", default=self.schedules),
            _safe_fetch(self.client.get_automations, "automations", default=self.automations),
            _safe_fetch(self.client.get_variables, "variables", default=self.variables),
        )
        rooms = self._apply_metadata_results(*meta)

        # ── Classify device IDs from rooms and parent-device trees ────────────
        room_ids = _collect_device_ids(rooms)
        parent_ids = _collect_device_ids(self.parent_devices)
        virtual_ids, wtp_ids, sbus_ids, lora_ids = (
            _unique_ids([*room_ids[0], *parent_ids[0]]),
            _unique_ids([*room_ids[1], *parent_ids[1]]),
            _unique_ids([*room_ids[2], *parent_ids[2]]),
            _unique_ids([*room_ids[3], *parent_ids[3]]),
        )

        # ── Group 2: device collections — all fetched in parallel ─────────────
        virtual, wtp, sbus, lora, alarm_list = await asyncio.gather(
            self._fetch_device_collection(
                "virtual",
                self.client.get_virtual_devices,
                self.client.get_virtual_device,
                virtual_ids,
                rooms,
                self.virtual_devices,
            ),
            self._fetch_device_collection(
                "WTP",
                self.client.get_wtp_devices,
                self.client.get_wtp_device,
                wtp_ids,
                rooms,
                self.wtp_devices,
            ),
            self._fetch_device_collection(
                "SBUS",
                self.client.get_sbus_devices,
                self.client.get_sbus_device,
                sbus_ids,
                rooms,
                self.sbus_devices,
            ),
            self._fetch_device_collection(
                "LoRa",
                self.client.get_lora_devices,
                self.client.get_lora_device,
                lora_ids,
                rooms,
                self.lora_devices,
            ),
            _safe_fetch(self.client.get_alarm_devices, "alarm devices", default=None),
        )

        self.virtual_devices = virtual
        self.wtp_devices = wtp
        self.sbus_devices = sbus
        self.lora_devices = lora

        if alarm_list:
            self.alarm_zones = {int(z["id"]): z for z in alarm_list if "id" in z}

        # ── Enrich child devices with parent hardware model and class ─────────
        parent_maps, parent_class_maps = _build_parent_maps(self.parent_devices)
        _inject_parent_models(wtp, "wtp", parent_maps, parent_class_maps)
        _inject_parent_models(sbus, "sbus", parent_maps, parent_class_maps)
        _inject_parent_models(lora, "lora", parent_maps, parent_class_maps)

        return {
            "virtual": virtual,
            "wtp": wtp,
            "sbus": sbus,
            "lora": lora,
            "scenes": self.scenes,
            "schedules": self.schedules,
            "automations": self.automations,
            "variables": self.variables,
        }

    def _process_bulk_devices(
        self,
        collection: list[Any],
        label: str,
        rooms: list[dict[str, Any]],
    ) -> dict[int, dict[str, Any]]:
        devices: dict[int, dict[str, Any]] = {}
        for device in collection:
            if not isinstance(device, dict):
                continue
            device_id = _device_id_as_int(device.get("id"))
            if device_id is None:
                continue
            device.setdefault("class", _source_from_label(label))
            _inject_room_keys(device, device_id, rooms, self.floors)
            devices[device_id] = device
        return devices

    async def _fetch_device_collection(
        self,
        label: str,
        list_getter: Any,
        item_getter: Any,
        fallback_ids: list[int],
        rooms: list[dict[str, Any]],
        cached: dict[int, dict[str, Any]],
    ) -> dict[int, dict[str, Any]]:
        """Fetch a class-wide device list, falling back to per-room IDs.

        When the bulk endpoint fails (hub unreachable), return the existing
        cached data unchanged to keep entities available during outages.
        The per-device fallback is only used when the bulk endpoint succeeds
        but returns an empty list (older firmware without a bulk endpoint).
        """
        bulk_ok = False
        try:
            collection = await list_getter()
            bulk_ok = True
        except Exception as err:
            _LOGGER.debug("Failed to fetch %s device collection: %s", label, err)
            collection = []

        if collection:
            return self._process_bulk_devices(collection, label, rooms)

        # Bulk failed (exception) → return cache to keep entities alive
        if not bulk_ok:
            return cached

        # Bulk succeeded but returned empty list → old firmware without bulk endpoint
        devices: dict[int, dict[str, Any]] = {}
        for device_id in fallback_ids:
            try:
                device = await item_getter(device_id)
                if not isinstance(device, dict):
                    continue
                device.setdefault("class", _source_from_label(label))
                _inject_room_keys(device, device_id, rooms, self.floors)
                devices[device_id] = device
            except SinumConnectionError as err:
                _LOGGER.warning("Failed to fetch %s device %s: %s", label, device_id, err)
        return devices


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _safe_fetch(coro_fn: Any, label: str, default: Any = None) -> Any:
    """Call an async API method, returning default on any non-cancellation error."""
    try:
        return await coro_fn()
    except Exception as err:
        _LOGGER.debug("Failed to fetch %s: %s", label, err)
        return default


_CLASS_BUCKET_INDEX: dict[str, int] = {
    **{cls: 0 for cls in _VIRTUAL_CLASSES},
    **{cls: 1 for cls in _WTP_CLASSES},
    **{cls: 2 for cls in _SBUS_CLASSES},
    **{cls: 3 for cls in _LORA_CLASSES},
}


def _collect_device_ids(
    rooms: list[dict[str, Any]],
) -> tuple[list[int], list[int], list[int], list[int]]:
    """Return (virtual_ids, wtp_ids, sbus_ids, lora_ids) from rooms device listings."""
    buckets: list[list[int]] = [[], [], [], []]
    seen: set[tuple[str, int]] = set()

    for room in rooms:
        if not isinstance(room, dict):
            continue
        for device in room.get("devices", []):
            if not isinstance(device, dict):
                continue
            cls = _device_class(device)
            dev_id = _device_id_as_int(device.get("id"))
            if dev_id is None:
                continue
            key = (cls, dev_id)
            if key in seen:
                continue
            seen.add(key)
            bucket = _CLASS_BUCKET_INDEX.get(cls)
            if bucket is not None:
                buckets[bucket].append(dev_id)

    return buckets[0], buckets[1], buckets[2], buckets[3]


def _device_id_as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _device_class(device: dict[str, Any]) -> str:
    raw = device.get("class") or device.get("source") or device.get("bus") or ""
    cls = str(raw).lower()
    if cls.startswith("virtual"):
        return "virtual"
    if cls.startswith("wtp"):
        return "wtp"
    if cls.startswith("sbus"):
        return "sbus"
    if cls.startswith("lora"):
        return "lora"
    return cls


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
    for room in rooms:
        if not isinstance(room, dict):
            continue
        for dev in room.get("devices", []):
            if not isinstance(dev, dict):
                continue
            dev_id = _device_id_as_int(dev.get("id"))
            if dev_id == device_id and _device_class(dev) == device_class:
                return room, (dev.get("name") or "")
    return None, ""


def _inject_room_keys(
    device: dict[str, Any],
    device_id: int,
    rooms: list[dict[str, Any]],
    floors: dict[int, dict[str, Any]],
) -> None:
    """Inject _id, _room, _device_name, _floor_name, _area into device dict."""
    device["_id"] = device_id
    room_id = device.get("room_id")
    if room_id is not None:
        room = _find_room_by_id(rooms, room_id)
        if room is not None:
            _apply_room_keys(device, room, floors)
            return

    room, dev_name = _find_room_containing_device(rooms, device_id, _device_class(device))
    if room is not None:
        if dev_name:
            device["_device_name"] = dev_name
        _apply_room_keys(device, room, floors)
        return

    device.setdefault("_room", "")
    device.setdefault("_device_name", device.get("name", str(device_id)))
    device.setdefault("_floor_name", "")
    device.setdefault("_area", "")


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
    for room in rooms:
        if not isinstance(room, dict):
            continue
        for device in room.get("devices", []):
            if not isinstance(device, dict):
                continue
            if _device_id_as_int(device.get("id")) == device_id:
                return room.get("name", "")
    return ""


def _device_name_in_room(rooms: list[dict[str, Any]], device_id: int) -> str:
    for room in rooms:
        if not isinstance(room, dict):
            continue
        for device in room.get("devices", []):
            if not isinstance(device, dict):
                continue
            if _device_id_as_int(device.get("id")) == device_id:
                return device.get("name", str(device_id))
    return str(device_id)


def _build_parent_maps(
    parent_devices: list[dict[str, Any]],
) -> tuple[dict[str, dict[int, str]], dict[str, dict[int, str]]]:
    """Build bus-keyed maps from the parent-devices list.

    Returns (model_maps, class_maps) where each is {bus → {parent_id → value}}.
    """
    model_maps: dict[str, dict[int, str]] = {}
    class_maps: dict[str, dict[int, str]] = {}
    for p in parent_devices:
        cls = p.get("class", "")
        pid = p.get("id")
        model = p.get("model")
        if pid is not None and "_parent_device" in cls:
            bus = cls.split("_parent_device")[0]  # "sbus", "wtp", "lora"
            pid = int(pid)
            if model:
                model_maps.setdefault(bus, {})[pid] = model
            class_maps.setdefault(bus, {})[pid] = cls
    return model_maps, class_maps


def _inject_parent_models(
    devices: dict[int, dict[str, Any]],
    bus: str,
    parent_maps: dict[str, dict[int, str]],
    parent_class_maps: dict[str, dict[int, str]] | None = None,
) -> None:
    """Inject _parent_model and _parent_class from parent device info into child devices."""
    bus_map = parent_maps.get(bus, {})
    class_map = (parent_class_maps or {}).get(bus, {})
    if not bus_map and not class_map:
        return
    for device in devices.values():
        pid = device.get("parent_id")
        if pid is not None:
            pid = int(pid)
            model = bus_map.get(pid)
            if model:
                device["_parent_model"] = model
            cls = class_map.get(pid)
            if cls:
                device["_parent_class"] = cls
                device["_parent_id"] = pid


class SinumDeviceAvailableMixin:
    """Marks entity unavailable when its backing device is absent from the coordinator store.

    Mix in *before* CoordinatorEntity so MRO resolves available here first:
        class MyEntity(SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator], ...):
    """

    @property
    def available(self) -> bool:  # type: ignore[override]
        return super().available and bool(self._device)  # type: ignore[misc]


def via_device_for(device: dict[str, Any], entry_id: str) -> tuple[str, str] | None:
    """Return (DOMAIN, unique_key) for the parent hardware device, or None."""
    cls = device.get("_parent_class")
    pid = device.get("_parent_id")
    if cls and pid is not None:
        return (DOMAIN, f"{entry_id}_parent_{cls}_{pid}")
    return None
