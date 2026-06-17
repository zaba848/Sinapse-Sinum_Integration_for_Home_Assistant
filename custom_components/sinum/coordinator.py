from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SinumClient, SinumConnectionError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Device classes present in the rooms device list
_WTP_CLASSES = {"wtp", "lora"}
_SBUS_CLASSES = {"sbus"}
_VIRTUAL_CLASSES = {"virtual"}


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
        self.rooms: list[dict[str, Any]] = []
        self.floors: dict[int, dict[str, Any]] = {}       # floor_id → {id, name, level}
        self.hub_info: dict[str, Any] = {}                # from /api/v1/info
        self.parent_devices: list[dict[str, Any]] = []    # flat list from /api/v1/parent-devices
        self.schedules: list[dict[str, Any]] = []         # thermal schedules from /api/v1/schedules
        self.mqtt_bridge: Any | None = None               # set by __init__ if MQTT enabled

    async def _async_update_data(self) -> dict[str, Any]:
        # ── Hub info (always-available health check) ──────────────────────────
        try:
            self.hub_info = await self.client.get_hub_info()
        except SinumConnectionError as err:
            if not self.hub_info:
                raise UpdateFailed(f"Cannot reach Sinum hub: {err}") from err
            _LOGGER.debug("Hub info unavailable (%s), using cached", err)

        # ── Rooms (non-fatal — 408 on alpha firmware, use cache or empty) ─────
        try:
            rooms = await self.client.get_rooms()
            self.rooms = rooms
        except SinumConnectionError as err:
            _LOGGER.debug("Rooms endpoint unavailable (%s), using cached rooms", err)
            rooms = self.rooms

        # ── Lua hub info (optional extension) ────────────────────────────────
        try:
            lua_info = await self.client.get_lua_hub_info()
            if lua_info:
                self.hub_info.update(lua_info)
        except SinumConnectionError as err:
            _LOGGER.debug("Optional Lua hub info endpoint not available: %s", err)

        # ── Floors (REST /api/v1/floors) ──────────────────────────────────────
        try:
            floors_list = await self.client.get_floors()
            self.floors = {int(f["id"]): f for f in floors_list if "id" in f}
        except SinumConnectionError as err:
            _LOGGER.debug("Failed to fetch floors: %s", err)

        # ── Parent device statuses (/api/v1/parent-devices) ───────────────────
        try:
            self.parent_devices = await self.client.get_parent_devices()
        except SinumConnectionError as err:
            _LOGGER.debug("Failed to fetch parent devices: %s", err)

        # ── Thermal schedules (/api/v1/schedules) ────────────────────────────
        try:
            self.schedules = await self.client.get_schedules()
        except SinumConnectionError as err:
            _LOGGER.debug("Failed to fetch schedules: %s", err)

        # ── Classify device IDs from rooms (fallback for older firmware) ──────
        virtual_ids, wtp_ids, sbus_ids = _collect_device_ids(rooms)

        # ── Device collections ────────────────────────────────────────────────
        # Firmware 1.24 exposes full class collections. Relying only on rooms
        # misses valid devices that are not assigned to any room.
        virtual = await self._fetch_device_collection(
            "virtual",
            self.client.get_virtual_devices,
            self.client.get_virtual_device,
            virtual_ids,
            rooms,
            self.virtual_devices,
        )
        wtp = await self._fetch_device_collection(
            "WTP",
            self.client.get_wtp_devices,
            self.client.get_wtp_device,
            wtp_ids,
            rooms,
            self.wtp_devices,
        )
        sbus = await self._fetch_device_collection(
            "SBUS",
            self.client.get_sbus_devices,
            self.client.get_sbus_device,
            sbus_ids,
            rooms,
            self.sbus_devices,
        )

        self.virtual_devices = virtual
        self.wtp_devices = wtp
        self.sbus_devices = sbus
        return {"virtual": virtual, "wtp": wtp, "sbus": sbus, "schedules": self.schedules}

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

def _collect_device_ids(
    rooms: list[dict[str, Any]],
) -> tuple[list[int], list[int], list[int]]:
    """Return (virtual_ids, wtp_ids, sbus_ids) from rooms device listings."""
    virtual_ids: list[int] = []
    wtp_ids: list[int] = []
    sbus_ids: list[int] = []
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

    return virtual_ids, wtp_ids, sbus_ids


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
