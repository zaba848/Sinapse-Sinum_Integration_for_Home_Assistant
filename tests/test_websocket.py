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
        import contextlib
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.sleep(100)

    bridge._task = asyncio.create_task(_noop_run())
    await bridge.async_stop()
    assert bridge._stop_event.is_set()
    assert bridge._task is None
    cancelled_task.cancel()
    import contextlib
    with contextlib.suppress(asyncio.CancelledError):
        await cancelled_task


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


# ── _dispatch_message msg type routing ───────────────────────────────────────

def test_dispatch_message_ping_continues():
    """PING is not CLOSED/ERROR — bridge should keep the loop running."""
    bridge, _hass, _coordinator = _bridge()
    msg = MagicMock()
    msg.type = aiohttp.WSMsgType.PING
    result = bridge._dispatch_message(msg)
    assert result is True


def test_dispatch_message_closed_stops_loop():
    bridge, _hass, _coordinator = _bridge()
    msg = MagicMock()
    msg.type = aiohttp.WSMsgType.CLOSED
    assert bridge._dispatch_message(msg) is False


def test_dispatch_message_closing_stops_loop():
    bridge, _hass, _coordinator = _bridge()
    msg = MagicMock()
    msg.type = aiohttp.WSMsgType.CLOSING
    assert bridge._dispatch_message(msg) is False


def test_dispatch_message_error_raises():
    bridge, _hass, _coordinator = _bridge()
    msg = MagicMock()
    msg.type = aiohttp.WSMsgType.ERROR
    with pytest.raises(RuntimeError):
        bridge._dispatch_message(msg)


def test_dispatch_message_text_processes_payload():
    bridge, _hass, coordinator = _bridge()
    msg = MagicMock()
    msg.type = aiohttp.WSMsgType.TEXT
    msg.data = json.dumps([{"data": {"type": "device_state_changed", "details": "humidity",
                                      "payload": {"class": "sbus", "id": 12, "humidity": 500}}}])
    result = bridge._dispatch_message(msg)
    assert result is True
    assert coordinator.sbus_devices[12]["humidity"] == 500


# ── source field as fallback for class ───────────────────────────────────────

def test_ws_source_field_used_when_class_absent():
    """Hub may send 'source' instead of 'class' in payload."""
    bridge, _hass, coordinator = _bridge()
    payload = [{"data": {"type": "device_state_changed", "details": "humidity",
                          "payload": {"source": "sbus", "id": 12, "humidity": 777}}}]
    bridge._handle_payload(json.dumps(payload))
    assert coordinator.sbus_devices[12]["humidity"] == 777


def test_ws_payload_without_class_and_source_ignored():
    bridge, _hass, coordinator = _bridge()
    payload = [{"data": {"type": "device_state_changed", "details": "x",
                          "payload": {"id": 5, "x": 1}}}]
    bridge._handle_payload(json.dumps(payload))
    coordinator.async_set_updated_data.assert_not_called()


# ── Auth failure raises PermissionError on next message ──────────────────────

def test_handle_text_message_raises_after_auth_failed():
    """Once auth_failed is set, the next text message must raise PermissionError."""
    bridge, _hass, _coordinator = _bridge()
    # First message: unauthorized → sets auth_failed
    bridge._handle_payload(json.dumps([{"data": {"type": "unauthorized"}}]))
    assert bridge._auth_failed is True
    # Second message: must raise so _consume_loop exits
    with pytest.raises(PermissionError):
        bridge._handle_text_message(json.dumps([{"data": {"type": "some_event"}}]))


# ── _run_one_cycle handles generic exceptions ─────────────────────────────────

@pytest.mark.asyncio
async def test_run_one_cycle_catches_generic_exception():
    """Generic exceptions must not crash the bridge — they are logged and reconnect waits."""
    bridge, _hass, _coordinator = _bridge()
    bridge._stop_event.set()  # prevent actual reconnect wait

    async def _fail():
        raise RuntimeError("connection dropped")

    bridge._consume_loop = _fail  # type: ignore[assignment]
    # Must not raise
    await bridge._run_one_cycle()


@pytest.mark.asyncio
async def test_run_one_cycle_reraises_cancelled_error():
    """CancelledError must propagate so the task can be properly cancelled."""
    bridge, _hass, _coordinator = _bridge()
    bridge._stop_event.set()

    async def _cancel():
        raise asyncio.CancelledError

    bridge._consume_loop = _cancel  # type: ignore[assignment]
    with pytest.raises(asyncio.CancelledError):
        await bridge._run_one_cycle()


