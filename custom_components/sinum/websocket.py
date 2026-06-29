"""WebSocket real-time transport for Sinapse.

The hub sends arrays of events in each WS frame. We consume each item,
apply device state updates for device_state_changed notifications, and push
coordinator data without waiting for the poll cycle.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

import aiohttp

from .const import DEFAULT_WS_PATH

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .api import SinumClient
    from .coordinator import SinumCoordinator

_LOGGER = logging.getLogger(__name__)
_RECONNECT_DELAY = 5


class SinumWebSocketBridge:
    """Bridges Sinum websocket events to the coordinator data store."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: SinumClient,
        coordinator: SinumCoordinator,
        ws_path: str | None = None,
    ) -> None:
        self._hass = hass
        self._client = client
        self._coordinator = coordinator
        self._ws_path = _normalize_ws_path(ws_path)
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._auth_failed = False

    async def async_start(self) -> bool:
        """Start websocket consumer task."""
        if self._task and not self._task.done():
            return True
        self._stop_event.clear()
        self._auth_failed = False
        self._task = self._hass.async_create_background_task(self._run(), name="sinum_ws_bridge")
        _LOGGER.info("Sinapse WebSocket bridge starting (%s)", self._ws_path)
        return True

    async def async_stop(self) -> None:
        """Stop websocket consumer task."""
        self._stop_event.set()
        task = self._task
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self._task = None
        _LOGGER.debug("Sinapse WebSocket bridge stopped")

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            await self._run_one_cycle()

    async def _run_one_cycle(self) -> None:
        try:
            await self._consume_loop()
        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.warning("WebSocket bridge error: %s", err)
        if not self._stop_event.is_set():
            await self._wait_reconnect()

    async def _wait_reconnect(self) -> None:
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._stop_event.wait(), timeout=_RECONNECT_DELAY)

    async def _consume_loop(self) -> None:
        await self._client.ensure_push_auth()
        ws_url = self._client.websocket_url_with_access_token(self._ws_path)
        async with self._client.session.ws_connect(ws_url, heartbeat=30, ssl=False) as ws:
            _LOGGER.info("Sinapse WebSocket bridge connected to %s", ws_url)
            await self._receive_messages(ws)

    async def _receive_messages(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        async for msg in ws:
            if self._stop_event.is_set():
                return
            if not self._dispatch_message(msg):
                return

    def _dispatch_message(self, msg: aiohttp.WSMessage) -> bool:
        """Process one WS message; return False if the loop should stop."""
        if msg.type == aiohttp.WSMsgType.TEXT:
            return self._handle_text_message(msg.data)
        return _ws_should_continue(msg.type)

    def _handle_text_message(self, data: str) -> bool:
        self._handle_payload(data)
        if self._auth_failed:
            raise PermissionError("WebSocket unauthorized")
        return True

    def _handle_payload(self, raw: str) -> None:
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            _LOGGER.debug("Ignoring invalid websocket payload: %s", raw)
            return

        results = [self._handle_event(ev) for ev in _iter_events(decoded)]
        if any(results):
            self._publish_coordinator_data()

    def _handle_event(self, event: dict[str, Any]) -> bool:
        data = event.get("data", event)
        if not isinstance(data, dict):
            return False
        return self._dispatch_event_type(data)

    def _dispatch_event_type(self, data: dict[str, Any]) -> bool:
        evt_type = data.get("type")
        if evt_type == "unauthorized":
            self._mark_auth_failed()
            return False
        if evt_type == "video_stream_message":
            self._handle_video_stream_message(data)
            return False
        if evt_type != "device_state_changed":
            return False
        return self._apply_device_state(data)

    def _handle_video_stream_message(self, data: dict[str, Any]) -> None:
        payload = data.get("payload", {})
        inner = payload.get("data", {})
        device_id = _as_int(inner.get("from"))
        if device_id is None:
            return
        msg_type = payload.get("type")
        if msg_type == "answer":
            self._handle_video_answer(device_id, inner)
        elif msg_type in ("bye", "error"):
            self._handle_video_bye(device_id, inner, msg_type)

    def _handle_video_answer(self, device_id: int, inner: dict[str, Any]) -> None:
        sdp = inner.get("description", {}).get("sdp", "")
        if sdp:
            self._coordinator.resolve_webrtc_answer(device_id, sdp)

    def _handle_video_bye(self, device_id: int, inner: dict[str, Any], msg_type: str) -> None:
        reason = inner.get("reason", msg_type)
        _LOGGER.debug("WebRTC %s for device %d: %s", msg_type, device_id, reason)
        self._coordinator.reject_webrtc_answer(device_id, reason)

    def _mark_auth_failed(self) -> None:
        self._auth_failed = True
        _LOGGER.warning(
            "Sinum websocket unauthorized on %s; verify WS auth mode/path",
            self._ws_path,
        )

    def _apply_device_state(self, data: dict[str, Any]) -> bool:
        payload = data.get("payload")
        if not isinstance(payload, dict):
            return False
        return self._apply_payload(payload, data.get("details"))

    def _apply_payload(self, payload: dict[str, Any], details: Any) -> bool:
        device_id = _as_int(payload.get("id"))
        store = self._store_for_class(payload.get("class") or payload.get("source"))
        if device_id is None or store is None:
            return False
        _patch_device(store, device_id, details, payload)
        self._fire_state_event(device_id, payload, details)
        return True

    def _fire_state_event(self, device_id: int, payload: dict[str, Any], details: Any) -> None:
        device_class = _device_class(payload.get("class") or payload.get("source"))
        self._hass.bus.async_fire(
            "sinum_device_state_changed",
            {"id": device_id, "class": device_class, "details": details, "payload": payload},
        )

    def _store_for_class(self, cls: Any) -> dict[int, dict[str, Any]] | None:
        stores: dict[str, dict[int, dict[str, Any]]] = {
            "virtual": self._coordinator.virtual_devices,
            "wtp": self._coordinator.wtp_devices,
            "sbus": self._coordinator.sbus_devices,
            "lora": self._coordinator.lora_devices,
            "modbus": self._coordinator.modbus_devices,
            "video": self._coordinator.video_devices,
        }
        return stores.get(_device_class(cls))

    def _publish_coordinator_data(self) -> None:
        data = self._coordinator.data if isinstance(self._coordinator.data, dict) else {}
        self._coordinator.async_set_updated_data(
            {
                **data,
                "virtual": self._coordinator.virtual_devices,
                "wtp": self._coordinator.wtp_devices,
                "sbus": self._coordinator.sbus_devices,
                "lora": self._coordinator.lora_devices,
                "modbus": self._coordinator.modbus_devices,
                "video": self._coordinator.video_devices,
            }
        )


def _patch_device(
    store: dict[int, dict[str, Any]],
    device_id: int,
    details: Any,
    payload: dict[str, Any],
) -> None:
    current = store.get(device_id, {"id": device_id})
    if isinstance(details, str) and details and details in payload:
        current[details] = payload[details]
    else:
        current.update(payload)
    store[device_id] = current


def _normalize_ws_path(path: str | None) -> str:
    raw = (path or DEFAULT_WS_PATH).strip()
    if not raw or _is_full_url(raw):
        return DEFAULT_WS_PATH
    return _ensure_leading_slash(raw)


def _ensure_leading_slash(raw: str) -> str:
    return raw if raw.startswith("/") else f"/{raw}"


def _is_full_url(raw: str) -> bool:
    return raw.startswith(("ws://", "wss://", "http://", "https://"))


def _iter_events(payload: Any) -> Iterator[dict[str, Any]]:
    if isinstance(payload, list):
        yield from _filter_dicts(payload)
        return
    if not isinstance(payload, dict):
        return
    nested = _find_nested_list(payload)
    if nested is not None:
        yield from _filter_dicts(nested)
        return
    yield payload


def _filter_dicts(lst: list[Any]) -> Iterator[dict[str, Any]]:
    for item in lst:
        if isinstance(item, dict):
            yield item


def _find_nested_list(payload: dict[str, Any]) -> list[Any] | None:
    for key in ("events", "items"):
        val = payload.get(key)
        if isinstance(val, list):
            return val
    return None


def _ws_should_continue(msg_type: aiohttp.WSMsgType) -> bool:
    if msg_type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
        return False
    if msg_type == aiohttp.WSMsgType.ERROR:
        raise RuntimeError("WS message stream entered error state")
    return True


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _device_class(value: Any) -> str:
    cls = str(value or "").lower()
    for prefix in ("virtual", "wtp", "sbus", "lora", "modbus", "video"):
        if cls.startswith(prefix):
            return prefix
    return ""
