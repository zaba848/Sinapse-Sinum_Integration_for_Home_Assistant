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
        self.schedules: list[dict[str, Any]] = []  # thermal schedules from /api/v1/schedules
        self.alarm_zones: dict[int, dict[str, Any]] = {}  # alarm_zone id → device dict
        self.mqtt_bridge: Any | None = None  # set by __init__ if MQTT enabled

    async def _async_update_data(self) -> dict[str, Any]:
        # ── Group 1: metadata — all fetched in parallel ───────────────────────
        (
            hub_info,
            rooms,
            lua_info,
            floors_list,
            parent_devices,
            schedules,
        ) = await asyncio.gather(
            _safe_fetch(self.client.get_hub_info, "hub info"),
            _safe_fetch(self.client.get_rooms, "rooms", default=[]),
            _safe_fetch(self.client.get_lua_hub_info, "lua hub info"),
            _safe_fetch(self.client.get_floors, "floors", default=[]),
            _safe_fetch(
                self.client.get_parent_devices, "parent devices", default=self.parent_devices
            ),
            _safe_fetch(self.client.get_schedules, "schedules", default=self.schedules),
        )

        # Apply metadata results (fall back to cache on None/failure)
        if hub_info is not None:
            self.hub_info = hub_info
        elif not self.hub_info:
            raise UpdateFailed("Cannot reach Sinum hub: hub info unavailable")
        if lua_info:
            self.hub_info.update(lua_info)

        if rooms is not None:
            self.rooms = rooms
        rooms = self.rooms  # use cached if fetch failed

        if floors_list is not None:
            self.floors = {int(f["id"]): f for f in floors_list if "id" in f}
        if parent_devices is not None:
            self.parent_devices = parent_devices
        if schedules is not None:
            self.schedules = schedules

        # ── Classify device IDs from rooms (fallback for older firmware) ──────
        virtual_ids, wtp_ids, sbus_ids, lora_ids = _collect_device_ids(rooms)

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

        # ── Enrich child devices with parent hardware model ───────────────────
        parent_maps = _build_parent_maps(self.parent_devices)
        _inject_parent_models(wtp, "wtp", parent_maps)
        _inject_parent_models(sbus, "sbus", parent_maps)
        _inject_parent_models(lora, "lora", parent_maps)

        return {
            "virtual": virtual,
            "wtp": wtp,
            "sbus": sbus,
            "lora": lora,
            "schedules": self.schedules,
        }

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
        devices: dict[int, dict[str, Any]] = {}
        bulk_ok = False
        try:
            collection = await list_getter()
            bulk_ok = True
        except SinumConnectionError as err:
            _LOGGER.debug("Failed to fetch %s device collection: %s", label, err)
            collection = []

        if collection:
            for device in collection:
                device_id = device.get("id")
                if device_id is None:
                    continue
                device_id = int(device_id)
                _inject_room_keys(device, device_id, rooms, self.floors)
                devices[device_id] = device
            return devices

        # Bulk succeeded but returned empty → try per-device (old firmware).
        # Bulk failed → return cached data to avoid 400+ WARNING log entries.
        if not bulk_ok:
            return cached

        for device_id in fallback_ids:
            try:
                device = await item_getter(device_id)
                _inject_room_keys(device, device_id, rooms, self.floors)
                devices[device_id] = device
            except SinumConnectionError as err:
                _LOGGER.warning("Failed to fetch %s device %s: %s", label, device_id, err)
        return devices


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _safe_fetch(coro_fn: Any, label: str, default: Any = None) -> Any:
    """Call an async API method, returning default on SinumConnectionError."""
    try:
        return await coro_fn()
    except SinumConnectionError as err:
        _LOGGER.debug("Failed to fetch %s: %s", label, err)
        return default


def _collect_device_ids(
    rooms: list[dict[str, Any]],
) -> tuple[list[int], list[int], list[int], list[int]]:
    """Return (virtual_ids, wtp_ids, sbus_ids, lora_ids) from rooms device listings."""
    virtual_ids: list[int] = []
    wtp_ids: list[int] = []
    sbus_ids: list[int] = []
    lora_ids: list[int] = []
    seen: set[tuple[str, int]] = set()

    for room in rooms:
        for device in room.get("devices", []):
            cls = device.get("class") or device.get("source", "")
            dev_id = device.get("id")
            if dev_id is None:
                continue
            key = (cls, dev_id)
            if key in seen:
                continue
            seen.add(key)

            if cls in _VIRTUAL_CLASSES:
                virtual_ids.append(dev_id)
            elif cls in _WTP_CLASSES:
                wtp_ids.append(dev_id)
            elif cls in _SBUS_CLASSES:
                sbus_ids.append(dev_id)
            elif cls in _LORA_CLASSES:
                lora_ids.append(dev_id)

    return virtual_ids, wtp_ids, sbus_ids, lora_ids


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
        for room in rooms:
            if int(room.get("id", -1)) == int(room_id):
                _apply_room_keys(device, room, floors)
                return

    for room in rooms:
        for dev in room.get("devices", []):
            dev_class = dev.get("class") or dev.get("source")
            if dev.get("id") == device_id and dev_class == device.get("class"):
                device["_device_name"] = dev.get("name") or device.get("name", str(device_id))
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
        for device in room.get("devices", []):
            if device.get("id") == device_id:
                return room.get("name", "")
    return ""


def _device_name_in_room(rooms: list[dict[str, Any]], device_id: int) -> str:
    for room in rooms:
        for device in room.get("devices", []):
            if device.get("id") == device_id:
                return device.get("name", str(device_id))
    return str(device_id)


def _build_parent_maps(parent_devices: list[dict[str, Any]]) -> dict[str, dict[int, str]]:
    """Build bus-keyed maps of {parent_id → model} from the parent-devices list."""
    maps: dict[str, dict[int, str]] = {}
    for p in parent_devices:
        cls = p.get("class", "")
        pid = p.get("id")
        model = p.get("model")
        if pid is not None and model and "_parent_device" in cls:
            bus = cls.split("_parent_device")[0]  # "sbus", "wtp", "lora"
            maps.setdefault(bus, {})[int(pid)] = model
    return maps


def _inject_parent_models(
    devices: dict[int, dict[str, Any]],
    bus: str,
    parent_maps: dict[str, dict[int, str]],
) -> None:
    """Inject _parent_model from parent device hardware model into child devices."""
    bus_map = parent_maps.get(bus, {})
    if not bus_map:
        return
    for device in devices.values():
        pid = device.get("parent_id")
        if pid is not None:
            model = bus_map.get(int(pid))
            if model:
                device["_parent_model"] = model
