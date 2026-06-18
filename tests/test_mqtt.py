"""Tests for Sinum MQTT bridge."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sinum.mqtt import SinumMqttBridge


@pytest.fixture(name="coordinator")
def coordinator_fixture() -> MagicMock:
    coordinator = MagicMock()
    coordinator.virtual_devices = {10: {"id": 10, "source": "virtual", "state": False}}
    coordinator.wtp_devices = {}
    coordinator.sbus_devices = {}
    coordinator.lora_devices = {}
    coordinator.async_set_updated_data = MagicMock()
    return coordinator


class TestSinumMqttBridge:
    @pytest.mark.asyncio
    async def test_start_returns_false_without_mqtt_client(self, coordinator):
        hass = MagicMock()
        bridge = SinumMqttBridge(hass, coordinator)

        with (
            patch("custom_components.sinum.mqtt.mqtt.async_wait_for_mqtt_client", AsyncMock(return_value=False)),
            patch("custom_components.sinum.mqtt.mqtt.async_subscribe", AsyncMock()) as subscribe,
        ):
            assert await bridge.async_start() is False

        subscribe.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_subscribes_to_state_and_event_topics(self, coordinator):
        hass = MagicMock()
        unsub_state = MagicMock()
        unsub_event = MagicMock()
        bridge = SinumMqttBridge(hass, coordinator)

        with (
            patch("custom_components.sinum.mqtt.mqtt.async_wait_for_mqtt_client", AsyncMock(return_value=True)),
            patch(
                "custom_components.sinum.mqtt.mqtt.async_subscribe",
                AsyncMock(side_effect=[unsub_state, unsub_event]),
            ) as subscribe,
        ):
            assert await bridge.async_start() is True
            await bridge.async_stop()

        assert subscribe.await_count == 2
        assert subscribe.await_args_list[0].args[1] == "sinum/state/#"
        assert subscribe.await_args_list[1].args[1] == "sinum/event/#"
        unsub_state.assert_called_once()
        unsub_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_subscribes_to_custom_topic_prefix(self, coordinator):
        hass = MagicMock()
        bridge = SinumMqttBridge(hass, coordinator, topic_prefix="sinum/tablica-wtp")

        with (
            patch("custom_components.sinum.mqtt.mqtt.async_wait_for_mqtt_client", AsyncMock(return_value=True)),
            patch(
                "custom_components.sinum.mqtt.mqtt.async_subscribe",
                AsyncMock(side_effect=[MagicMock(), MagicMock()]),
            ) as subscribe,
        ):
            assert await bridge.async_start() is True

        assert subscribe.await_args_list[0].args[1] == "sinum/tablica-wtp/state/#"
        assert subscribe.await_args_list[1].args[1] == "sinum/tablica-wtp/event/#"

    def test_state_update_merges_supported_source(self, coordinator):
        hass = MagicMock()
        bridge = SinumMqttBridge(hass, coordinator)
        msg = SimpleNamespace(
            topic="sinum/state/10",
            payload=json.dumps({"source": "virtual", "state": True}),
        )

        bridge._handle_state(msg)

        assert coordinator.virtual_devices[10]["state"] is True
        coordinator.async_set_updated_data.assert_called_once()

    def test_state_update_ignores_topic_outside_bridge_prefix(self, coordinator):
        hass = MagicMock()
        bridge = SinumMqttBridge(hass, coordinator, topic_prefix="sinum/hub-a")
        msg = SimpleNamespace(
            topic="sinum/hub-b/state/10",
            payload=json.dumps({"source": "virtual", "state": True}),
        )

        bridge._handle_state(msg)

        assert coordinator.virtual_devices[10]["state"] is False
        coordinator.async_set_updated_data.assert_not_called()

    def test_two_hubs_with_same_device_id_are_isolated_by_topic_prefix(self):
        hass = MagicMock()
        coordinator_a = MagicMock()
        coordinator_a.virtual_devices = {10: {"id": 10, "state": False}}
        coordinator_a.wtp_devices = {}
        coordinator_a.sbus_devices = {}
        coordinator_a.lora_devices = {}
        coordinator_a.async_set_updated_data = MagicMock()
        coordinator_b = MagicMock()
        coordinator_b.virtual_devices = {10: {"id": 10, "state": False}}
        coordinator_b.wtp_devices = {}
        coordinator_b.sbus_devices = {}
        coordinator_b.lora_devices = {}
        coordinator_b.async_set_updated_data = MagicMock()

        bridge_a = SinumMqttBridge(hass, coordinator_a, topic_prefix="sinum/hub-a")
        bridge_b = SinumMqttBridge(hass, coordinator_b, topic_prefix="sinum/hub-b")
        msg = SimpleNamespace(
            topic="sinum/hub-a/state/10",
            payload=json.dumps({"source": "virtual", "state": True}),
        )

        bridge_a._handle_state(msg)
        bridge_b._handle_state(msg)

        assert coordinator_a.virtual_devices[10]["state"] is True
        assert coordinator_b.virtual_devices[10]["state"] is False
        coordinator_a.async_set_updated_data.assert_called_once()
        coordinator_b.async_set_updated_data.assert_not_called()

    def test_state_update_ignores_unsupported_source(self, coordinator):
        hass = MagicMock()
        bridge = SinumMqttBridge(hass, coordinator)
        msg = SimpleNamespace(
            topic="sinum/state/77",
            payload=json.dumps({"source": "modbus", "state": True}),
        )

        bridge._handle_state(msg)

        assert 77 not in coordinator.virtual_devices
        coordinator.async_set_updated_data.assert_not_called()

    def test_lora_state_update_is_stored_in_lora_devices(self, coordinator):
        hass = MagicMock()
        bridge = SinumMqttBridge(hass, coordinator)
        msg = SimpleNamespace(
            topic="sinum/state/77",
            payload=json.dumps({"source": "lora", "state": True}),
        )

        bridge._handle_state(msg)

        assert coordinator.lora_devices[77]["state"] is True
        coordinator.async_set_updated_data.assert_called_once()

    def test_event_message_fires_home_assistant_event(self, coordinator):
        hass = MagicMock()
        bridge = SinumMqttBridge(hass, coordinator)
        msg = SimpleNamespace(
            topic="sinum/event/heartbeat",
            payload=json.dumps({"ts": 123}),
        )

        bridge._handle_event(msg)

        hass.bus.async_fire.assert_called_once_with(
            "sinum_heartbeat",
            {"ts": 123, "topic_prefix": "sinum"},
        )

    def test_event_message_ignores_topic_outside_bridge_prefix(self, coordinator):
        hass = MagicMock()
        bridge = SinumMqttBridge(hass, coordinator, topic_prefix="sinum/hub-a")
        msg = SimpleNamespace(
            topic="sinum/hub-b/event/heartbeat",
            payload=json.dumps({"ts": 123}),
        )

        bridge._handle_event(msg)

        hass.bus.async_fire.assert_not_called()

    def test_state_topic_with_invalid_device_id_is_ignored(self, coordinator):
        """Lines 65-67: ValueError when topic last segment is not an integer."""
        hass = MagicMock()
        bridge = SinumMqttBridge(hass, coordinator)
        msg = SimpleNamespace(
            topic="sinum/state/abc",
            payload=json.dumps({"source": "virtual", "state": True}),
        )

        bridge._handle_state(msg)

        coordinator.async_set_updated_data.assert_not_called()

    def test_state_payload_invalid_json_is_ignored(self, coordinator):
        """Lines 71-73: JSONDecodeError when payload is not valid JSON."""
        hass = MagicMock()
        bridge = SinumMqttBridge(hass, coordinator)
        msg = SimpleNamespace(
            topic="sinum/state/10",
            payload="not-valid-json{{",
        )

        bridge._handle_state(msg)

        coordinator.async_set_updated_data.assert_not_called()

    def test_state_new_device_added_to_store(self, coordinator):
        """Lines 89-90: device_id not in store → added as new entry."""
        hass = MagicMock()
        bridge = SinumMqttBridge(hass, coordinator)
        # device_id 99 is not in coordinator.virtual_devices
        msg = SimpleNamespace(
            topic="sinum/state/99",
            payload=json.dumps({"source": "virtual", "state": True}),
        )

        bridge._handle_state(msg)

        assert 99 in coordinator.virtual_devices
        assert coordinator.virtual_devices[99]["_id"] == 99
        coordinator.async_set_updated_data.assert_called_once()

    def test_event_invalid_json_creates_raw_payload(self, coordinator):
        """Lines 108-109: JSONDecodeError → payload set to {"raw": ...}."""
        hass = MagicMock()
        bridge = SinumMqttBridge(hass, coordinator)
        msg = SimpleNamespace(
            topic="sinum/event/alarm",
            payload="this is not json!",
        )

        bridge._handle_event(msg)

        hass.bus.async_fire.assert_called_once()
        call_args = hass.bus.async_fire.call_args
        assert call_args.args[0] == "sinum_alarm"
        assert "raw" in call_args.args[1]
        assert call_args.args[1]["topic_prefix"] == "sinum"

    @pytest.mark.asyncio
    async def test_async_publish_command(self, coordinator):
        """Lines 120-128: async_publish_command sends correct topic and JSON payload."""
        hass = MagicMock()
        bridge = SinumMqttBridge(hass, coordinator)

        with patch(
            "custom_components.sinum.mqtt.mqtt.async_publish",
            AsyncMock(),
        ) as mock_publish:
            await bridge.async_publish_command(42, {"state": True, "brightness": 80})

        mock_publish.assert_awaited_once()
        call_args = mock_publish.await_args
        assert call_args.args[1] == "sinum/cmd/42"
        published_payload = json.loads(call_args.args[2])
        assert published_payload == {"state": True, "brightness": 80}
        assert call_args.kwargs.get("qos") == 1
        assert call_args.kwargs.get("retain") is False

    @pytest.mark.asyncio
    async def test_async_publish_command_uses_custom_topic_prefix(self, coordinator):
        hass = MagicMock()
        bridge = SinumMqttBridge(hass, coordinator, topic_prefix="/sinum/hub-a/")

        with patch(
            "custom_components.sinum.mqtt.mqtt.async_publish",
            AsyncMock(),
        ) as mock_publish:
            await bridge.async_publish_command(42, {"state": True})

        assert mock_publish.await_args.args[1] == "sinum/hub-a/cmd/42"
