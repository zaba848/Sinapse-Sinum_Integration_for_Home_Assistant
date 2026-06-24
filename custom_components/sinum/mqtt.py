"""MQTT real-time transport for Sinapse.

When configured, this module:
  - Subscribes to <topic_prefix>/state/# and <topic_prefix>/event/#
  - Updates coordinator data in-place on each incoming message
  - Triggers entity state refresh without waiting for the poll cycle
  - Keeps device commands on REST PATCH until MQTT write payloads are verified

Topic schema
------------
sinum/state/<device_id>     Device state JSON  (Sinum → HA, default prefix)
sinum/event/<type>          Hub event JSON     (Sinum → HA, default prefix)
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant, callback

from .const import DEFAULT_MQTT_TOPIC_PREFIX

if TYPE_CHECKING:
    from .coordinator import SinumCoordinator

_LOGGER = logging.getLogger(__name__)

TOPIC_STATE = "sinum/state/#"
TOPIC_EVENT = "sinum/event/#"
TOPIC_CMD = "sinum/cmd/{device_id}"


def normalize_topic_prefix(topic_prefix: str | None) -> str:
    """Normalize an MQTT topic prefix used by one Sinum hub."""
    prefix = (topic_prefix or DEFAULT_MQTT_TOPIC_PREFIX).strip().strip("/")
    return prefix or DEFAULT_MQTT_TOPIC_PREFIX


class SinumMqttBridge:
    """Bridges Sinum MQTT topics to the coordinator data store."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: SinumCoordinator,
        topic_prefix: str | None = None,
    ) -> None:
        self._hass = hass
        self._coordinator = coordinator
        self._topic_prefix = normalize_topic_prefix(topic_prefix)
        self._state_topic = f"{self._topic_prefix}/state/#"
        self._event_topic = f"{self._topic_prefix}/event/#"
        self._unsub: list[Any] = []

    async def async_start(self) -> bool:
        """Subscribe to Sinum MQTT topics."""
        if not await mqtt.async_wait_for_mqtt_client(self._hass):
            _LOGGER.warning("MQTT client not available — real-time updates disabled")
            return False

        self._unsub.append(
            await mqtt.async_subscribe(self._hass, self._state_topic, self._handle_state)
        )
        self._unsub.append(
            await mqtt.async_subscribe(self._hass, self._event_topic, self._handle_event)
        )
        _LOGGER.info("Sinapse MQTT bridge active — subscribed to %s/#", self._topic_prefix)
        return True

    async def async_stop(self) -> None:
        """Unsubscribe from all MQTT topics."""
        for unsub in self._unsub:
            unsub()
        self._unsub.clear()
        _LOGGER.debug("Sinapse MQTT bridge stopped")

    def _state_device_id(self, topic: str) -> int | None:
        state_prefix = f"{self._topic_prefix}/state/"
        if not topic.startswith(state_prefix):
            _LOGGER.debug("Ignoring MQTT state outside prefix %s: %s", self._topic_prefix, topic)
            return None
        try:
            return int(topic.removeprefix(state_prefix).split("/")[-1])
        except ValueError:
            _LOGGER.debug("Unexpected state topic: %s", topic)
            return None

    def _state_payload(self, msg: mqtt.ReceiveMessage) -> dict[str, Any] | None:
        try:
            return json.loads(msg.payload)
        except json.JSONDecodeError:
            _LOGGER.warning("Invalid JSON on %s: %s", msg.topic, msg.payload)
            return None

    def _store_for_source(self, source: str) -> dict[int, dict[str, Any]] | None:
        stores = {
            "virtual": self._coordinator.virtual_devices,
            "wtp": self._coordinator.wtp_devices,
            "sbus": self._coordinator.sbus_devices,
            "lora": self._coordinator.lora_devices,
        }
        return stores.get(source)

    def _apply_state_update(
        self, store: dict[int, dict[str, Any]], device_id: int, payload: dict[str, Any]
    ) -> None:
        if device_id in store:
            store[device_id].update(payload)
            return
        payload["_id"] = device_id
        store[device_id] = payload

    def _publish_coordinator_data(self) -> None:
        self._coordinator.async_set_updated_data(
            {
                "virtual": self._coordinator.virtual_devices,
                "wtp": self._coordinator.wtp_devices,
                "sbus": self._coordinator.sbus_devices,
                "lora": self._coordinator.lora_devices,
            }
        )

    @callback
    def _handle_state(self, msg: mqtt.ReceiveMessage) -> None:
        """Handle <topic_prefix>/state/<device_id> messages."""
        device_id = self._state_device_id(msg.topic)
        if device_id is None:
            return

        payload = self._state_payload(msg)
        if payload is None:
            return

        source = payload.get("source", "virtual")
        store = self._store_for_source(source)
        if store is None:
            _LOGGER.debug("Ignoring MQTT state for unsupported source %s: %s", source, payload)
            return

        self._apply_state_update(store, device_id, payload)

        # Push entity refresh without a full coordinator poll
        self._publish_coordinator_data()
        _LOGGER.debug("MQTT state update: device %s → %s", device_id, payload)

    @callback
    def _handle_event(self, msg: mqtt.ReceiveMessage) -> None:
        """Handle <topic_prefix>/event/<type> messages → fire HA events for automations."""
        event_prefix = f"{self._topic_prefix}/event/"
        if not msg.topic.startswith(event_prefix):
            _LOGGER.debug(
                "Ignoring MQTT event outside prefix %s: %s", self._topic_prefix, msg.topic
            )
            return

        event_type = msg.topic.removeprefix(event_prefix).split("/")[-1]
        try:
            payload: dict[str, Any] = json.loads(msg.payload)
        except json.JSONDecodeError:
            payload = {"raw": str(msg.payload)}
        payload["topic_prefix"] = self._topic_prefix

        # Fire as a HA event so automations can react
        self._hass.bus.async_fire(
            f"sinum_{event_type}",
            payload,
        )
        _LOGGER.debug("MQTT event: sinum_%s → %s", event_type, payload)

    async def async_publish_command(self, device_id: int, payload: dict[str, Any]) -> None:
        """Publish a device command to <topic_prefix>/cmd/<device_id>."""
        topic = f"{self._topic_prefix}/cmd/{device_id}"
        await mqtt.async_publish(
            self._hass,
            topic,
            json.dumps(payload),
            qos=1,
            retain=False,
        )
        _LOGGER.debug("MQTT command → %s: %s", topic, payload)
