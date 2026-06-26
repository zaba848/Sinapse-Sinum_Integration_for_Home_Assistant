from __future__ import annotations

import asyncio
import logging
from typing import Any, TypeAlias, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SinumClient, SinumNotSupportedError
from .const import (
    ATTR_ENTRY_ID,
    ATTR_MQTT_CLIENT_ID,
    ATTR_MQTT_DRY_RUN,
    ATTR_MQTT_SCENE_ID,
    ATTR_NOTIFICATION_MESSAGE,
    ATTR_NOTIFICATION_TITLE,
    ATTR_PAYLOAD,
    ATTR_SCHEDULE_ID,
    AUTH_MODE_TOKEN,
    CONF_API_TOKEN,
    CONF_AUTH_MODE,
    CONF_MQTT_CLIENT_ID,
    CONF_MQTT_ENABLED,
    CONF_MQTT_SCENE_ID,
    CONF_MQTT_TOPIC_PREFIX,
    CONF_WS_ENABLED,
    CONF_WS_PATH,
    DEFAULT_MQTT_CLIENT_ID,
    DEFAULT_MQTT_SCENE_ID,
    DEFAULT_MQTT_TOPIC_PREFIX,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_WS_PATH,
    DOMAIN,
    SERVICE_SEND_NOTIFICATION,
    SERVICE_UPDATE_SCHEDULE,
    SERVICE_UPLOAD_MQTT_BRIDGE,
)
from .coordinator import SinumCoordinator
from .lua_mqtt_bridge import render as _render_mqtt_bridge_lua
from .mqtt import SinumMqttBridge
from .websocket import SinumWebSocketBridge

_LOGGER = logging.getLogger(__name__)

DATA_NOTIFICATION_CLIENTS = "notification_clients"
DATA_COORDINATORS = "coordinators"

PLATFORMS: list[Platform] = [
    Platform.ALARM_CONTROL_PANEL,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CAMERA,
    Platform.CLIMATE,
    Platform.COVER,
    Platform.EVENT,
    Platform.LIGHT,
    Platform.NOTIFY,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
]

NOTIFY_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_NOTIFICATION_TITLE): cv.string,
        vol.Required(ATTR_NOTIFICATION_MESSAGE): cv.string,
    }
)

UPDATE_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Required(ATTR_SCHEDULE_ID): cv.positive_int,
        vol.Required(ATTR_PAYLOAD): dict,
    }
)

UPLOAD_MQTT_BRIDGE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Optional(ATTR_MQTT_SCENE_ID): cv.positive_int,
        vol.Optional(ATTR_MQTT_CLIENT_ID): cv.positive_int,
        vol.Optional(ATTR_MQTT_DRY_RUN, default=False): cv.boolean,
    }
)

SinumConfigEntry: TypeAlias = ConfigEntry[SinumCoordinator]

_MQTT_BRIDGES: dict[str, SinumMqttBridge] = {}
_WS_BRIDGES: dict[str, SinumWebSocketBridge] = {}


def _notification_clients(hass: HomeAssistant) -> dict[str, SinumClient]:
    domain_data = hass.data.setdefault(DOMAIN, {})
    return cast(dict[str, SinumClient], domain_data.setdefault(DATA_NOTIFICATION_CLIENTS, {}))


def _coordinators(hass: HomeAssistant) -> dict[str, SinumCoordinator]:
    domain_data = hass.data.setdefault(DOMAIN, {})
    return cast(dict[str, SinumCoordinator], domain_data.setdefault(DATA_COORDINATORS, {}))


def _single_coordinator_or_raise(coordinators: dict[str, SinumCoordinator]) -> SinumCoordinator:
    if len(coordinators) == 1:
        return next(iter(coordinators.values()))
    if coordinators:
        raise HomeAssistantError("entry_id is required when multiple Sinum hubs are loaded")
    raise HomeAssistantError("No Sinum hubs are loaded")


def _select_coordinator(hass: HomeAssistant, entry_id: str | None) -> SinumCoordinator:
    coordinators = _coordinators(hass)
    if not entry_id:
        return _single_coordinator_or_raise(coordinators)
    coordinator = coordinators.get(entry_id)
    if coordinator is None:
        raise HomeAssistantError(f"Sinum config entry not loaded: {entry_id}")
    return coordinator


def _merge_schedule(
    coordinator: SinumCoordinator,
    schedule_id: int,
    updated_schedule: dict[str, Any],
) -> None:
    if not updated_schedule:
        return
    merged = {"id": schedule_id, **updated_schedule}
    for index, schedule in enumerate(coordinator.schedules):
        if str(schedule.get("id")) == str(schedule_id):
            coordinator.schedules[index] = {**schedule, **merged}
            return
    coordinator.schedules.append(merged)


