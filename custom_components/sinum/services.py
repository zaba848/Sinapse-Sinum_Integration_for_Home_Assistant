"""Home Assistant service handlers for the Sinum integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

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
    CONF_MQTT_CLIENT_ID,
    CONF_MQTT_SCENE_ID,
    CONF_MQTT_TOPIC_PREFIX,
    DEFAULT_MQTT_CLIENT_ID,
    DEFAULT_MQTT_SCENE_ID,
    DEFAULT_MQTT_TOPIC_PREFIX,
    DOMAIN,
    SERVICE_RUN_SCENE,
    SERVICE_SEND_NOTIFICATION,
    SERVICE_UPDATE_SCHEDULE,
    SERVICE_UPLOAD_MQTT_BRIDGE,
)
from .coordinator import SinumCoordinator
from .lua_mqtt_bridge import render as _render_mqtt_bridge_lua

_LOGGER = logging.getLogger(__name__)

DATA_NOTIFICATION_CLIENTS = "notification_clients"
DATA_COORDINATORS = "coordinators"

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


def notification_clients(hass: HomeAssistant) -> dict[str, SinumClient]:
    domain_data = hass.data.setdefault(DOMAIN, {})
    return cast(dict[str, SinumClient], domain_data.setdefault(DATA_NOTIFICATION_CLIENTS, {}))


def coordinators(hass: HomeAssistant) -> dict[str, SinumCoordinator]:
    domain_data = hass.data.setdefault(DOMAIN, {})
    return cast(dict[str, SinumCoordinator], domain_data.setdefault(DATA_COORDINATORS, {}))


def _single_coordinator_or_raise(coordinators_map: dict[str, SinumCoordinator]) -> SinumCoordinator:
    if len(coordinators_map) == 1:
        return next(iter(coordinators_map.values()))
    if coordinators_map:
        raise HomeAssistantError("entry_id is required when multiple Sinum hubs are loaded")
    raise HomeAssistantError("No Sinum hubs are loaded")


def select_coordinator(hass: HomeAssistant, entry_id: str | None) -> SinumCoordinator:
    coordinators_map = coordinators(hass)
    if not entry_id:
        return _single_coordinator_or_raise(coordinators_map)
    coordinator = coordinators_map.get(entry_id)
    if coordinator is None:
        raise HomeAssistantError(f"Sinum config entry not loaded: {entry_id}")
    return coordinator


def merge_schedule(
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


def publish_schedule_update(coordinator: SinumCoordinator) -> None:
    data = coordinator.data if isinstance(coordinator.data, dict) else {}
    coordinator.async_set_updated_data({**data, "schedules": coordinator.schedules})


def _register_service_if_missing(
    hass: HomeAssistant,
    service: str,
    handler: Any,
    schema: vol.Schema,
) -> None:
    if hass.services.has_service(DOMAIN, service):
        return
    hass.services.async_register(DOMAIN, service, handler, schema=schema)


def register_services(hass: HomeAssistant) -> None:
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

        await asyncio.gather(*(_send(c) for c in notification_clients(hass).values()))

    async def handle_update_schedule(call: ServiceCall) -> None:
        coordinator = select_coordinator(hass, call.data.get(ATTR_ENTRY_ID))
        schedule_id = call.data[ATTR_SCHEDULE_ID]
        payload = dict(call.data[ATTR_PAYLOAD])
        updated = await coordinator.client.patch_schedule(schedule_id, payload)
        merge_schedule(coordinator, schedule_id, updated or payload)
        publish_schedule_update(coordinator)

    async def handle_run_scene(call: ServiceCall) -> None:
        coordinator = select_coordinator(hass, call.data.get(ATTR_ENTRY_ID))
        scene_id = int(call.data[ATTR_RUN_SCENE_ID])
        await coordinator.client.run_scene(scene_id)
        _LOGGER.debug("Triggered Sinum scene %d via service", scene_id)

    async def handle_upload_mqtt_bridge(call: ServiceCall) -> None:
        coordinator = select_coordinator(hass, call.data.get(ATTR_ENTRY_ID))
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


def remove_entry_runtime_data(hass: HomeAssistant, entry_id: str) -> None:
    notification_clients(hass).pop(entry_id, None)
    coordinators(hass).pop(entry_id, None)


def remove_domain_services_if_no_coordinators(hass: HomeAssistant) -> None:
    if coordinators(hass):
        return
    for svc in (
        SERVICE_SEND_NOTIFICATION,
        SERVICE_UPDATE_SCHEDULE,
        SERVICE_UPLOAD_MQTT_BRIDGE,
        SERVICE_RUN_SCENE,
    ):
        if hass.services.has_service(DOMAIN, svc):
            hass.services.async_remove(DOMAIN, svc)
