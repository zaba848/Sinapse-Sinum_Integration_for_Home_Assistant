from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from ._bus_registry import BUS_REGISTRY, ROOM_CLASSIFIED_BUSES
from ._coordinator_helpers import (
    _apply_optional_stores,
    _build_parent_maps,
    _collect_device_ids,
    _device_id_as_int,
    _index_by_id,
    _inject_parent_models,
    _inject_room_keys,
    _safe_fetch,
    _source_from_label,
    _unique_ids,
)
from ._webrtc import WebRtcSessionManager
from .api import SinumAuthError, SinumClient, SinumConnectionError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class _DeviceStoreResults:
    virtual: dict[int, dict[str, Any]]
    wtp: dict[int, dict[str, Any]]
    sbus: dict[int, dict[str, Any]]
    lora: dict[int, dict[str, Any]]
    alarm_list: list[Any] | None
    modbus_list: list[Any] | None
    video_list: list[Any] | None
    slink_list: list[Any] | None


# Re-export helpers so existing importers (tests, other modules) continue to work
from ._coordinator_helpers import (  # noqa: F401, E402
    _CLASS_BUCKET_INDEX,
    _KNOWN_CLASSES,
    _LORA_CLASSES,
    _SBUS_CLASSES,
    _VIRTUAL_CLASSES,
    _WTP_CLASSES,
    _accumulate_parent_entry,
    _add_device_to_bucket,
    _apply_room_keys,
    _device_class,
    _device_matches,
    _device_name_in_room,
    _filter_dicts,
    _find_room_by_id,
    _find_room_containing_device,
    _first_device_class_field,
    _inject_parent_model_for_device,
    _inject_room_defaults,
    _inject_room_from_explicit_id,
    _inject_room_from_lookup,
    _iter_room_device_pairs,
    _iter_room_devices,
    _map_for_bus,
    _maybe_index_list,
    _parent_id,
    _room_devices,
    _room_name_for_device,
)


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
        self.slink_devices: dict[int, dict[str, Any]] = {}
        self.modbus_devices: dict[int, dict[str, Any]] = {}
        self.video_devices: dict[int, dict[str, Any]] = {}
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
        self.removed_ids: dict[str, frozenset[int]] = {}
        self._webrtc = WebRtcSessionManager(client)
        self._motion_events: dict[int, dict[str, Any]] = {}

    def register_webrtc_session(self, session_id: str, device_id: int, send_message: Any) -> None:
        self._webrtc.register(session_id, device_id, send_message)

    def dispatch_webrtc_answer(self, session_id: str, answer_sdp: str) -> None:
        self._webrtc.dispatch_answer(session_id, answer_sdp)

    def dispatch_webrtc_candidate(self, session_id: str, candidate_dict: dict[str, Any]) -> None:
        self._webrtc.dispatch_candidate(session_id, candidate_dict)

    def dispatch_webrtc_error(self, session_id: str, code: str, message: str) -> None:
        self._webrtc.dispatch_error(session_id, code, message)

    def close_webrtc_session(self, session_id: str) -> None:
        self._webrtc.close(session_id)

    def dispatch_motion_detected(self, device_id: int, payload: dict[str, Any]) -> None:
        """Store motion detection event from WebSocket for event entities."""
        self._motion_events[device_id] = {
            "timestamp": payload.get("timestamp"),
            "device_id": device_id,
        }
        self.async_set_updated_data(self.data)

    def get_motion_event(self, device_id: int) -> dict[str, Any] | None:
        """Get and clear motion event for device."""
        return self._motion_events.pop(device_id, None)

    async def forward_webrtc_candidate(self, session_id: str, candidate: Any) -> None:
        await self._webrtc.forward_candidate(session_id, candidate)

    @property
    def hub_name(self) -> str:
        """Short name of this hub, used to prefix device names for multi-hub uniqueness."""
        return self.hub_info.get("name") or self.hub_info.get("hostname") or ""

    @property
    def video_device_ips(self) -> frozenset[str]:
        return frozenset(dev["ip"] for dev in self.video_devices.values() if dev.get("ip"))

    def _apply_hub_metadata(self, hub_info: Any, lua_info: Any) -> None:
        if hub_info is not None:
            self.hub_info = hub_info
        elif not self.hub_info:
            raise UpdateFailed("Cannot reach Sinum hub: hub info unavailable")
        if lua_info:
            self.hub_info.update(lua_info)

    def _apply_rooms_and_floors(self, rooms: Any, floors_list: Any) -> None:
        if rooms is not None:
            self.rooms = rooms
        if floors_list is not None:
            self.floors = _index_by_id(floors_list)

    def _apply_optional_metadata(self, values: dict[str, Any]) -> None:
        for attr, value in values.items():
            if value is not None:
                setattr(self, attr, value)

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
        self._apply_hub_metadata(hub_info, lua_info)
        self._apply_rooms_and_floors(rooms, floors_list)
        self._apply_optional_metadata(
            {
                "parent_devices": parent_devices,
                "scenes": scenes,
                "schedules": schedules,
                "automations": automations,
                "variables": variables,
            }
        )

        return self.rooms

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self._fetch_all()
        except SinumAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err

    async def _fetch_all(self) -> dict[str, Any]:
        rooms = await self._fetch_metadata()
        prev_by_bus = self._removal_snapshots()
        bus_ids = self._room_classified_bus_ids(rooms)
        stores = await self._fetch_device_stores(rooms, bus_ids)
        self._apply_device_store_results(stores, prev_by_bus)
        self._inject_parent_models_for_buses(stores.wtp, stores.sbus, stores.lora)
        return self._coordinator_data_payload(stores)

    async def _fetch_metadata(self) -> list[dict[str, Any]]:
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
        return self._apply_metadata_results(*meta)

    def _removal_snapshots(self) -> dict[str, frozenset[int]]:
        return {
            spec.name: frozenset(getattr(self, spec.store_attr))
            for spec in BUS_REGISTRY
            if spec.track_removals
        }

    def _room_classified_bus_ids(self, rooms: list[dict[str, Any]]) -> dict[str, list[int]]:
        room_bucket_ids = _collect_device_ids(rooms)
        parent_bucket_ids = _collect_device_ids(self.parent_devices)
        return {
            spec.name: _unique_ids([*room_bucket_ids[i], *parent_bucket_ids[i]])
            for i, spec in enumerate(ROOM_CLASSIFIED_BUSES)
        }

    async def _fetch_device_stores(
        self, rooms: list[dict[str, Any]], bus_ids: dict[str, list[int]]
    ) -> _DeviceStoreResults:
        (
            virtual,
            wtp,
            sbus,
            lora,
            alarm_list,
            modbus_list,
            video_list,
            slink_list,
        ) = await asyncio.gather(
            *[
                self._fetch_device_collection(
                    spec.collection_label or spec.name,
                    getattr(self.client, spec.list_getter),
                    getattr(self.client, spec.item_getter),
                    bus_ids[spec.name],
                    rooms,
                    getattr(self, spec.store_attr),
                )
                for spec in ROOM_CLASSIFIED_BUSES
            ],
            _safe_fetch(self.client.get_alarm_devices, "alarm devices", default=None),
            _safe_fetch(self.client.get_modbus_devices, "modbus devices", default=None),
            _safe_fetch(self.client.get_video_devices, "video devices", default=None),
            _safe_fetch(self.client.get_slink_devices, "slink devices", default=None),
        )
        return _DeviceStoreResults(
            virtual, wtp, sbus, lora, alarm_list, modbus_list, video_list, slink_list
        )

    def _apply_device_store_results(
        self,
        stores: _DeviceStoreResults,
        prev_by_bus: dict[str, frozenset[int]],
    ) -> None:
        self.virtual_devices = stores.virtual
        self.wtp_devices = stores.wtp
        self.sbus_devices = stores.sbus
        self.lora_devices = stores.lora
        _apply_optional_stores(
            self, stores.alarm_list, stores.modbus_list, stores.video_list, stores.slink_list
        )
        self.removed_ids = {
            spec.name: prev_by_bus[spec.name] - frozenset(getattr(self, spec.store_attr))
            for spec in BUS_REGISTRY
            if spec.track_removals
        }

    def _inject_parent_models_for_buses(
        self,
        wtp: dict[int, dict[str, Any]],
        sbus: dict[int, dict[str, Any]],
        lora: dict[int, dict[str, Any]],
    ) -> None:
        parent_maps, parent_class_maps = _build_parent_maps(self.parent_devices)
        _inject_parent_models(wtp, "wtp", parent_maps, parent_class_maps)
        _inject_parent_models(sbus, "sbus", parent_maps, parent_class_maps)
        _inject_parent_models(lora, "lora", parent_maps, parent_class_maps)

    def _coordinator_data_payload(self, stores: _DeviceStoreResults) -> dict[str, Any]:
        return {
            "virtual": stores.virtual,
            "wtp": stores.wtp,
            "sbus": stores.sbus,
            "lora": stores.lora,
            "slink": self.slink_devices,
            "modbus": self.modbus_devices,
            "video": self.video_devices,
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

    async def _bulk_collection(self, list_getter: Any, label: str) -> tuple[list[Any], bool]:
        try:
            return await list_getter(), True
        except Exception as err:
            _LOGGER.debug("Failed to fetch %s device collection: %s", label, err)
            return [], False

    async def _fallback_devices(
        self,
        item_getter: Any,
        fallback_ids: list[int],
        rooms: list[dict[str, Any]],
        label: str,
    ) -> dict[int, dict[str, Any]]:
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
        collection, bulk_ok = await self._bulk_collection(list_getter, label)

        if collection:
            return self._process_bulk_devices(collection, label, rooms)

        # Bulk failed (exception) → return cache to keep entities alive
        if not bulk_ok:
            return cached

        # Bulk succeeded but returned empty list → old firmware without bulk endpoint
        return await self._fallback_devices(item_getter, fallback_ids, rooms, label)


class SinumDeviceAvailableMixin:
    """Marks entity unavailable when its backing device is absent from the coordinator store.

    Mix in *before* CoordinatorEntity so MRO resolves available here first:
        class MyEntity(SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator], ...):

    Also injects the hub name as a prefix in device_info.name so that identically-named
    devices on different hubs get distinct entity_ids in multi-hub setups.
    """

    coordinator: SinumCoordinator
    _attr_device_info: DeviceInfo | None

    @property
    def _device(self) -> dict[str, Any]:
        raise NotImplementedError

    @property
    def available(self) -> bool:
        return super().available and bool(self._device)  # type: ignore[misc]

    @property
    def device_info(self) -> DeviceInfo | None:
        info = self._attr_device_info
        hub_name = _effective_hub_name(self.coordinator)
        if not info or not hub_name:
            return info
        raw_name = info.get("name")
        if not raw_name:
            return info
        return DeviceInfo(**{**info, "name": f"{hub_name}: {raw_name}"})


def _effective_hub_name(coordinator: SinumCoordinator) -> str | None:
    if not coordinator.hub_name:
        return None
    entries = coordinator.hass.config_entries.async_entries(DOMAIN)
    active = sum(not e.disabled_by for e in entries)
    if active <= 1:
        return None
    return coordinator.hub_name


def hub_prefixed_name(coordinator: SinumCoordinator, name: str) -> str:
    hub = _effective_hub_name(coordinator)
    return f"{hub}: {name}" if hub else name


def via_device_for(device: dict[str, Any], entry_id: str) -> tuple[str, str] | None:
    """Return (DOMAIN, unique_key) for the parent hardware device, or None."""
    cls = device.get("_parent_class")
    pid = device.get("_parent_id")
    if cls and pid is not None:
        return (DOMAIN, f"{entry_id}_parent_{cls}_{pid}")
    return None
