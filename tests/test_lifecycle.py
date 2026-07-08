"""Direct unit tests for lifecycle bridge helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sinum.const import (
    CONF_MQTT_ENABLED,
    CONF_MQTT_TOPIC_PREFIX,
    CONF_WS_ENABLED,
    CONF_WS_PATH,
    DEFAULT_MQTT_TOPIC_PREFIX,
    DEFAULT_WS_PATH,
)
from custom_components.sinum.lifecycle import (
    _MQTT_BRIDGES,
    _WS_BRIDGES,
    start_mqtt_bridge,
    start_realtime_bridge,
    start_ws_bridge,
    stop_mqtt_bridge,
    stop_ws_bridge,
)


@pytest.mark.asyncio
async def test_start_mqtt_bridge_skips_when_disabled(hass):
    coordinator = MagicMock()
    entry = MagicMock(entry_id="e1")
    await start_mqtt_bridge(hass, entry, coordinator, {CONF_MQTT_ENABLED: False})
    assert "e1" not in _MQTT_BRIDGES


@pytest.mark.asyncio
async def test_start_mqtt_bridge_skips_when_start_fails(hass):
    coordinator = MagicMock()
    coordinator.mqtt_bridge = None
    entry = MagicMock(entry_id="e2")
    bridge = MagicMock()
    bridge.async_start = AsyncMock(return_value=False)

    with patch(
        "custom_components.sinum.lifecycle.SinumMqttBridge",
        return_value=bridge,
    ):
        await start_mqtt_bridge(
            hass,
            entry,
            coordinator,
            {CONF_MQTT_ENABLED: True, CONF_MQTT_TOPIC_PREFIX: DEFAULT_MQTT_TOPIC_PREFIX},
        )

    assert "e2" not in _MQTT_BRIDGES


@pytest.mark.asyncio
async def test_start_ws_bridge_returns_false_when_disabled(hass):
    coordinator = MagicMock()
    entry = MagicMock(entry_id="e3")
    result = await start_ws_bridge(hass, entry, coordinator, {CONF_WS_ENABLED: False})
    assert result is False


@pytest.mark.asyncio
async def test_start_ws_bridge_returns_false_when_start_fails(hass):
    coordinator = MagicMock()
    coordinator.client = MagicMock()
    entry = MagicMock(entry_id="e4")
    bridge = MagicMock()
    bridge.async_start = AsyncMock(return_value=False)

    with patch(
        "custom_components.sinum.lifecycle.SinumWebSocketBridge",
        return_value=bridge,
    ):
        result = await start_ws_bridge(
            hass,
            entry,
            coordinator,
            {CONF_WS_ENABLED: True, CONF_WS_PATH: DEFAULT_WS_PATH},
        )

    assert result is False
    assert "e4" not in _WS_BRIDGES


@pytest.mark.asyncio
async def test_start_realtime_bridge_falls_back_to_mqtt(hass):
    coordinator = MagicMock()
    coordinator.mqtt_bridge = None
    entry = MagicMock(entry_id="e5")
    ws_bridge = MagicMock()
    ws_bridge.async_start = AsyncMock(return_value=False)
    mqtt_bridge = MagicMock()
    mqtt_bridge.async_start = AsyncMock(return_value=True)

    with (
        patch(
            "custom_components.sinum.lifecycle.SinumWebSocketBridge",
            return_value=ws_bridge,
        ),
        patch(
            "custom_components.sinum.lifecycle.SinumMqttBridge",
            return_value=mqtt_bridge,
        ),
    ):
        await start_realtime_bridge(
            hass,
            entry,
            coordinator,
            {CONF_WS_ENABLED: True, CONF_MQTT_ENABLED: True},
        )

    assert "e5" in _MQTT_BRIDGES
    _MQTT_BRIDGES.pop("e5", None)


@pytest.mark.asyncio
async def test_stop_mqtt_bridge_noop_when_missing():
    await stop_mqtt_bridge("missing_mqtt_entry")


@pytest.mark.asyncio
async def test_stop_ws_bridge_noop_when_missing():
    await stop_ws_bridge("missing_ws_entry")


@pytest.mark.asyncio
async def test_stop_mqtt_bridge_stops_active_bridge():
    bridge = MagicMock()
    bridge.async_stop = AsyncMock()
    _MQTT_BRIDGES["stop_mqtt"] = bridge
    await stop_mqtt_bridge("stop_mqtt")
    bridge.async_stop.assert_awaited_once()
    assert "stop_mqtt" not in _MQTT_BRIDGES


@pytest.mark.asyncio
async def test_stop_ws_bridge_stops_active_bridge():
    bridge = MagicMock()
    bridge.async_stop = AsyncMock()
    _WS_BRIDGES["stop_ws"] = bridge
    await stop_ws_bridge("stop_ws")
    bridge.async_stop.assert_awaited_once()
    assert "stop_ws" not in _WS_BRIDGES