@pytest.mark.asyncio
async def test_run_loop_exits_when_stop_event_set():
    """_run() must exit quickly when stop_event is already set."""
    bridge, _hass, _coordinator = _bridge()
    bridge._stop_event.set()
    call_count = 0

    async def _counted_cycle():
        nonlocal call_count
        call_count += 1
        bridge._stop_event.set()

    bridge._run_one_cycle = _counted_cycle  # type: ignore[assignment]
    bridge._stop_event.clear()
    bridge._stop_event.set()
    await bridge._run()
    assert call_count == 0


# ── _run executes cycle then stops ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_executes_one_cycle_then_stops():
    """_run() calls _run_one_cycle at least once before stop_event exits the loop."""
    bridge, _hass, _coordinator = _bridge()
    call_count = 0

    async def _counted_cycle():
        nonlocal call_count
        call_count += 1
        bridge._stop_event.set()

    bridge._run_one_cycle = _counted_cycle  # type: ignore[assignment]
    bridge._stop_event.clear()
    await bridge._run()
    assert call_count == 1


# ── _wait_reconnect ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_wait_reconnect_returns_immediately_when_stop_set():
    bridge, _hass, _coordinator = _bridge()
    bridge._stop_event.set()
    await bridge._wait_reconnect()  # must not hang


@pytest.mark.asyncio
async def test_wait_reconnect_times_out_when_not_stopped():
    bridge, _hass, _coordinator = _bridge()
    bridge._stop_event.clear()
    with patch("custom_components.sinum.websocket._RECONNECT_DELAY_MIN", 0.01):
        await bridge._wait_reconnect()  # timeout fires after 10 ms, suppressed


@pytest.mark.asyncio
async def test_run_one_cycle_calls_wait_reconnect_when_not_stopped():
    """After a generic exception, _wait_reconnect is called when stop_event is clear."""
    bridge, _hass, _coordinator = _bridge()
    bridge._stop_event.clear()
    reconnect_called = False

    async def _fail():
        raise RuntimeError("dropped")

    async def _mock_reconnect():
        nonlocal reconnect_called
        reconnect_called = True
        bridge._stop_event.set()

    bridge._consume_loop = _fail  # type: ignore[assignment]
    bridge._wait_reconnect = _mock_reconnect  # type: ignore[assignment]
    await bridge._run_one_cycle()
    assert reconnect_called


# ── _consume_loop ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_consume_loop_connects_and_receives():
    bridge, _hass, _coordinator = _bridge()
    bridge._client.ensure_push_auth = AsyncMock()
    bridge._client.websocket_url_with_access_token = MagicMock(return_value="ws://hub/ws")

    mock_ws = MagicMock()
    mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
    mock_ws.__aexit__ = AsyncMock(return_value=None)
    bridge._client.session.ws_connect = MagicMock(return_value=mock_ws)
    bridge._receive_messages = AsyncMock()

    await bridge._consume_loop()

    bridge._client.ensure_push_auth.assert_awaited_once()
    bridge._receive_messages.assert_awaited_once_with(mock_ws)


# ── _receive_messages ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_receive_messages_processes_text_message():
    bridge, _hass, coordinator = _bridge()
    msg = MagicMock()
    msg.type = aiohttp.WSMsgType.TEXT
    msg.data = json.dumps([{"data": {"type": "device_state_changed", "details": "humidity",
                                      "payload": {"class": "sbus", "id": 12, "humidity": 999}}}])

    async def _iter(_self=None):
        yield msg

    mock_ws = MagicMock()
    mock_ws.__aiter__ = _iter
    await bridge._receive_messages(mock_ws)
    assert coordinator.sbus_devices[12]["humidity"] == 999


@pytest.mark.asyncio
async def test_receive_messages_stops_on_closed():
    bridge, _hass, _coordinator = _bridge()
    msg = MagicMock()
    msg.type = aiohttp.WSMsgType.CLOSED

    async def _iter(_self=None):
        yield msg

    mock_ws = MagicMock()
    mock_ws.__aiter__ = _iter
    await bridge._receive_messages(mock_ws)  # must return without error


@pytest.mark.asyncio
async def test_receive_messages_exits_on_stop_event():
    bridge, _hass, _coordinator = _bridge()
    bridge._stop_event.set()
    msg = MagicMock()
    msg.type = aiohttp.WSMsgType.TEXT
    msg.data = json.dumps([])

    async def _iter(_self=None):
        yield msg

    mock_ws = MagicMock()
    mock_ws.__aiter__ = _iter
    await bridge._receive_messages(mock_ws)  # must return early


# ── _handle_event / _apply_device_state edge cases ───────────────────────────

def test_handle_event_non_dict_data_returns_false():
    bridge, _hass, _coordinator = _bridge()
    assert bridge._handle_event({"data": "not-a-dict"}) is False


