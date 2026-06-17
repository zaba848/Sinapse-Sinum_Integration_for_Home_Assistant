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

    def test_state_update_ignores_unsupported_source(self, coordinator):
        hass = MagicMock()
        bridge = SinumMqttBridge(hass, coordinator)
        msg = SimpleNamespace(
            topic="sinum/state/77",
            payload=json.dumps({"source": "lora", "state": True}),
        )

        bridge._handle_state(msg)

        assert 77 not in coordinator.virtual_devices
        coordinator.async_set_updated_data.assert_not_called()

    def test_event_message_fires_home_assistant_event(self, coordinator):
        hass = MagicMock()
        bridge = SinumMqttBridge(hass, coordinator)
        msg = SimpleNamespace(
            topic="sinum/event/heartbeat",
            payload=json.dumps({"ts": 123}),
        )

        bridge._handle_event(msg)

        hass.bus.async_fire.assert_called_once_with("sinum_heartbeat", {"ts": 123})
