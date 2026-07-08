"""Unit tests for the central bus registry."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.sinum._bus_registry import (
    BUS_REGISTRY,
    ROOM_CLASSIFIED_BUSES,
    bus_patch_method,
    bus_spec,
    bus_store,
    normalize_bus_name,
)


def _coordinator() -> MagicMock:
    coordinator = MagicMock()
    coordinator.virtual_devices = {1: {"id": 1}}
    coordinator.wtp_devices = {2: {"id": 2}}
    coordinator.sbus_devices = {3: {"id": 3}}
    coordinator.lora_devices = {4: {"id": 4}}
    coordinator.slink_devices = {5: {"id": 5}}
    coordinator.modbus_devices = {6: {"id": 6}}
    coordinator.video_devices = {7: {"id": 7}}
    coordinator.client.patch_wtp_device = MagicMock()
    coordinator.client.patch_slink_device = MagicMock()
    return coordinator


def test_bus_registry_has_seven_buses() -> None:
    assert len(BUS_REGISTRY) == 7
    assert {spec.name for spec in BUS_REGISTRY} == {
        "virtual",
        "wtp",
        "sbus",
        "lora",
        "slink",
        "modbus",
        "video",
    }


def test_room_classified_buses_order() -> None:
    assert [spec.name for spec in ROOM_CLASSIFIED_BUSES] == [
        "virtual",
        "wtp",
        "sbus",
        "lora",
    ]


def test_bus_store_returns_correct_store() -> None:
    coordinator = _coordinator()
    assert bus_store(coordinator, "slink") is coordinator.slink_devices
    assert bus_store(coordinator, "wtp_regulator") is coordinator.wtp_devices
    assert bus_store(coordinator, "sbus_regulator") is coordinator.sbus_devices


def test_bus_store_unknown_bus_returns_none() -> None:
    assert bus_store(_coordinator(), "unknown") is None


def test_bus_patch_method_for_slink() -> None:
    coordinator = _coordinator()
    assert bus_patch_method(coordinator, "slink") is coordinator.client.patch_slink_device


def test_bus_patch_method_unknown_bus_returns_none() -> None:
    assert bus_patch_method(_coordinator(), "modbus") is None


def test_normalize_bus_name_aliases() -> None:
    assert normalize_bus_name("wtp_regulator") == "wtp"
    assert normalize_bus_name("SBUS") == "sbus"


def test_bus_spec_lookup() -> None:
    spec = bus_spec("lora")
    assert spec is not None
    assert spec.store_attr == "lora_devices"
    assert spec.track_removals is True
