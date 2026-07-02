"""WebRTC session state manager extracted from SinumCoordinator."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .api import SinumClient

_LOGGER = logging.getLogger(__name__)


class WebRtcSessionManager:
    """Tracks active WebRTC sessions and dispatches ICE/SDP events to HA."""

    def __init__(self, client: SinumClient) -> None:
        self._client = client
        self._sessions: dict[str, tuple[int, Any]] = {}

    def register(self, session_id: str, device_id: int, send_message: Any) -> None:
        self._sessions[session_id] = (device_id, send_message)

    def dispatch_answer(self, session_id: str, answer_sdp: str) -> None:
        session = self._sessions.get(session_id)
        if session:
            from homeassistant.components.camera.webrtc import WebRTCAnswer

            session[1](WebRTCAnswer(answer=answer_sdp))

    def dispatch_candidate(self, session_id: str, candidate_dict: dict[str, Any]) -> None:
        session = self._sessions.get(session_id)
        if session:
            from homeassistant.components.camera.webrtc import WebRTCCandidate
            from webrtc_models import RTCIceCandidateInit

            candidate = RTCIceCandidateInit(
                candidate=candidate_dict.get("candidate", ""),
                sdp_mid=candidate_dict.get("sdp_mid") or None,
                sdp_m_line_index=candidate_dict.get("sdp_m_line_index"),
            )
            session[1](WebRTCCandidate(candidate=candidate))

    def dispatch_error(self, session_id: str, code: str, message: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session:
            from homeassistant.components.camera.webrtc import WebRTCError

            session[1](WebRTCError(code=code, message=message))

    def close(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    async def forward_candidate(self, session_id: str, candidate: Any) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        device_id, _ = session
        try:
            await self._client.post_video_candidate(device_id, session_id, candidate)
        except Exception as exc:
            _LOGGER.debug("Cannot forward ICE candidate to hub: %s", exc)
