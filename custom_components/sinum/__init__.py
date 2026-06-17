from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SinumClient
from .const import (
    ATTR_NOTIFICATION_MESSAGE,
    ATTR_NOTIFICATION_TITLE,
    AUTH_MODE_TOKEN,
    CONF_API_TOKEN,
    CONF_AUTH_MODE,
    CONF_MQTT_ENABLED,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SERVICE_SEND_NOTIFICATION,
)
from .coordinator import SinumCoordinator
from .mqtt import SinumMqttBridge

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.ALARM_CONTROL_PANEL,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.COVER,
    Platform.EVENT,
    Platform.LIGHT,
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

SinumConfigEntry = ConfigEntry[SinumCoordinator]

_MQTT_BRIDGES: dict[str, SinumMqttBridge] = {}


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

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Start MQTT bridge if enabled
    if opts.get(CONF_MQTT_ENABLED, False):
        bridge = SinumMqttBridge(hass, coordinator)
        if await bridge.async_start():
            _MQTT_BRIDGES[entry.entry_id] = bridge
            coordinator.mqtt_bridge = bridge

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Push notification service
    async def handle_send_notification(call: ServiceCall) -> None:
        await client.send_notification(
            title=call.data[ATTR_NOTIFICATION_TITLE],
            message=call.data[ATTR_NOTIFICATION_MESSAGE],
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_NOTIFICATION,
        handle_send_notification,
        schema=NOTIFY_SCHEMA,
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: SinumConfigEntry) -> bool:
    # Stop MQTT bridge
    bridge = _MQTT_BRIDGES.pop(entry.entry_id, None)
    if bridge:
        await bridge.async_stop()

    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded and not hass.config_entries.async_entries(DOMAIN):
        hass.services.async_remove(DOMAIN, SERVICE_SEND_NOTIFICATION)
    return unloaded
