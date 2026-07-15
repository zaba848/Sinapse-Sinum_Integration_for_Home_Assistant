"""Bridge lifecycle and stale entity cleanup helpers for the Sinum integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_MQTT_ENABLED,
    CONF_MQTT_TOPIC_PREFIX,
    CONF_WS_ENABLED,
    CONF_WS_PATH,
    DEFAULT_MQTT_TOPIC_PREFIX,
    DEFAULT_WS_PATH,
    DOMAIN,
)
from .mqtt import SinumMqttBridge
from .websocket import SinumWebSocketBridge

if TYPE_CHECKING:  # pragma: no cover
    from homeassistant.config_entries import ConfigEntry

    from .coordinator import SinumCoordinator

_LOGGER = logging.getLogger(__name__)

_MQTT_BRIDGES: dict[str, SinumMqttBridge] = {}
_WS_BRIDGES: dict[str, SinumWebSocketBridge] = {}


async def start_mqtt_bridge(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: SinumCoordinator,
    opts: dict[str, Any],
) -> None:
    if not opts.get(CONF_MQTT_ENABLED, False):
        return
    bridge = SinumMqttBridge(
        hass,
        coordinator,
        topic_prefix=opts.get(CONF_MQTT_TOPIC_PREFIX, DEFAULT_MQTT_TOPIC_PREFIX),
    )
    if await bridge.async_start():
        _MQTT_BRIDGES[entry.entry_id] = bridge
        coordinator.mqtt_bridge = bridge


async def start_ws_bridge(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: SinumCoordinator,
    opts: dict[str, Any],
) -> bool:
    if not opts.get(CONF_WS_ENABLED, True):
        return False

    bridge = SinumWebSocketBridge(
        hass,
        coordinator.client,
        coordinator,
        ws_path=opts.get(CONF_WS_PATH, DEFAULT_WS_PATH),
    )
    if not await bridge.async_start():
        return False

    _WS_BRIDGES[entry.entry_id] = bridge
    coordinator.ws_bridge = bridge
    return True


async def start_realtime_bridge(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: SinumCoordinator,
    opts: dict[str, Any],
) -> None:
    if await start_ws_bridge(hass, entry, coordinator, opts):
        return
    await start_mqtt_bridge(hass, entry, coordinator, opts)


async def stop_mqtt_bridge(entry_id: str) -> None:
    bridge = _MQTT_BRIDGES.pop(entry_id, None)
    if bridge:
        await bridge.async_stop()


async def stop_ws_bridge(entry_id: str) -> None:
    bridge = _WS_BRIDGES.pop(entry_id, None)
    if bridge:
        await bridge.async_stop()


def _stale_uid_prefixes(entry_id: str, removed_ids: dict[str, frozenset[int]]) -> set[str]:
    prefixes: set[str] = set()
    for bus, ids in removed_ids.items():
        for device_id in ids:
            prefixes.add(f"{entry_id}_{bus}_{device_id}")
    return prefixes


def _stale_identifiers(
    entry_id: str, removed_ids: dict[str, frozenset[int]]
) -> set[tuple[str, str]]:
    return {
        (DOMAIN, f"{entry_id}_{bus}_{device_id}")
        for bus, ids in removed_ids.items()
        for device_id in ids
    }


def _is_stale_entity(entity_entry: er.RegistryEntry, prefixes: set[str]) -> bool:
    uid = entity_entry.unique_id
    return any(uid == p or uid.startswith(f"{p}_") for p in prefixes)


def _remove_stale_devices(
    hass: HomeAssistant,
    entry_id: str,
    stale_identifiers: set[tuple[str, str]],
) -> None:
    dev_reg = dr.async_get(hass)
    for identifier in stale_identifiers:
        device = dev_reg.async_get_device(identifiers={identifier})
        if device is not None:
            _LOGGER.info("Sinum: removing stale device %s", device.name or device.id)
            dev_reg.async_remove_device(device.id)


async def cleanup_stale_entities(
    hass: HomeAssistant,
    entry_id: str,
    removed_ids: dict[str, frozenset[int]],
) -> None:
    prefixes = _stale_uid_prefixes(entry_id, removed_ids)
    if not prefixes:
        return
    ent_reg = er.async_get(hass)
    for entity_entry in list(ent_reg.entities.get_entries_for_config_entry_id(entry_id)):
        if _is_stale_entity(entity_entry, prefixes):
            _LOGGER.info("Sinum: removing stale entity %s", entity_entry.entity_id)
            ent_reg.async_remove(entity_entry.entity_id)
    _remove_stale_devices(hass, entry_id, _stale_identifiers(entry_id, removed_ids))
