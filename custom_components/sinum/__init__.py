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
    ATTR_RUN_SCENE_ID,
    ATTR_SCHEDULE_ID,
    AUTH_MODE_TOKEN,
    CONF_API_TOKEN,
    CONF_AUTH_MODE,
    CONF_MQTT_CLIENT_ID,
    CONF_MQTT_SCENE_ID,
    CONF_MQTT_TOPIC_PREFIX,
    DEFAULT_MQTT_CLIENT_ID,
    DEFAULT_MQTT_SCENE_ID,
    DEFAULT_MQTT_TOPIC_PREFIX,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SERVICE_RUN_SCENE,
    SERVICE_SEND_NOTIFICATION,
    SERVICE_UPDATE_SCHEDULE,
    SERVICE_UPLOAD_MQTT_BRIDGE,
)
from .coordinator import SinumCoordinator
from .lifecycle import (
    cleanup_stale_entities as _cleanup_stale_entities,
)
from .lifecycle import (
    start_realtime_bridge as _start_realtime_bridge,
)
from .lifecycle import (
    stop_mqtt_bridge as _stop_mqtt_bridge_for_entry,
)
from .lifecycle import (
    stop_ws_bridge as _stop_ws_bridge_for_entry,
)
from .lua_mqtt_bridge import render as _render_mqtt_bridge_lua

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
    Platform.FAN,
    Platform.LIGHT,
    Platform.NOTIFY,
    Platform.NUMBER,
    Platform.SELECT,
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

RUN_SCENE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Required(ATTR_RUN_SCENE_ID): cv.positive_int,
    }
)

SinumConfigEntry: TypeAlias = ConfigEntry[SinumCoordinator]

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

    async def handle_run_scene(call: ServiceCall) -> None:
        coordinator = _select_coordinator(hass, call.data.get(ATTR_ENTRY_ID))
        scene_id = int(call.data[ATTR_RUN_SCENE_ID])
        await coordinator.client.run_scene(scene_id)
        _LOGGER.debug("Triggered Sinum scene %d via service", scene_id)

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
    _register_service_if_missing(
        hass,
        SERVICE_RUN_SCENE,
        handle_run_scene,
        RUN_SCENE_SCHEMA,
    )


def _remove_entry_runtime_data(hass: HomeAssistant, entry_id: str) -> None:
    _notification_clients(hass).pop(entry_id, None)
    _coordinators(hass).pop(entry_id, None)


def _remove_domain_services_if_no_coordinators(hass: HomeAssistant) -> None:
    if _coordinators(hass):
        return
    for svc in (
        SERVICE_SEND_NOTIFICATION,
        SERVICE_UPDATE_SCHEDULE,
        SERVICE_UPLOAD_MQTT_BRIDGE,
        SERVICE_RUN_SCENE,
    ):
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
