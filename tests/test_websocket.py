"""Tests for Sinum WebSocket bridge."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.sinum.websocket import (
    SinumWebSocketBridge,
    _device_class,
    _filter_dicts,
    _find_nested_list,
    _iter_events,
    _normalize_ws_path,
    _patch_device,
    _ws_should_continue,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _coordinator() -> MagicMock:
    coordinator = MagicMock()
    coordinator.virtual_devices = {}
    coordinator.wtp_devices = {}
    coordinator.sbus_devices = {12: {"id": 12, "class": "sbus", "humidity": 401}}
    coordinator.lora_devices = {}
    coordinator.modbus_devices = {}
    coordinator.video_devices = {}
    coordinator.data = {
        "virtual": coordinator.virtual_devices,
        "wtp": coordinator.wtp_devices,
        "sbus": coordinator.sbus_devices,
        "lora": coordinator.lora_devices,
        "modbus": coordinator.modbus_devices,
        "video": coordinator.video_devices,
    }
    coordinator.async_set_updated_data = MagicMock()
    return coordinator


def _bridge() -> tuple[SinumWebSocketBridge, MagicMock, MagicMock]:
    hass = MagicMock()
    client = MagicMock()
    coordinator = _coordinator()
    bridge = SinumWebSocketBridge(hass, client, coordinator)
    return bridge, hass, coordinator


# ── Core payload handling ─────────────────────────────────────────────────────

def test_ws_event_array_updates_only_details_field():
    bridge, hass, coordinator = _bridge()
    payload = [
        {"data": {"type": "device_state_changed", "details": "humidity",
                  "payload": {"class": "sbus", "id": 12, "humidity": 445}}},
        {"data": {"type": "device_state_changed", "details": "humidity",
                  "payload": {"class": "sbus", "id": 62, "humidity": 409}}},
    ]
    bridge._handle_payload(json.dumps(payload))
    assert coordinator.sbus_devices[12]["humidity"] == 445
    assert coordinator.sbus_devices[62]["humidity"] == 409
    coordinator.async_set_updated_data.assert_called_once()
    assert hass.bus.async_fire.call_count == 2


def test_ws_ignores_non_device_state_changed_events():
    bridge, hass, coordinator = _bridge()
    payload = [{"data": {"type": "minute_changed", "payload": {"id": 1}}}]
    bridge._handle_payload(json.dumps(payload))
    coordinator.async_set_updated_data.assert_not_called()
    hass.bus.async_fire.assert_not_called()


def test_ws_without_details_merges_full_payload():
    bridge, _hass, coordinator = _bridge()
    payload = [{"data": {"type": "device_state_changed",
                          "payload": {"class": "wtp", "id": 8, "state": True, "temperature": 220}}}]
    bridge._handle_payload(json.dumps(payload))
    assert coordinator.wtp_devices[8]["state"] is True
    assert coordinator.wtp_devices[8]["temperature"] == 220
    coordinator.async_set_updated_data.assert_called_once()


def test_ws_virtual_device_update():
    bridge, _hass, coordinator = _bridge()
    payload = [{"data": {"type": "device_state_changed", "details": "temperature",
                          "payload": {"class": "virtual", "id": 31, "temperature": 354}}}]
    bridge._handle_payload(json.dumps(payload))
    assert coordinator.virtual_devices[31]["temperature"] == 354


def test_ws_invalid_json_ignored():
    bridge, hass, coordinator = _bridge()
    bridge._handle_payload("not valid json {{{{")
    coordinator.async_set_updated_data.assert_not_called()
    hass.bus.async_fire.assert_not_called()


def test_ws_missing_id_in_payload_ignored():
    bridge, hass, coordinator = _bridge()
    payload = [{"data": {"type": "device_state_changed", "details": "val",
                          "payload": {"class": "sbus", "val": 42}}}]
    bridge._handle_payload(json.dumps(payload))
    coordinator.async_set_updated_data.assert_not_called()


def test_ws_unknown_class_ignored():
    bridge, hass, coordinator = _bridge()
    payload = [{"data": {"type": "device_state_changed", "details": "x",
                          "payload": {"class": "zigbee", "id": 5, "x": 1}}}]
    bridge._handle_payload(json.dumps(payload))
    coordinator.async_set_updated_data.assert_not_called()


def test_ws_lora_device_update():
    bridge, _hass, coordinator = _bridge()
    payload = [{"data": {"type": "device_state_changed", "details": "signal",
                          "payload": {"class": "lora", "id": 7, "signal": -88}}}]
    bridge._handle_payload(json.dumps(payload))
    assert coordinator.lora_devices[7]["signal"] == -88


def test_ws_existing_device_field_not_overwritten_by_other_details():
    """Only the 'details' field in payload should be patched when details is set."""
    bridge, _hass, coordinator = _bridge()
    coordinator.sbus_devices[12] = {"id": 12, "humidity": 401, "temperature": 250}
    payload = [{"data": {"type": "device_state_changed", "details": "humidity",
                          "payload": {"class": "sbus", "id": 12, "humidity": 410}}}]
    bridge._handle_payload(json.dumps(payload))
    assert coordinator.sbus_devices[12]["humidity"] == 410
    assert coordinator.sbus_devices[12]["temperature"] == 250


def test_ws_multiple_events_all_processed():
    """All events in the array must be processed even if the first one succeeds."""
    bridge, _hass, coordinator = _bridge()
    payload = [
        {"data": {"type": "device_state_changed", "details": "humidity",
                  "payload": {"class": "sbus", "id": 1, "humidity": 100}}},
        {"data": {"type": "device_state_changed", "details": "temperature",
                  "payload": {"class": "sbus", "id": 2, "temperature": 200}}},
        {"data": {"type": "device_state_changed", "details": "motion_detected",
                  "payload": {"class": "sbus", "id": 3, "motion_detected": True}}},
    ]
    bridge._handle_payload(json.dumps(payload))
    assert coordinator.sbus_devices[1]["humidity"] == 100
    assert coordinator.sbus_devices[2]["temperature"] == 200
    assert coordinator.sbus_devices[3]["motion_detected"] is True


def test_ws_fires_sinum_bus_event_on_update():
    bridge, hass, coordinator = _bridge()
    payload = [{"data": {"type": "device_state_changed", "details": "humidity",
                          "payload": {"class": "sbus", "id": 12, "humidity": 300}}}]
    bridge._handle_payload(json.dumps(payload))
    hass.bus.async_fire.assert_called_once()
    call_args = hass.bus.async_fire.call_args
    assert call_args[0][0] == "sinum_device_state_changed"
    event_data = call_args[0][1]
    assert event_data["id"] == 12
    assert event_data["class"] == "sbus"
    assert event_data["details"] == "humidity"


# ── Auth failure handling ─────────────────────────────────────────────────────

def test_ws_unauthorized_event_sets_auth_failed_flag():
    bridge, _hass, coordinator = _bridge()
    payload = [{"data": {"type": "unauthorized"}}]
    bridge._handle_payload(json.dumps(payload))
    assert bridge._auth_failed is True
    coordinator.async_set_updated_data.assert_not_called()


# ── _iter_events ──────────────────────────────────────────────────────────────

def test_iter_events_plain_list():
    events = list(_iter_events([{"a": 1}, {"b": 2}]))
    assert events == [{"a": 1}, {"b": 2}]


def test_iter_events_skips_non_dicts_in_list():
    events = list(_iter_events([{"a": 1}, "string", 42, None, {"b": 2}]))
    assert events == [{"a": 1}, {"b": 2}]


def test_iter_events_single_dict_fallback():
    events = list(_iter_events({"type": "x"}))
    assert events == [{"type": "x"}]


def test_iter_events_nested_events_key():
    payload = {"events": [{"a": 1}, {"b": 2}]}
    assert list(_iter_events(payload)) == [{"a": 1}, {"b": 2}]


def test_iter_events_nested_items_key():
    payload = {"items": [{"c": 3}]}
    assert list(_iter_events(payload)) == [{"c": 3}]


def test_iter_events_non_list_non_dict_returns_empty():
    assert list(_iter_events("string")) == []
    assert list(_iter_events(42)) == []
    assert list(_iter_events(None)) == []


# ── _normalize_ws_path ────────────────────────────────────────────────────────

def test_normalize_ws_path_none_returns_default():
    from custom_components.sinum.const import DEFAULT_WS_PATH
    assert _normalize_ws_path(None) == DEFAULT_WS_PATH


def test_normalize_ws_path_adds_leading_slash():
    assert _normalize_ws_path("api/v1/ws") == "/api/v1/ws"


def test_normalize_ws_path_keeps_valid_path():
    assert _normalize_ws_path("/api/v1/ws") == "/api/v1/ws"


def test_normalize_ws_path_rejects_full_url():
    from custom_components.sinum.const import DEFAULT_WS_PATH
    assert _normalize_ws_path("ws://10.0.0.1/api/v1/ws") == DEFAULT_WS_PATH


def test_normalize_ws_path_empty_returns_default():
    from custom_components.sinum.const import DEFAULT_WS_PATH
    assert _normalize_ws_path("") == DEFAULT_WS_PATH


# ── _patch_device ─────────────────────────────────────────────────────────────

def test_patch_device_with_details_only_patches_named_field():
    store: dict[int, dict] = {1: {"id": 1, "humidity": 100, "temperature": 200}}
    _patch_device(store, 1, "humidity", {"id": 1, "class": "sbus", "humidity": 999})
    assert store[1]["humidity"] == 999
    assert store[1]["temperature"] == 200


def test_patch_device_without_details_merges_all():
    store: dict[int, dict] = {}
    _patch_device(store, 5, None, {"id": 5, "class": "sbus", "a": 1, "b": 2})
    assert store[5]["a"] == 1
    assert store[5]["b"] == 2


def test_patch_device_creates_new_entry_for_unknown_id():
    store: dict[int, dict] = {}
    _patch_device(store, 99, "val", {"id": 99, "class": "sbus", "val": 42})
    assert store[99]["val"] == 42


# ── _device_class ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("cls,expected", [
    ("sbus", "sbus"),
    ("sbus_sensor", "sbus"),
    ("wtp", "wtp"),
    ("virtual", "virtual"),
    ("lora", "lora"),
    ("modbus", "modbus"),
    ("video", "video"),
    ("unknown_type", ""),
    ("", ""),
])
def test_device_class_mapping(cls: str, expected: str):
    assert _device_class(cls) == expected


# ── _ws_should_continue ───────────────────────────────────────────────────────

def test_ws_should_continue_text_not_reached():
    assert _ws_should_continue(aiohttp.WSMsgType.BINARY) is True


def test_ws_should_continue_closed_returns_false():
    assert _ws_should_continue(aiohttp.WSMsgType.CLOSED) is False


def test_ws_should_continue_closing_returns_false():
    assert _ws_should_continue(aiohttp.WSMsgType.CLOSING) is False


def test_ws_should_continue_error_raises():
    with pytest.raises(RuntimeError, match="error state"):
        _ws_should_continue(aiohttp.WSMsgType.ERROR)


# ── _filter_dicts / _find_nested_list ────────────────────────────────────────

def test_filter_dicts_keeps_only_dicts():
    result = list(_filter_dicts([1, "x", {"a": 1}, None, {"b": 2}]))
    assert result == [{"a": 1}, {"b": 2}]


def test_find_nested_list_events_key():
    assert _find_nested_list({"events": [1, 2]}) == [1, 2]


def test_find_nested_list_items_key():
    assert _find_nested_list({"items": [3, 4]}) == [3, 4]


def test_find_nested_list_missing_returns_none():
    assert _find_nested_list({"data": 1}) is None


# ── Async lifecycle ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ws_bridge_async_start_creates_task():
    bridge, hass, coordinator = _bridge()
    created_tasks: list = []

    def _track_task(coro, name=None):
        created_tasks.append(coro)
        coro.close()  # prevent "coroutine never awaited" GC warning
        return MagicMock()

    hass.async_create_background_task = _track_task
    result = await bridge.async_start()
    assert result is True
    assert len(created_tasks) == 1


@pytest.mark.asyncio
async def test_ws_bridge_async_stop_with_no_task_is_safe():
    bridge, _hass, _coordinator = _bridge()
    bridge._task = None
    await bridge.async_stop()
    assert bridge._task is None


@pytest.mark.asyncio
async def test_ws_bridge_async_stop_sets_stop_event():
    bridge, _hass, _coordinator = _bridge()
    bridge._stop_event.clear()

    cancelled_task = asyncio.create_task(asyncio.sleep(100))

    async def _noop_run():
        try:
            await asyncio.sleep(100)
        except asyncio.CancelledError:
            pass

    bridge._task = asyncio.create_task(_noop_run())
    await bridge.async_stop()
    assert bridge._stop_event.is_set()
    assert bridge._task is None
    cancelled_task.cancel()
    try:
        await cancelled_task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_ws_bridge_double_start_is_noop():
    bridge, hass, coordinator = _bridge()
    mock_task = MagicMock()
    mock_task.done.return_value = False
    bridge._task = mock_task
    hass.async_create_background_task = MagicMock()
    result = await bridge.async_start()
    assert result is True
    hass.async_create_background_task.assert_not_called()
