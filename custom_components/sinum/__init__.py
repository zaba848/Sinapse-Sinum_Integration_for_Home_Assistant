from __future__ import annotations

import logging
from typing import TypeAlias

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SinumClient
from .const import (
    AUTH_MODE_TOKEN,
    CONF_API_TOKEN,
    CONF_AUTH_MODE,
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
from .services import (
    DATA_COORDINATORS,
    DATA_NOTIFICATION_CLIENTS,
    NOTIFY_SCHEMA,
    RUN_SCENE_SCHEMA,
    UPDATE_SCHEDULE_SCHEMA,
    UPLOAD_MQTT_BRIDGE_SCHEMA,
)
from .services import (
    coordinators as _coordinators,
)
from .services import (
    merge_schedule as _merge_schedule,
)
from .services import (
    notification_clients as _notification_clients,
)
from .services import (
    register_services as _register_services,
)
from .services import (
    remove_domain_services_if_no_coordinators as _remove_domain_services_if_no_coordinators,
)
from .services import (
    remove_entry_runtime_data as _remove_entry_runtime_data,
)
from .services import (
    select_coordinator as _select_coordinator,
)

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "DATA_COORDINATORS",
    "DATA_NOTIFICATION_CLIENTS",
    "DOMAIN",
    "NOTIFY_SCHEMA",
    "PLATFORMS",
    "RUN_SCENE_SCHEMA",
    "SERVICE_RUN_SCENE",
    "SERVICE_SEND_NOTIFICATION",
    "SERVICE_UPDATE_SCHEDULE",
    "SERVICE_UPLOAD_MQTT_BRIDGE",
    "SinumConfigEntry",
    "UPDATE_SCHEDULE_SCHEMA",
    "UPLOAD_MQTT_BRIDGE_SCHEMA",
    "_build_client",
    "_coordinators",
    "_merge_schedule",
    "_render_mqtt_bridge_lua",
    "_select_coordinator",
    "_sync_entry_title",
    "async_migrate_entry",
    "async_setup_entry",
    "async_unload_entry",
]

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

SinumConfigEntry: TypeAlias = ConfigEntry[SinumCoordinator]


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
