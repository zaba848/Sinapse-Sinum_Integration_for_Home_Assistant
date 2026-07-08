"""Central bus registry — single source of truth for device store routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Regulator sensor sources map to their parent bus store.
_BUS_ALIASES: dict[str, str] = {
    "wtp_regulator": "wtp",
    "sbus_regulator": "sbus",
}


@dataclass(frozen=True)
class BusSpec:
    name: str
    room_classified: bool
    track_removals: bool
    store_attr: str
    list_getter: str
    item_getter: str | None = None
    patch_getter: str | None = None
    collection_label: str | None = None


BUS_REGISTRY: tuple[BusSpec, ...] = (
    BusSpec(
        "virtual",
        room_classified=True,
        track_removals=True,
        store_attr="virtual_devices",
        list_getter="get_virtual_devices",
        item_getter="get_virtual_device",
        collection_label="virtual",
    ),
    BusSpec(
        "wtp",
        room_classified=True,
        track_removals=True,
        store_attr="wtp_devices",
        list_getter="get_wtp_devices",
        item_getter="get_wtp_device",
        patch_getter="patch_wtp_device",
        collection_label="WTP",
    ),
    BusSpec(
        "sbus",
        room_classified=True,
        track_removals=True,
        store_attr="sbus_devices",
        list_getter="get_sbus_devices",
        item_getter="get_sbus_device",
        patch_getter="patch_sbus_device",
        collection_label="SBUS",
    ),
    BusSpec(
        "lora",
        room_classified=True,
        track_removals=True,
        store_attr="lora_devices",
        list_getter="get_lora_devices",
        item_getter="get_lora_device",
        patch_getter="patch_lora_device",
        collection_label="LoRa",
    ),
    BusSpec(
        "slink",
        room_classified=False,
        track_removals=True,
        store_attr="slink_devices",
        list_getter="get_slink_devices",
        item_getter="get_slink_device",
        patch_getter="patch_slink_device",
    ),
    BusSpec(
        "modbus",
        room_classified=False,
        track_removals=False,
        store_attr="modbus_devices",
        list_getter="get_modbus_devices",
    ),
    BusSpec(
        "video",
        room_classified=False,
        track_removals=False,
        store_attr="video_devices",
        list_getter="get_video_devices",
    ),
)

ROOM_CLASSIFIED_BUSES: tuple[BusSpec, ...] = tuple(s for s in BUS_REGISTRY if s.room_classified)
OPTIONAL_FETCH_BUSES: tuple[BusSpec, ...] = tuple(
    s for s in BUS_REGISTRY if not s.room_classified and s.name != "video"
)
# video fetched alongside modbus/slink in optional group; slink/modbus/video all use safe_fetch

_BUS_BY_NAME: dict[str, BusSpec] = {spec.name: spec for spec in BUS_REGISTRY}


def normalize_bus_name(bus: str) -> str:
    """Map regulator aliases and normalize bus identifiers."""
    key = str(bus).lower()
    return _BUS_ALIASES.get(key, key)


def bus_spec(bus: str) -> BusSpec | None:
    return _BUS_BY_NAME.get(normalize_bus_name(bus))


def bus_store(coordinator: Any, bus: str) -> dict[int, dict[str, Any]] | None:
    """Return the coordinator device store for a bus name, or None if unknown."""
    spec = bus_spec(bus)
    if spec is None:
        return None
    return getattr(coordinator, spec.store_attr)


def bus_patch_method(coordinator: Any, bus: str) -> Any | None:
    """Return the client PATCH callable for a bus, if defined."""
    spec = bus_spec(bus)
    if spec is None or spec.patch_getter is None:
        return None
    return getattr(coordinator.client, spec.patch_getter)