def _publish_schedule_update(coordinator: SinumCoordinator) -> None:
    data = coordinator.data if isinstance(coordinator.data, dict) else {}
    coordinator.async_set_updated_data({**data, "schedules": coordinator.schedules})


async def _async_update_listener(hass: HomeAssistant, entry: SinumConfigEntry) -> None:
    """Reload the integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _build_client(hass: HomeAssistant, entry: SinumConfigEntry) -> SinumClient:
    session = async_get_clientsession(hass, verify_ssl=False)
    auth_mode = entry.data.get(CONF_AUTH_MODE, "password")
    if auth_mode == AUTH_MODE_TOKEN:
        return SinumClient(
            entry.data[CONF_HOST],
            session,
            api_token=entry.data[CONF_API_TOKEN],
        )
    return SinumClient(
        entry.data[CONF_HOST],
        session,
        username=entry.data.get(CONF_USERNAME),
        password=entry.data.get(CONF_PASSWORD),
    )


def _sync_entry_title(
    hass: HomeAssistant, entry: SinumConfigEntry, coordinator: SinumCoordinator
) -> None:
    hub_name = coordinator.hub_info.get("name") or coordinator.hub_info.get("hostname")
    if not hub_name:
        return
    expected = f"Sinum ({hub_name})"
    if entry.title != expected:
        _update_entry_title_if_loaded(hass, entry, expected)


def _update_entry_title_if_loaded(hass: HomeAssistant, entry: SinumConfigEntry, title: str) -> None:
    if hass.config_entries.async_get_entry(entry.entry_id):
        hass.config_entries.async_update_entry(entry, title=title)


async def _start_mqtt_bridge(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
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


async def _start_ws_bridge(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    coordinator: SinumCoordinator,
    opts: dict[str, Any],
) -> bool:
    if not opts.get(CONF_WS_ENABLED, False):
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
    return True


async def _start_realtime_bridge(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    coordinator: SinumCoordinator,
    opts: dict[str, Any],
) -> None:
    if await _start_ws_bridge(hass, entry, coordinator, opts):
        return
    await _start_mqtt_bridge(hass, entry, coordinator, opts)


def _register_service_if_missing(
    hass: HomeAssistant,
    service: str,
    handler: Any,
    schema: vol.Schema,
) -> None:
    if hass.services.has_service(DOMAIN, service):
        return
    hass.services.async_register(DOMAIN, service, handler, schema=schema)


def _register_services(hass: HomeAssistant) -> None:
    """Register HA services; safe to call on every entry load (no-ops if already registered)."""

    async def handle_send_notification(call: ServiceCall) -> None:
        async def _send(client: SinumClient) -> None:
            try:
                await client.send_notification(
                    title=call.data[ATTR_NOTIFICATION_TITLE],
                    message=call.data[ATTR_NOTIFICATION_MESSAGE],
                )
            except SinumNotSupportedError as err:
                raise HomeAssistantError(
                    "This Sinum hub model does not support push notifications"
                ) from err

        await asyncio.gather(*(_send(c) for c in _notification_clients(hass).values()))

    async def handle_update_schedule(call: ServiceCall) -> None:
        coordinator = _select_coordinator(hass, call.data.get(ATTR_ENTRY_ID))
        schedule_id = call.data[ATTR_SCHEDULE_ID]
        payload = dict(call.data[ATTR_PAYLOAD])
        updated = await coordinator.client.patch_schedule(schedule_id, payload)
        _merge_schedule(coordinator, schedule_id, updated or payload)
        _publish_schedule_update(coordinator)

    async def handle_upload_mqtt_bridge(call: ServiceCall) -> None:
        coordinator = _select_coordinator(hass, call.data.get(ATTR_ENTRY_ID))
        opts = coordinator.config_entry.options
        data = coordinator.config_entry.data

        scene_id = call.data.get(
            ATTR_MQTT_SCENE_ID,
            opts.get(CONF_MQTT_SCENE_ID, data.get(CONF_MQTT_SCENE_ID, DEFAULT_MQTT_SCENE_ID)),
        )
        client_id = call.data.get(
            ATTR_MQTT_CLIENT_ID,
            opts.get(CONF_MQTT_CLIENT_ID, data.get(CONF_MQTT_CLIENT_ID, DEFAULT_MQTT_CLIENT_ID)),
        )
        topic_prefix = opts.get(
            CONF_MQTT_TOPIC_PREFIX,
            data.get(CONF_MQTT_TOPIC_PREFIX, DEFAULT_MQTT_TOPIC_PREFIX),
        )
        lua_code = _render_mqtt_bridge_lua(topic_prefix=topic_prefix, client_id=int(client_id))
        dry_run = call.data.get(ATTR_MQTT_DRY_RUN, False)
        if dry_run:
            _LOGGER.info(
                "sinum.upload_mqtt_bridge dry_run: scene=%d client=%d prefix=%s lua_len=%d",
                scene_id,
                client_id,
                topic_prefix,
                len(lua_code),
            )
            return
        await coordinator.client.patch_scene_lua(int(scene_id), lua_code)
        _LOGGER.info(
            "Uploaded MQTT bridge Lua to scene %d (client_id=%d prefix=%s)",
            scene_id,
            client_id,
            topic_prefix,
        )

    _register_service_if_missing(
        hass,
        SERVICE_SEND_NOTIFICATION,
        handle_send_notification,
        NOTIFY_SCHEMA,
    )
    _register_service_if_missing(
        hass,
        SERVICE_UPDATE_SCHEDULE,
        handle_update_schedule,
        UPDATE_SCHEDULE_SCHEMA,
    )
    _register_service_if_missing(
        hass,
        SERVICE_UPLOAD_MQTT_BRIDGE,
        handle_upload_mqtt_bridge,
        UPLOAD_MQTT_BRIDGE_SCHEMA,
    )


async def _stop_mqtt_bridge_for_entry(entry_id: str) -> None:
    bridge = _MQTT_BRIDGES.pop(entry_id, None)
    if bridge:
        await bridge.async_stop()


async def _stop_ws_bridge_for_entry(entry_id: str) -> None:
    bridge = _WS_BRIDGES.pop(entry_id, None)
    if bridge:
        await bridge.async_stop()


def _stale_uid_prefixes(entry_id: str, removed_ids: dict[str, frozenset[int]]) -> set[str]:
    prefixes: set[str] = set()
    for bus, ids in removed_ids.items():
        for device_id in ids:
            prefixes.add(f"{entry_id}_{bus}_{device_id}")
    return prefixes


def _stale_identifiers(entry_id: str, removed_ids: dict[str, frozenset[int]]) -> set[tuple[str, str]]:
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


async def _cleanup_stale_entities(
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


def _remove_entry_runtime_data(hass: HomeAssistant, entry_id: str) -> None:
    _notification_clients(hass).pop(entry_id, None)
    _coordinators(hass).pop(entry_id, None)


def _remove_domain_services_if_no_coordinators(hass: HomeAssistant) -> None:
    if _coordinators(hass):
        return
    for svc in (SERVICE_SEND_NOTIFICATION, SERVICE_UPDATE_SCHEDULE, SERVICE_UPLOAD_MQTT_BRIDGE):
        if hass.services.has_service(DOMAIN, svc):
            hass.services.async_remove(DOMAIN, svc)


async def async_migrate_entry(hass: HomeAssistant, entry: SinumConfigEntry) -> bool:
    """Migrate old config entry schema to current version."""
    _LOGGER.debug("Migrating Sinum entry from version %s", entry.version)

    if entry.version > 1:
        _LOGGER.error("Cannot migrate Sinum config entry: unsupported version %s", entry.version)
        return False

    # v1: ensure auth_mode is present (early entries created before auth_mode field was added)
    if CONF_AUTH_MODE not in entry.data:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_AUTH_MODE: AUTH_MODE_TOKEN}
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: SinumConfigEntry) -> bool:
    client = _build_client(hass, entry)
    await client.login()

    opts = {**entry.data, **entry.options}
    coordinator = SinumCoordinator(
        hass, client, scan_interval=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    _sync_entry_title(hass, entry, coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await _start_realtime_bridge(hass, entry, coordinator, opts)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _notification_clients(hass)[entry.entry_id] = client
    _coordinators(hass)[entry.entry_id] = coordinator
    _register_services(hass)

    @callback
    def _handle_stale_cleanup() -> None:
        if coordinator.last_update_success and any(coordinator.removed_ids.values()):
            hass.async_create_task(
                _cleanup_stale_entities(hass, entry.entry_id, coordinator.removed_ids)
            )

    entry.async_on_unload(coordinator.async_add_listener(_handle_stale_cleanup))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: SinumConfigEntry) -> bool:
    await _stop_ws_bridge_for_entry(entry.entry_id)
    await _stop_mqtt_bridge_for_entry(entry.entry_id)

    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unloaded:
        return unloaded

    _remove_entry_runtime_data(hass, entry.entry_id)
    _remove_domain_services_if_no_coordinators(hass)
    return unloaded
