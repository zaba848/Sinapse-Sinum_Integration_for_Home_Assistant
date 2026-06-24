"""Device triggers for Sinum button devices.

Exposes button presses as Device Triggers in the HA automation editor so
users can pick "Sinum button pressed" directly from the device card without
manually writing event entity trigger configs.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.event import DOMAIN as EVENT_DOMAIN
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo

from .const import DOMAIN

TRIGGER_TYPE_PRESSED = "pressed"
TRIGGER_TYPES = {TRIGGER_TYPE_PRESSED}

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend({vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES)})


async def async_validate_trigger_config(
    hass: HomeAssistant, config: dict[str, Any]
) -> dict[str, Any]:
    return TRIGGER_SCHEMA(config)


async def async_get_triggers(hass: HomeAssistant, device_id: str) -> list[dict[str, Any]]:
    """Return a 'pressed' trigger for each Sinum button event entity on this device."""
    ent_reg = er.async_get(hass)
    return [
        {
            CONF_PLATFORM: "device",
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: device_id,
            CONF_TYPE: TRIGGER_TYPE_PRESSED,
        }
        for entry in er.async_entries_for_device(ent_reg, device_id)
        if entry.domain == EVENT_DOMAIN and entry.platform == DOMAIN
    ]


async def async_attach_trigger(
    hass: HomeAssistant,
    config: dict[str, Any],
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a trigger that fires when any Sinum button on the device is pressed."""
    device_id = config[CONF_DEVICE_ID]
    ent_reg = er.async_get(hass)

    event_entity_ids: set[str] = {
        entry.entity_id
        for entry in er.async_entries_for_device(ent_reg, device_id)
        if entry.domain == EVENT_DOMAIN and entry.platform == DOMAIN
    }

    if not event_entity_ids:
        return lambda: None

    @callback
    def _state_changed(event: Event) -> None:
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        if new_state.entity_id not in event_entity_ids:
            return
        # Skip the initial state write (entity just added, no real press yet)
        if event.data.get("old_state") is None:
            return
        hass.async_run_hass_job(
            action,
            {
                "trigger": {
                    **config,
                    "description": f"button pressed on {new_state.entity_id}",
                },
                "action": new_state.attributes.get("action"),
                "entity_id": new_state.entity_id,
            },
        )

    return hass.bus.async_listen("state_changed", _state_changed)
