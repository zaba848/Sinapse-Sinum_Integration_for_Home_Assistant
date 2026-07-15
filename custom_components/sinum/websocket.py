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
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import aiohttp

from ._bus_registry import BUS_REGISTRY, bus_store
from ._websocket_helpers import (  # noqa: F401
    _as_int,
    _device_class,
    _ensure_leading_slash,
    _filter_dicts,
    _find_nested_list,
    _is_full_url,
    _iter_events,
    _normalize_ws_path,
    _patch_device,
    _ws_should_continue,
)
from ._websocket_video import _WebSocketVideoMixin

if TYPE_CHECKING:  # pragma: no cover
    from homeassistant.core import HomeAssistant

    from .api import SinumClient
    from .coordinator import SinumCoordinator

_LOGGER = logging.getLogger(__name__)
_RECONNECT_DELAY_MIN = 5
_RECONNECT_DELAY_MAX = 60
_SECRET_QUERY_KEYS = frozenset({"access_token"})


def _redact_ws_url(url: str) -> str:
    """Redact query-string secrets before writing websocket URLs to logs."""
    parsed = urlsplit(url)
    if not parsed.query:
        return url
    query = [
        (key, "<redacted>" if key in _SECRET_QUERY_KEYS else value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(query, safe="<>"), parsed.fragment)
    )


class SinumWebSocketBridge(_WebSocketVideoMixin):
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
        self._reconnect_attempt = 0
        # Lifetime counters (unlike _reconnect_attempt, never reset) surfaced
        # via diagnostics.py.
        self.connect_count = 0
        self.reconnect_count = 0

    async def async_start(self) -> bool:
        """Start websocket consumer task."""
        if self._task and not self._task.done():
            return True
        self._stop_event.clear()
        self._auth_failed = False
        self._reconnect_attempt = 0
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
            self._reconnect_attempt = 0  # Reset on success
            self.connect_count += 1
        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.warning("WebSocket bridge error: %s", err)
            self._reconnect_attempt += 1
            self.reconnect_count += 1
        if not self._stop_event.is_set():
            await self._wait_reconnect()

    async def _wait_reconnect(self) -> None:
        delay = min(_RECONNECT_DELAY_MIN * (2**self._reconnect_attempt), _RECONNECT_DELAY_MAX)
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay)

    async def _consume_loop(self) -> None:
        await self._client.ensure_push_auth()
        ws_url = self._client.websocket_url_with_access_token(self._ws_path)
        async with self._client.session.ws_connect(ws_url, heartbeat=30, ssl=False) as ws:
            _LOGGER.info("Sinapse WebSocket bridge connected to %s", _redact_ws_url(ws_url))
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

    def _handle_special_event(self, evt_type: str | None, data: dict[str, Any]) -> bool | None:
        """Handle special (non-state) event types. Returns bool or None if unhandled."""
        if evt_type == "unauthorized":
            self._mark_auth_failed()
            return False
        if evt_type == "video_stream_message":
            self._handle_video_stream_message(data)
            return False
        if evt_type == "motion_detected":
            self._handle_motion_detected(data)
            return False
        return None

    def _dispatch_event_type(self, data: dict[str, Any]) -> bool:
        evt_type = data.get("type")
        special = self._handle_special_event(evt_type, data)
        if special is not None:
            return special
        if evt_type != "device_state_changed":
            _LOGGER.debug("Unhandled Sinum WS event type: %s", evt_type)
            return False
        return self._apply_device_state(data)

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
        return bus_store(self._coordinator, _device_class(cls))

    def _publish_coordinator_data(self) -> None:
        data = self._coordinator.data if isinstance(self._coordinator.data, dict) else {}
        bus_data = {spec.name: getattr(self._coordinator, spec.store_attr) for spec in BUS_REGISTRY}
        self._coordinator.async_set_updated_data({**data, **bus_data})
