"""Video/motion mixin for SinumWebSocketBridge."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .coordinator import SinumCoordinator

_LOGGER = logging.getLogger(__name__)


class _WebSocketVideoMixin:
    """Handles video stream and motion detection WebSocket events."""

    if TYPE_CHECKING:
        _coordinator: SinumCoordinator

    def _handle_video_stream_message(self, data: dict[str, Any]) -> None:
        payload = data.get("payload", {})
        inner = payload.get("data", {})
        session_id = inner.get("session_id", "")
        if not session_id:
            return
        self._dispatch_video_message(payload.get("type"), session_id, inner)

    def _dispatch_video_message(
        self, msg_type: str | None, session_id: str, inner: dict[str, Any]
    ) -> None:
        if msg_type == "answer":
            self._handle_video_answer(session_id, inner)
        elif msg_type == "candidate":
            self._handle_video_candidate(session_id, inner)
        elif msg_type in ("bye", "error"):
            self._handle_video_bye(session_id, inner, msg_type)

    def _handle_video_answer(self, session_id: str, inner: dict[str, Any]) -> None:
        sdp = inner.get("description", {}).get("sdp", "")
        if sdp:
            self._coordinator.dispatch_webrtc_answer(session_id, sdp)

    def _handle_video_candidate(self, session_id: str, inner: dict[str, Any]) -> None:
        candidate_dict = inner.get("candidate", {})
        if candidate_dict:
            self._coordinator.dispatch_webrtc_candidate(session_id, candidate_dict)

    def _handle_video_bye(
        self, session_id: str, inner: dict[str, Any], msg_type: str
    ) -> None:
        reason = inner.get("reason", msg_type)
        _LOGGER.debug("WebRTC %s session %s: %s", msg_type, session_id, reason)
        self._coordinator.dispatch_webrtc_error(session_id, msg_type, reason)

    def _handle_motion_detected(self, data: dict[str, Any]) -> None:
        """Handle motion detection event from camera WebSocket."""
        payload = data.get("payload", {})
        device_id = payload.get("device_id")
        timestamp = payload.get("timestamp")
        if not device_id:
            _LOGGER.debug("Motion event missing device_id: %s", payload)
            return
        _LOGGER.debug("Motion detected on device %s at %s", device_id, timestamp)
        self._coordinator.dispatch_motion_detected(device_id, payload)