def test_apply_device_state_non_dict_payload_returns_false():
    bridge, _hass, _coordinator = _bridge()
    assert bridge._apply_device_state({"payload": "not-a-dict"}) is False


# ── WebRTC / video stream message handling ───────────────────────────────────

def _video_event(msg_type: str, payload_data: dict) -> dict:
    return {
        "type": "video_stream_message",
        "payload": {
            "type": msg_type,
            "data": {"session_id": "sess-1", **payload_data},
        },
    }


def test_dispatch_event_type_video_stream_returns_false():
    """Lines 137-139: video_stream_message returns False (no coordinator update)."""
    bridge, _hass, coordinator = _bridge()
    result = bridge._dispatch_event_type(_video_event("answer", {"description": {"sdp": ""}}))
    assert result is False


def test_handle_video_stream_message_skips_when_no_session_id():
    """Line 148-149: early return when session_id missing."""
    bridge, _hass, coordinator = _bridge()
    data = {"type": "video_stream_message", "payload": {"type": "answer", "data": {}}}
    bridge._handle_video_stream_message(data)
    coordinator.dispatch_webrtc_answer.assert_not_called()


def test_handle_video_answer_dispatches_sdp():
    """Lines 162-165: answer message with SDP calls dispatch_webrtc_answer."""
    bridge, _hass, coordinator = _bridge()
    coordinator.dispatch_webrtc_answer = MagicMock()
    inner = {"session_id": "s1", "description": {"sdp": "v=0\r\n"}}
    bridge._handle_video_answer("s1", inner)
    coordinator.dispatch_webrtc_answer.assert_called_once_with("s1", "v=0\r\n")


def test_handle_video_answer_skips_when_sdp_empty():
    """Line 164: empty SDP does not call dispatch."""
    bridge, _hass, coordinator = _bridge()
    coordinator.dispatch_webrtc_answer = MagicMock()
    bridge._handle_video_answer("s1", {"description": {"sdp": ""}})
    coordinator.dispatch_webrtc_answer.assert_not_called()


def test_handle_video_candidate_dispatches():
    """Lines 167-170: candidate message calls dispatch_webrtc_candidate."""
    bridge, _hass, coordinator = _bridge()
    coordinator.dispatch_webrtc_candidate = MagicMock()
    candidate = {"candidate": "a=candidate:...", "sdpMid": "0"}
    bridge._handle_video_candidate("s1", {"candidate": candidate})
    coordinator.dispatch_webrtc_candidate.assert_called_once_with("s1", candidate)


def test_handle_video_candidate_skips_when_empty():
    """Line 169: empty candidate dict does not call dispatch."""
    bridge, _hass, coordinator = _bridge()
    coordinator.dispatch_webrtc_candidate = MagicMock()
    bridge._handle_video_candidate("s1", {"candidate": {}})
    coordinator.dispatch_webrtc_candidate.assert_not_called()


def test_handle_video_bye_dispatches_error():
    """Lines 172-175: bye message calls dispatch_webrtc_error with reason."""
    bridge, _hass, coordinator = _bridge()
    coordinator.dispatch_webrtc_error = MagicMock()
    bridge._handle_video_bye("s1", {"reason": "closed"}, "bye")
    coordinator.dispatch_webrtc_error.assert_called_once_with("s1", "bye", "closed")


def test_handle_video_bye_uses_msg_type_as_default_reason():
    """Line 173: reason defaults to msg_type when missing from inner."""
    bridge, _hass, coordinator = _bridge()
    coordinator.dispatch_webrtc_error = MagicMock()
    bridge._handle_video_bye("s1", {}, "error")
    coordinator.dispatch_webrtc_error.assert_called_once_with("s1", "error", "error")


def test_dispatch_video_message_answer():
    """Line 155-156: 'answer' routes to _handle_video_answer."""
    bridge, _hass, coordinator = _bridge()
    coordinator.dispatch_webrtc_answer = MagicMock()
    inner = {"session_id": "s1", "description": {"sdp": "v=0\r\n"}}
    bridge._dispatch_video_message("answer", "s1", inner)
    coordinator.dispatch_webrtc_answer.assert_called_once()


def test_dispatch_video_message_candidate():
    """Lines 157-158: 'candidate' routes to _handle_video_candidate."""
    bridge, _hass, coordinator = _bridge()
    coordinator.dispatch_webrtc_candidate = MagicMock()
    inner = {"candidate": {"candidate": "a=candidate:..."}}
    bridge._dispatch_video_message("candidate", "s1", inner)
    coordinator.dispatch_webrtc_candidate.assert_called_once()


