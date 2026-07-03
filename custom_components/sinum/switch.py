from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SinumConfigEntry
from .const import (
    LTYPE_RELAY,
    STYPE_COMMON_VALVE,
    STYPE_RELAY,
    VTYPE_HEAT_PUMP_MANAGER,
    VTYPE_RELAY,
    VTYPE_WICKET,
    WTYPE_RELAY,
)
from .coordinator import SinumCoordinator
from .switch_bus import SinumBusRelaySwitch, SinumCommonValveSwitch  # noqa: F401
from .switch_virtual import SinumDhwSwitch, SinumRelaySwitch, SinumWicketSwitch  # noqa: F401

PARALLEL_UPDATES = 0


def _virtual_switch_entity(
    coordinator: SinumCoordinator, device_id: int, entry_id: str, device: dict[str, Any]
) -> SwitchEntity | None:
    dev_type = device.get("type")
    if not isinstance(dev_type, str):
        return None
    if dev_type == VTYPE_HEAT_PUMP_MANAGER:
        return _heat_pump_dhw_switch(coordinator, device_id, entry_id, device)
    factories = {
        VTYPE_RELAY: SinumRelaySwitch,
        VTYPE_WICKET: SinumWicketSwitch,
    }
    factory = factories.get(dev_type)
    if factory is None:
        return None
    return factory(coordinator, device_id, entry_id)


def _heat_pump_dhw_switch(
    coordinator: SinumCoordinator, device_id: int, entry_id: str, device: dict[str, Any]
) -> SwitchEntity | None:
    dhw = device.get("dhw_control")
    if not (isinstance(dhw, dict) and "enabled" in dhw):
        return None
    return SinumDhwSwitch(coordinator, device_id, entry_id)


def _wtp_switch_entity(
    coordinator: SinumCoordinator, device_id: int, entry_id: str, device: dict[str, Any]
) -> SwitchEntity | None:
    if device.get("type") != WTYPE_RELAY:
        return None
    return SinumBusRelaySwitch(coordinator, device_id, entry_id, "wtp")


def _sbus_switch_entity(
    coordinator: SinumCoordinator, device_id: int, entry_id: str, device: dict[str, Any]
) -> SwitchEntity | None:
    dev_type = device.get("type")
    if dev_type == STYPE_COMMON_VALVE:
        return SinumCommonValveSwitch(coordinator, device_id, entry_id)
    if dev_type != STYPE_RELAY:
        return None
    if "managed_by_thermostat" in device.get("labels", []):
        return None
    return SinumBusRelaySwitch(coordinator, device_id, entry_id, "sbus")


def _lora_switch_entity(
    coordinator: SinumCoordinator, device_id: int, entry_id: str, device: dict[str, Any]
) -> SwitchEntity | None:
    if device.get("type") != LTYPE_RELAY:
        return None
    return SinumBusRelaySwitch(coordinator, device_id, entry_id, "lora")


def _slink_switch_entity(
    coordinator: SinumCoordinator, device_id: int, entry_id: str, device: dict[str, Any]
) -> SwitchEntity | None:
    if device.get("type") != STYPE_RELAY:
        return None
    return SinumBusRelaySwitch(coordinator, device_id, entry_id, "slink")


def _bus_switch_entity(
    coordinator: SinumCoordinator,
    device_id: int,
    entry_id: str,
    bus: str,
    device: dict[str, Any],
) -> SwitchEntity | None:
    handlers = {
        "wtp": _wtp_switch_entity,
        "sbus": _sbus_switch_entity,
        "lora": _lora_switch_entity,
        "slink": _slink_switch_entity,
    }
    handler = handlers.get(bus)
    if handler is None:
        return None
    return handler(coordinator, device_id, entry_id, device)


def _add_bus_entities_for_store(
    coordinator: SinumCoordinator,
    entities: list[SwitchEntity],
    entry_id: str,
    bus: str,
    store: dict[int, dict[str, Any]],
) -> None:
    for device_id, device in store.items():
        entity = _bus_switch_entity(coordinator, device_id, entry_id, bus, device)
        if entity is not None:
            entities.append(entity)


def _add_virtual_switches(
    coordinator: SinumCoordinator, entities: list[SwitchEntity], entry_id: str
) -> None:
    for device_id, device in coordinator.virtual_devices.items():
        entity = _virtual_switch_entity(coordinator, device_id, entry_id, device)
        if entity is not None:
            entities.append(entity)


def _add_bus_switches(
    coordinator: SinumCoordinator, entities: list[SwitchEntity], entry_id: str
) -> None:
    _add_bus_entities_for_store(coordinator, entities, entry_id, "wtp", coordinator.wtp_devices)
    _add_bus_entities_for_store(coordinator, entities, entry_id, "sbus", coordinator.sbus_devices)
    _add_bus_entities_for_store(coordinator, entities, entry_id, "lora", coordinator.lora_devices)
    _add_bus_entities_for_store(coordinator, entities, entry_id, "slink", coordinator.slink_devices)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinumCoordinator = entry.runtime_data
    entities: list[SwitchEntity] = []
    _add_virtual_switches(coordinator, entities, entry.entry_id)
    _add_bus_switches(coordinator, entities, entry.entry_id)
    async_add_entities(entities)
