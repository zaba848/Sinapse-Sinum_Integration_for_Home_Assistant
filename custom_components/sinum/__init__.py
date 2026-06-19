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
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SinumClient
from .const import (
    ATTR_ENTRY_ID,
    ATTR_NOTIFICATION_MESSAGE,
    ATTR_NOTIFICATION_TITLE,
    ATTR_PAYLOAD,
    ATTR_SCHEDULE_ID,
    AUTH_MODE_TOKEN,
    CONF_API_TOKEN,
    CONF_AUTH_MODE,
    CONF_MQTT_ENABLED,
    CONF_MQTT_TOPIC_PREFIX,
    DEFAULT_MQTT_TOPIC_PREFIX,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SERVICE_SEND_NOTIFICATION,
    SERVICE_UPDATE_SCHEDULE,
)
from .coordinator import SinumCoordinator
from .mqtt import SinumMqttBridge

_LOGGER = logging.getLogger(__name__)

DATA_NOTIFICATION_CLIENTS = "notification_clients"
DATA_COORDINATORS = "coordinators"

PLATFORMS: list[Platform] = [
    Platform.ALARM_CONTROL_PANEL,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
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

SinumConfigEntry: TypeAlias = ConfigEntry[SinumCoordinator]

_MQTT_BRIDGES: dict[str, SinumMqttBridge] = {}


def _notification_clients(hass: HomeAssistant) -> dict[str, SinumClient]:
    domain_data = hass.data.setdefault(DOMAIN, {})
    return cast(dict[str, SinumClient], domain_data.setdefault(DATA_NOTIFICATION_CLIENTS, {}))


def _coordinators(hass: HomeAssistant) -> dict[str, SinumCoordinator]:
    domain_data = hass.data.setdefault(DOMAIN, {})
    return cast(dict[str, SinumCoordinator], domain_data.setdefault(DATA_COORDINATORS, {}))


def _select_coordinator(hass: HomeAssistant, entry_id: str | None) -> SinumCoordinator:
    coordinators = _coordinators(hass)
    if entry_id:
        coordinator = coordinators.get(entry_id)
        if coordinator is None:
            raise HomeAssistantError(f"Sinum config entry not loaded: {entry_id}")
        return coordinator
    if len(coordinators) == 1:
        return next(iter(coordinators.values()))
    if coordinators:
        raise HomeAssistantError("entry_id is required when multiple Sinum hubs are loaded")
    raise HomeAssistantError("No Sinum hubs are loaded")


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


async def async_setup_entry(hass: HomeAssistant, entry: SinumConfigEntry) -> bool:
    client = _build_client(hass, entry)
    await client.login()

    opts = {**entry.data, **entry.options}
    coordinator = SinumCoordinator(
        hass,
        client,
        scan_interval=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # Sync config entry title with actual hub name (fixes stale IP-based titles)
    hub_name = coordinator.hub_info.get("name") or coordinator.hub_info.get("hostname")
    if hub_name:
        expected_title = f"Sinum ({hub_name})"
        if entry.title != expected_title and hass.config_entries.async_get_entry(entry.entry_id):
            hass.config_entries.async_update_entry(entry, title=expected_title)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Start MQTT bridge if enabled
    if opts.get(CONF_MQTT_ENABLED, False):
        bridge = SinumMqttBridge(
            hass,
            coordinator,
            topic_prefix=opts.get(CONF_MQTT_TOPIC_PREFIX, DEFAULT_MQTT_TOPIC_PREFIX),
        )
        if await bridge.async_start():
            _MQTT_BRIDGES[entry.entry_id] = bridge
            coordinator.mqtt_bridge = bridge

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _notification_clients(hass)[entry.entry_id] = client
    _coordinators(hass)[entry.entry_id] = coordinator

    # Push notification service. Register once per HA instance; with multiple hubs loaded,
    # the service broadcasts to all currently loaded Sinum clients.
    async def handle_send_notification(call: ServiceCall) -> None:
        await asyncio.gather(
            *(
                notification_client.send_notification(
                    title=call.data[ATTR_NOTIFICATION_TITLE],
                    message=call.data[ATTR_NOTIFICATION_MESSAGE],
                )
                for notification_client in _notification_clients(hass).values()
            )
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SEND_NOTIFICATION):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SEND_NOTIFICATION,
            handle_send_notification,
            schema=NOTIFY_SCHEMA,
        )

    async def handle_update_schedule(call: ServiceCall) -> None:
        coordinator = _select_coordinator(hass, call.data.get(ATTR_ENTRY_ID))
        schedule_id = call.data[ATTR_SCHEDULE_ID]
        payload = dict(call.data[ATTR_PAYLOAD])
        updated = await coordinator.client.patch_schedule(schedule_id, payload)
        _merge_schedule(coordinator, schedule_id, updated or payload)
        _publish_schedule_update(coordinator)

    if not hass.services.has_service(DOMAIN, SERVICE_UPDATE_SCHEDULE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_UPDATE_SCHEDULE,
            handle_update_schedule,
            schema=UPDATE_SCHEDULE_SCHEMA,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: SinumConfigEntry) -> bool:
    # Stop MQTT bridge
    bridge = _MQTT_BRIDGES.pop(entry.entry_id, None)
    if bridge:
        await bridge.async_stop()

    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        _notification_clients(hass).pop(entry.entry_id, None)
        _coordinators(hass).pop(entry.entry_id, None)
    if (
        unloaded
        and not _coordinators(hass)
        and hass.services.has_service(DOMAIN, SERVICE_SEND_NOTIFICATION)
    ):
        hass.services.async_remove(DOMAIN, SERVICE_SEND_NOTIFICATION)
    if (
        unloaded
        and not _coordinators(hass)
        and hass.services.has_service(DOMAIN, SERVICE_UPDATE_SCHEDULE)
    ):
        hass.services.async_remove(DOMAIN, SERVICE_UPDATE_SCHEDULE)
    return unloaded
