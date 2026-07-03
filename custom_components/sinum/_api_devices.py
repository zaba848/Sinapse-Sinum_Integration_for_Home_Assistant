"""Device CRUD mixin for SinumClient — hub, rooms, floors, and bus device endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._api_helpers import _list_result
from .const import (
    API_ALARM_COMMAND,
    API_ALARM_DEVICE,
    API_ALARM_DEVICES,
    API_FLOORS,
    API_INFO,
    API_LORA_DEVICE,
    API_LORA_DEVICES,
    API_MODBUS_DEVICE,
    API_MODBUS_DEVICES,
    API_NOTIFICATIONS,
    API_PARENT_DEVICES,
    API_ROOMS,
    API_SBUS_DEVICE,
    API_SBUS_DEVICES,
    API_SLINK_DEVICE,
    API_SLINK_DEVICES,
    API_VIDEO_DEVICE,
    API_VIDEO_DEVICES,
    API_VIDEO_SNAPSHOT,
    API_VIDEO_STREAM,
    API_VIRTUAL_DEVICE,
    API_VIRTUAL_DEVICES,
    API_WTP_DEVICE,
    API_WTP_DEVICES,
    TEMP_SCALE,
)

if TYPE_CHECKING:

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any: ...  # noqa: E704


class DevicesMixin:
    """Mixin adding device CRUD methods to SinumClient.

    Requires `self._request` — provided by SinumClient at runtime; declared
    here under TYPE_CHECKING so mypy resolves call sites without suppresses.
    """

    if TYPE_CHECKING:

        async def _request(self, method: str, path: str, **kwargs: Any) -> Any: ...  # noqa: E704

    # ------------------------------------------------------------------ hub info

    async def get_hub_info(self) -> dict[str, Any]:
        return await self._request("GET", API_INFO)

    # ------------------------------------------------------------------ rooms

    async def get_rooms(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_ROOMS)
        return _list_result(result, "rooms")

    # ----------------------------------------------------------------- floors

    async def get_floors(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_FLOORS)
        return _list_result(result, "floors")

    # --------------------------------------------------------- parent devices

    async def get_parent_devices(self) -> list[dict[str, Any]]:
        """Return a flat list of all parent devices across all classes."""
        result = await self._request("GET", API_PARENT_DEVICES)
        return _list_result(result, "parent_devices", "parents", "devices")

    # --------------------------------------------------------- virtual devices

    async def get_virtual_devices(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_VIRTUAL_DEVICES)
        return _list_result(result, "virtual", "devices")

    async def get_virtual_device(self, device_id: int) -> dict[str, Any]:
        return await self._request("GET", API_VIRTUAL_DEVICE.format(id=device_id))

    async def patch_virtual_device(self, device_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PATCH", API_VIRTUAL_DEVICE.format(id=device_id), json=payload)

    # ----------------------------------------------------------- WTP devices

    async def get_wtp_devices(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_WTP_DEVICES)
        return _list_result(result, "wtp", "devices")

    async def get_wtp_device(self, device_id: int) -> dict[str, Any]:
        return await self._request("GET", API_WTP_DEVICE.format(id=device_id))

    async def patch_wtp_device(self, device_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PATCH", API_WTP_DEVICE.format(id=device_id), json=payload)

    # ----------------------------------------------------------- SBUS devices

    async def get_sbus_devices(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_SBUS_DEVICES)
        return _list_result(result, "sbus", "devices")

    async def get_sbus_device(self, device_id: int) -> dict[str, Any]:
        return await self._request("GET", API_SBUS_DEVICE.format(id=device_id))

    async def patch_sbus_device(self, device_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PATCH", API_SBUS_DEVICE.format(id=device_id), json=payload)

    # ---------------------------------------------------------- SLINK devices

    async def get_slink_devices(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_SLINK_DEVICES)
        return _list_result(result, "slink", "devices")

    async def get_slink_device(self, device_id: int) -> dict[str, Any]:
        return await self._request("GET", API_SLINK_DEVICE.format(id=device_id))

    async def patch_slink_device(self, device_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PATCH", API_SLINK_DEVICE.format(id=device_id), json=payload)

    # --------------------------------------------------------------- alarms

    async def get_alarm_devices(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_ALARM_DEVICES)
        return _list_result(result, "alarm_system", "alarm_devices", "devices")

    async def get_alarm_device(self, device_id: int) -> dict[str, Any]:
        return await self._request("GET", API_ALARM_DEVICE.format(id=device_id))

    async def patch_alarm_device(self, device_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PATCH", API_ALARM_DEVICE.format(id=device_id), json=payload)

    async def command_alarm_device(
        self, device_id: int, command: str, payload: dict[str, Any]
    ) -> None:
        await self._request(
            "POST",
            API_ALARM_COMMAND.format(id=device_id, command=command),
            json=payload,
        )

    # ------------------------------------------------------------ LoRa devices

    async def get_lora_devices(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_LORA_DEVICES)
        return _list_result(result, "lora", "devices")

    async def get_lora_device(self, device_id: int) -> dict[str, Any]:
        return await self._request("GET", API_LORA_DEVICE.format(id=device_id))

    async def patch_lora_device(self, device_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PATCH", API_LORA_DEVICE.format(id=device_id), json=payload)

    # ---------------------------------------------------------- Modbus devices

    async def get_modbus_devices(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_MODBUS_DEVICES)
        return _list_result(result, "modbus", "devices")

    async def get_modbus_device(self, device_id: int) -> dict[str, Any]:
        return await self._request("GET", API_MODBUS_DEVICE.format(id=device_id))

    # --------------------------------------------------------------- video

    async def get_video_devices(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_VIDEO_DEVICES)
        return _list_result(result, "video", "devices")

    async def get_video_device(self, device_id: int) -> dict[str, Any]:
        return await self._request("GET", API_VIDEO_DEVICE.format(id=device_id))

    async def post_video_stream_offer(
        self, device_id: int, offer_sdp: str, session_id: str
    ) -> None:
        """POST a WebRTC SDP offer to the hub for the given camera device."""
        payload = {
            "type": "offer",
            "data": {
                "session_id": session_id,
                "from": "ha-client",
                "to": str(device_id),
                "description": {
                    "ice_servers": [],  # hub uses go2rtc internally; no external STUN needed
                    "sdp": offer_sdp,
                },
            },
        }
        await self._request("POST", API_VIDEO_STREAM.format(id=device_id), json=payload)

    async def post_video_candidate(self, device_id: int, session_id: str, candidate: Any) -> None:
        """Forward a browser ICE candidate to the hub."""
        payload = {
            "type": "candidate",
            "data": {
                "session_id": session_id,
                "from": "ha-client",
                "to": str(device_id),
                "candidate": {
                    "candidate": candidate.candidate,
                    "sdp_m_line_index": candidate.sdp_m_line_index
                    if candidate.sdp_m_line_index is not None
                    else 0,
                    "sdp_mid": candidate.sdp_mid or "",
                },
            },
        }
        await self._request("POST", API_VIDEO_STREAM.format(id=device_id), json=payload)

    async def get_video_snapshot(self, device_id: int) -> bytes | None:
        """Return raw JPEG bytes from hub snapshot proxy, or None if unavailable."""
        import base64

        result = await self._request("GET", API_VIDEO_SNAPSHOT.format(id=device_id))
        payload = (result or {}).get("payload")
        if not payload:
            return None
        try:
            return base64.b64decode(payload)
        except Exception:
            return None

    # ---------------------------------------------------------- notifications

    async def send_notification(self, title: str, message: str) -> None:
        payload = {"title": title, "message": message}
        await self._request("POST", API_NOTIFICATIONS, json=payload)

    # -------------------------------------------------- temperature encoding

    @staticmethod
    def decode_temperature(raw: int) -> float:
        return raw / TEMP_SCALE

    @staticmethod
    def encode_temperature(celsius: float) -> int:
        return round(celsius * TEMP_SCALE)