def test_dispatch_video_message_error():
    """Lines 159-160: 'error' routes to _handle_video_bye."""
    bridge, _hass, coordinator = _bridge()
    coordinator.dispatch_webrtc_error = MagicMock()
    bridge._dispatch_video_message("error", "s1", {"reason": "timeout"})
    coordinator.dispatch_webrtc_error.assert_called_once_with("s1", "error", "timeout")


def test_full_video_stream_message_via_handle_payload():
    """Integration: full WS payload with video answer flows end-to-end."""
    bridge, _hass, coordinator = _bridge()
    coordinator.dispatch_webrtc_answer = MagicMock()
    payload = json.dumps([{
        "data": {
            "type": "video_stream_message",
            "payload": {
                "type": "answer",
                "data": {"session_id": "s42", "description": {"sdp": "v=0\r\n"}},
            },
        }
    }])
    bridge._handle_payload(payload)
    coordinator.dispatch_webrtc_answer.assert_called_once_with("s42", "v=0\r\n")
    coordinator.async_set_updated_data.assert_not_called()


# ─── Blind Position Feedback via WebSocket (P5.3) ───────────────────────────────


def test_apply_device_state_updates_sbus_blind_position():
    """P5.3: device_state_changed updates SBUS blind current_opening."""
    bridge, _hass, coordinator = _bridge()
    coordinator.sbus_devices[15] = {"id": 15, "type": "blind_controller", "current_opening": 50}
    
    payload = [{"data": {"type": "device_state_changed", "details": None,
                          "payload": {"class": "sbus", "id": 15, "current_opening": 75}}}]
    bridge._handle_payload(json.dumps(payload))
    
    assert coordinator.sbus_devices[15]["current_opening"] == 75
    coordinator.async_set_updated_data.assert_called_once()


def test_apply_device_state_updates_sbus_blind_position_and_tilt():
    """P5.3: device_state_changed updates SBUS blind position and tilt."""
    bridge, _hass, coordinator = _bridge()
    coordinator.sbus_devices[15] = {
        "id": 15,
        "type": "blind_controller",
        "current_opening": 50,
        "current_tilt": 20,
    }
    
    payload = [{"data": {"type": "device_state_changed", "details": None,
                          "payload": {"class": "sbus", "id": 15,
                                      "current_opening": 80, "current_tilt": 45,
                                      "target_opening": 80}}}]
    bridge._handle_payload(json.dumps(payload))
    
    assert coordinator.sbus_devices[15]["current_opening"] == 80
    assert coordinator.sbus_devices[15]["current_tilt"] == 45
    coordinator.async_set_updated_data.assert_called_once()


def test_apply_device_state_updates_wtp_blind_position():
    """P5.3: device_state_changed updates WTP blind current_opening."""
    bridge, _hass, coordinator = _bridge()
    coordinator.wtp_devices[25] = {"id": 25, "type": "blind_controller", "current_opening": 30}
    
    payload = [{"data": {"type": "device_state_changed", "details": None,
                          "payload": {"class": "wtp", "id": 25,
                                      "current_opening": 60, "target_opening": 60,
                                      "action_in_progress": False}}}]
    bridge._handle_payload(json.dumps(payload))
    
    assert coordinator.wtp_devices[25]["current_opening"] == 60
    coordinator.async_set_updated_data.assert_called_once()


def test_blind_position_updates_fire_state_event():
    """P5.3: Blind position updates fire sinum_device_state_changed event."""
    bridge, hass, coordinator = _bridge()
    coordinator.sbus_devices[15] = {"id": 15, "type": "blind_controller", "current_opening": 50}
    
    payload = [{"data": {"type": "device_state_changed", "details": None,
                          "payload": {"class": "sbus", "id": 15, "current_opening": 75}}}]
    bridge._handle_payload(json.dumps(payload))
    
    hass.bus.async_fire.assert_called_once()
    call_args = hass.bus.async_fire.call_args
    assert call_args[0][0] == "sinum_device_state_changed"
    event_data = call_args[0][1]
    assert event_data["id"] == 15
    assert event_data["class"] == "sbus"


def test_blind_position_updates_via_full_ws_payload():
    """P5.3 Integration: full WS payload with blind position update."""
    bridge, _hass, coordinator = _bridge()
    coordinator.sbus_devices[15] = {"id": 15, "type": "blind_controller", "current_opening": 50}
    
    payload = json.dumps([{
        "data": {
            "type": "device_state_changed",
            "details": None,
            "payload": {
                "class": "sbus",
                "id": 15,
                "current_opening": 85,
                "current_tilt": 30,
            }
        }
    }])
    
    bridge._handle_payload(payload)
    
    assert coordinator.sbus_devices[15]["current_opening"] == 85
    assert coordinator.sbus_devices[15]["current_tilt"] == 30
    coordinator.async_set_updated_data.assert_called()
