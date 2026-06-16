"""MQTT real-time transport for Sinapse.

When configured, this module:
  - Subscribes to sinum/state/# and sinum/event/#
  - Updates coordinator data in-place on each incoming message
  - Triggers entity state refresh without waiting for the poll cycle
  - Publishes commands to sinum/cmd/{device_id} instead of REST PATCH

Topic schema
------------
sinum/state/<device_id>     Device state JSON  (Sinum → HA)
sinum/event/<type>          Hub event JSON     (Sinum → HA)
sinum/cmd/<device_id>       Command JSON       (HA → Sinum)
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant, callback

if TYPE_CHECKING:
    from .coordinator import SinumCoordinator

_LOGGER = logging.getLogger(__name__)

TOPIC_STATE = "sinum/state/#"
TOPIC_EVENT = "sinum/event/#"
TOPIC_CMD = "sinum/cmd/{device_id}"


class SinumMqttBridge:
    """Bridges Sinum MQTT topics to the coordinator data store."""

    def __init__(self, hass: HomeAssistant, coordinator: SinumCoordinator) -> None:
        self._hass = hass
        self._coordinator = coordinator
        self._unsub: list[Any] = []

    async def async_start(self) -> None:
        """Subscribe to Sinum MQTT topics."""
        if not await mqtt.async_wait_for_mqtt_client(self._hass):
            _LOGGER.warning("MQTT client not available — real-time updates disabled")
            return

        self._unsub.append(
            await mqtt.async_subscribe(self._hass, TOPIC_STATE, self._handle_state)
        )
        self._unsub.append(
            await mqtt.async_subscribe(self._hass, TOPIC_EVENT, self._handle_event)
        )
        _LOGGER.info("Sinapse MQTT bridge active — subscribed to sinum/#")

    async def async_stop(self) -> None:
        """Unsubscribe from all MQTT topics."""
        for unsub in self._unsub:
            unsub()
        self._unsub.clear()
        _LOGGER.debug("Sinapse MQTT bridge stopped")

    @callback
    def _handle_state(self, msg: mqtt.ReceiveMessage) -> None:
        """Handle sinum/state/<device_id> messages."""
        try:
            device_id = int(msg.topic.split("/")[-1])
        except ValueError:
            _LOGGER.debug("Unexpected state topic: %s", msg.topic)
            return

        try:
            payload: dict[str, Any] = json.loads(msg.payload)
        except json.JSONDecodeError:
            _LOGGER.warning("Invalid JSON on %s: %s", msg.topic, msg.payload)
            return

        source = payload.get("source", "virtual")
        if source == "wtp":
            store = self._coordinator.wtp_devices
        elif source == "sbus":
            store = self._coordinator.sbus_devices
        else:
            store = self._coordinator.virtual_devices

        if device_id in store:
            store[device_id].update(payload)
        else:
            payload["_id"] = device_id
            store[device_id] = payload

        # Push entity refresh without a full coordinator poll
        self._coordinator.async_set_updated_data(
            {
                "virtual": self._coordinator.virtual_devices,
                "wtp": self._coordinator.wtp_devices,
                "sbus": self._coordinator.sbus_devices,
            }
        )
        _LOGGER.debug("MQTT state update: device %s → %s", device_id, payload)

    @callback
    def _handle_event(self, msg: mqtt.ReceiveMessage) -> None:
        """Handle sinum/event/<type> messages → fire HA events for automations."""
        event_type = msg.topic.split("/")[-1]
        try:
            payload: dict[str, Any] = json.loads(msg.payload)
        except json.JSONDecodeError:
            payload = {"raw": str(msg.payload)}

        # Fire as a HA event so automations can react
        self._hass.bus.async_fire(
            f"sinum_{event_type}",
            payload,
        )
        _LOGGER.debug("MQTT event: sinum_%s → %s", event_type, payload)

    async def async_publish_command(self, device_id: int, payload: dict[str, Any]) -> None:
        """Publish a device command to sinum/cmd/<device_id>."""
        topic = TOPIC_CMD.format(device_id=device_id)
        await mqtt.async_publish(
            self._hass,
            topic,
            json.dumps(payload),
            qos=1,
            retain=False,
        )
        _LOGGER.debug("MQTT command → %s: %s", topic, payload)
