from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import aiohttp

from .const import (
    API_ALARM_COMMAND,
    API_ALARM_DEVICE,
    API_ALARM_DEVICES,
    API_AUTOMATION,
    API_AUTOMATION_LOGS,
    API_AUTOMATION_LUA,
    API_AUTOMATION_LUA_EXTENSIONS,
    API_AUTOMATION_SCHEMA,
    API_AUTOMATIONS,
    API_ENERGY,
    API_ENERGY_CENTER_ASSOCIATIONS,
    API_ENERGY_CENTER_CONSUMPTION,
    API_ENERGY_CENTER_FLOW_MONITOR,
    API_ENERGY_CENTER_PRICES,
    API_ENERGY_CENTER_PRICES_SETTINGS,
    API_ENERGY_CENTER_PRICES_SOURCES,
    API_ENERGY_CENTER_PRODUCTION,
    API_ENERGY_CENTER_STORAGE,
    API_FLOORS,
    API_INFO,
    API_LOGIN,
    API_LORA_DEVICE,
    API_LORA_DEVICES,
    API_LUA_INFO,
    API_MODBUS_DEVICE,
    API_MODBUS_DEVICES,
    API_NOTIFICATIONS,
    API_PARENT_DEVICES,
    API_REFRESH,
    API_ROOMS,
    API_SBUS_DEVICE,
    API_SBUS_DEVICES,
    API_SCENE,
    API_SCENE_ACTIVATE,
    API_SCENE_LOGS,
    API_SCENE_LUA,
    API_SCENE_LUA_EXTENSIONS,
    API_SCENE_SCHEMA,
    API_SCENES,
    API_SCHEDULE,
    API_SCHEDULES,
    API_VARIABLE,
    API_VARIABLES,
    API_VIDEO_DEVICE,
    API_VIDEO_DEVICES,
    API_VIDEO_SNAPSHOT,
    API_VIDEO_STREAM,
    API_VIRTUAL_DEVICE,
    API_VIRTUAL_DEVICES,
    API_WEATHER,
    API_WTP_DEVICE,
    API_WTP_DEVICES,
    ATTR_REFRESH_TOKEN,
    ATTR_SESSION,
    TEMP_SCALE,
)

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = 25


def _dict_list(items: Any) -> list[dict[str, Any]]:
    """Return only dictionary items from a list-like API collection."""
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _extract_from_value(value: Any) -> list[dict[str, Any]] | None:
    if isinstance(value, list):
        return _dict_list(value)
    if isinstance(value, dict):
        nested = _list_result(value)
        return nested or None
    return None


def _extract_by_keys(result: dict[str, Any], keys: tuple[str, ...]) -> list[dict[str, Any]] | None:
    for key in keys:
        extracted = _extract_from_value(result.get(key))
        if extracted is not None:
            return extracted
    return None


def _flatten_values(result: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for value in result.values():
        _append_value_to_flat_list(out, value)
    return out


def _append_value_to_flat_list(out: list[dict[str, Any]], value: Any) -> None:
    if isinstance(value, list):
        out.extend(_dict_list(value))
    elif isinstance(value, dict) and "id" in value:
        out.append(value)


def _partition_energy_results(
    keys: tuple[str, ...], results: list[Any]
) -> tuple[dict[str, Any], list[str]]:
    available: dict[str, Any] = {}
    missing: list[str] = []
    for key, result in zip(keys, results):
        _classify_energy_result(key, result, available, missing)
    return available, missing


def _classify_energy_result(
    key: str, result: Any, available: dict[str, Any], missing: list[str]
) -> None:
    if result is not None:
        available[key] = result
    else:
        missing.append(key)


def _list_result_from_dict(
    result: dict[str, Any], preferred_keys: tuple[str, ...]
) -> list[dict[str, Any]]:
    extracted = _extract_by_keys(result, (*preferred_keys, "items", "devices", "results", "data"))
    if extracted is not None:
        return extracted
    if "id" in result:
        return [result]
    return _flatten_values(result)


def _list_result(result: Any, *preferred_keys: str) -> list[dict[str, Any]]:
    """Normalize Sinum list responses across firmware variants.

    Most documented endpoints return a bare list after the {"data": ...} envelope
    is unwrapped. Some firmware builds return maps keyed by id/bus, or wrap the
    list once more in keys such as "items" or "devices".
    """
    if isinstance(result, list):
        return _dict_list(result)
    if not isinstance(result, dict):
        return []
    return _list_result_from_dict(result, preferred_keys)


class SinumAuthError(Exception):
    pass


class SinumConnectionError(Exception):
    pass


class SinumNotSupportedError(Exception):
    """Raised when the hub firmware does not support a given endpoint (HTTP 404)."""


async def _read_json(resp: aiohttp.ClientResponse, path: str) -> dict[str, Any]:
    """Read response body and parse JSON; handle empty/non-JSON responses gracefully."""
    try:
        raw = await resp.read()
    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
        raise SinumConnectionError(f"Failed to read response body for {path}: {err}") from err
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError) as err:
        raise SinumConnectionError(
            f"Non-JSON response from {path} (status {resp.status}): {raw[:80]!r}"
        ) from err


class SinumClient:
    """Async HTTP client for the Sinum EH-01 hub REST API.

    Authentication modes:
    - Static API token  (preferred — never expires, created in the Sinum web UI)
    - Username + password  (fallback — JWT renewed automatically via refresh token)

    All responses are wrapped in {"data": ...} — _request() unwraps automatically.
    Authorization always sent with "Bearer" prefix (required for write operations).
    """

    def __init__(
        self,
        host: str,
        session: aiohttp.ClientSession,
        *,
        api_token: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self._host = host.rstrip("/")
        self._session = session
        # Static token mode
        self._api_token: str | None = api_token
        # JWT mode (username + password)
        self._username = username
        self._password = password
        self._jwt: str | None = None
        self._refresh_token: str | None = None
        # Limit concurrent requests — hub embedded firmware can't handle parallel load
        self._sem = asyncio.Semaphore(2)

    @property
    def base_url(self) -> str:
        if self._host.startswith("http"):
            return self._host
        return f"http://{self._host}"

    @property
    def session(self) -> aiohttp.ClientSession:
        """Return aiohttp session used by the REST/WebSocket client."""
        return self._session

    def websocket_url(self, path: str) -> str:
        """Build WS/WSS URL from configured hub URL and endpoint path."""
        parsed = urlsplit(self.base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        ws_path = path if path.startswith("/") else f"/{path}"
        return f"{scheme}://{parsed.netloc}{ws_path}"

    def websocket_url_with_access_token(self, path: str) -> str:
        """Build WS URL with Sinum-compatible access_token query auth."""
        ws_url = self.websocket_url(path)
        token = self._auth_token()
        if not token:
            return ws_url

        parsed = urlsplit(ws_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query["access_token"] = token
        return urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
        )

    async def ensure_push_auth(self) -> None:
        """Ensure websocket auth token is present before connecting."""
        if self._api_token or self._jwt:
            return
        await self.login()

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _auth_token(self) -> str | None:
        return self._api_token or self._jwt

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        token = self._auth_token()
        if token:
            # Always use Bearer prefix — required for write operations
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _require_password_credentials(self) -> None:
        if self._username and self._password:
            return
        raise SinumAuthError("No credentials provided")

    def _login_payload(self) -> dict[str, str]:
        return {
            "username": self._username or "",
            "password": self._password or "",
            "os_info": "HomeAssistant",
            "device_info": "Sinapse",
            "uuid_device": "sinapse-ha-integration",
        }

    async def _post_with_timeout(
        self, path: str, payload: dict[str, Any]
    ) -> aiohttp.ClientResponse:
        async with asyncio.timeout(REQUEST_TIMEOUT):
            return await self._session.post(self._url(path), json=payload, ssl=False)

    @staticmethod
    def _unwrap_data(body: Any) -> dict[str, Any]:
        if not isinstance(body, dict):
            return {}
        data = body.get("data", body)
        return data if isinstance(data, dict) else {}

    def _store_auth_tokens(self, data: dict[str, Any], *, allow_refresh_fallback: bool) -> bool:
        session = data.get(ATTR_SESSION)
        if session is None:
            return False
        self._jwt = str(session)
        if allow_refresh_fallback:
            self._refresh_token = data.get(ATTR_REFRESH_TOKEN, self._refresh_token)
        else:
            self._refresh_token = data.get(ATTR_REFRESH_TOKEN)
        return True

    @staticmethod
    def _validate_login_status(status: int) -> None:
        if status == 401:
            raise SinumAuthError("Invalid credentials")
        if status != 200:
            raise SinumConnectionError(f"Login failed with status {status}")

    async def _refresh_response_ok(self) -> aiohttp.ClientResponse | None:
        try:
            resp = await self._post_with_timeout(
                API_REFRESH,
                {ATTR_REFRESH_TOKEN: self._refresh_token},
            )
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return None
        if resp.status != 200:
            return None
        return resp

    async def _read_refresh_payload(self, resp: aiohttp.ClientResponse) -> dict[str, Any] | None:
        try:
            body = await _read_json(resp, "token-refresh")
        except SinumConnectionError:
            return None
        return self._unwrap_data(body)

    def _log_refresh_result(self, refreshed: bool) -> None:
        if refreshed:
            _LOGGER.debug("JWT refreshed successfully for %s", self._host)

    async def login(self) -> None:
        """Authenticate with username/password and obtain JWT + refresh token."""
        if self._api_token:
            return  # Static token — no login needed
        self._require_password_credentials()
        try:
            resp = await self._post_with_timeout(API_LOGIN, self._login_payload())
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise SinumConnectionError(f"Cannot connect to {self._host}: {err}") from err

        self._validate_login_status(resp.status)

        body = await _read_json(resp, "login")
        self._store_auth_tokens(self._unwrap_data(body), allow_refresh_fallback=False)
        _LOGGER.debug("Login successful for %s", self._host)

    async def _refresh_jwt(self) -> bool:
        """Try to renew JWT using the refresh token. Returns True on success."""
        if not self._refresh_token:
            return False
        resp = await self._refresh_response_ok()
        if resp is None:
            return False

        data = await self._read_refresh_payload(resp)
        if data is None:
            return False

        refreshed = self._store_auth_tokens(data, allow_refresh_fallback=True)
        self._log_refresh_result(refreshed)
        return refreshed

    async def test_connection(self) -> None:
        """Verify connection and auth by fetching hub info."""
        await self.get_hub_info()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        async with self._sem:
            return await self._request_inner(method, path, **kwargs)

    async def _do_request(self, method: str, path: str, **kwargs: Any) -> aiohttp.ClientResponse:
        """Execute a single HTTP request; raises SinumConnectionError on transport failure."""
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                return await self._session.request(
                    method, self._url(path), headers=self._headers(), ssl=False, **kwargs
                )
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise SinumConnectionError(f"Request failed: {err}") from err

    async def _handle_401(self, method: str, path: str, **kwargs: Any) -> aiohttp.ClientResponse:
        """Re-authenticate and retry after a 401 response."""
        if self._api_token:
            raise SinumAuthError("API token rejected by hub")
        _LOGGER.debug("Auth expired, refreshing")
        if not await self._refresh_jwt():
            self._jwt = None
            await self.login()
        return await self._do_request(method, path, **kwargs)

    async def _handle_408(self, method: str, path: str, **kwargs: Any) -> aiohttp.ClientResponse:
        """Retry once after a 408 bus-busy response."""
        _LOGGER.debug("Bus busy (408) on %s %s, retrying in 1 s", method, path)
        await asyncio.sleep(1)
        return await self._do_request(method, path, **kwargs)

    async def _raise_for_422(self, resp: aiohttp.ClientResponse, path: str) -> None:
        """Parse validation error details and raise SinumConnectionError."""
        try:
            body = await _read_json(resp, path)
            errors = body.get("error", {}).get("errors", {})
            details = "; ".join(
                f"{k}: {v.get('text', v)}" if isinstance(v, dict) else f"{k}: {v}"
                for k, v in errors.items()
            )
        except Exception:
            details = f"status {resp.status}"
        raise SinumConnectionError(f"Validation error for {path}: {details}")

    async def _ensure_authenticated(self) -> None:
        if self._api_token or self._jwt:
            return
        await self.login()

    async def _retry_if_401(
        self,
        resp: aiohttp.ClientResponse,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> aiohttp.ClientResponse:
        if resp.status != 401:
            return resp
        return await self._handle_401(method, path, **kwargs)

    @staticmethod
    def _payload_for_304(resp: aiohttp.ClientResponse) -> dict[str, Any] | None:
        if resp.status == 304:
            return {}
        return None

    async def _retry_if_408(
        self,
        resp: aiohttp.ClientResponse,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> aiohttp.ClientResponse:
        if resp.status != 408:
            return resp
        return await self._handle_408(method, path, **kwargs)

    @staticmethod
    def _raise_if_408(resp: aiohttp.ClientResponse, path: str) -> None:
        if resp.status != 408:
            return
        raise SinumConnectionError(f"Hub internal timeout for {path} (bus may be busy)")

    async def _raise_if_422(self, resp: aiohttp.ClientResponse, path: str) -> None:
        if resp.status != 422:
            return
        await self._raise_for_422(resp, path)

    @staticmethod
    def _raise_if_unexpected_status(resp: aiohttp.ClientResponse, path: str) -> None:
        if resp.status in (200, 201, 204):
            return
        if resp.status == 404:
            raise SinumNotSupportedError(f"Endpoint not found on this hub: {path}")
        raise SinumConnectionError(f"API error {resp.status} for {path}")

    async def _unwrap_response_body(self, resp: aiohttp.ClientResponse, path: str) -> Any:
        body = await _read_json(resp, path)
        return body.get("data", body) if isinstance(body, dict) else body

    async def _request_inner(self, method: str, path: str, **kwargs: Any) -> Any:
        await self._ensure_authenticated()

        resp = await self._do_request(method, path, **kwargs)
        resp = await self._retry_if_401(resp, method, path, **kwargs)

        payload_304 = self._payload_for_304(resp)
        if payload_304 is not None:
            return payload_304

        resp = await self._retry_if_408(resp, method, path, **kwargs)
        self._raise_if_408(resp, path)
        await self._raise_if_422(resp, path)
        self._raise_if_unexpected_status(resp, path)

        return await self._unwrap_response_body(resp, path)

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

    # --------------------------------------------------------------- scenes

    async def get_scenes(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_SCENES)
        return _list_result(result, "scenes")

    async def get_scene(self, scene_id: int) -> dict[str, Any]:
        result = await self._request("GET", API_SCENE.format(id=scene_id))
        return result if isinstance(result, dict) else {}

    async def get_scene_lua(self, scene_id: int) -> dict[str, Any]:
        result = await self._request("GET", API_SCENE_LUA.format(id=scene_id))
        return result if isinstance(result, dict) else {}

    async def get_scene_lua_extensions(self, scene_id: int) -> list[dict[str, Any]]:
        result = await self._request("GET", API_SCENE_LUA_EXTENSIONS.format(id=scene_id))
        return _list_result(result, "lua_extensions", "extensions")

    async def get_scene_schema(self, scene_id: int) -> dict[str, Any]:
        result = await self._request("GET", API_SCENE_SCHEMA.format(id=scene_id))
        return result if isinstance(result, dict) else {}

    async def get_scene_logs(self, scene_id: int) -> list[dict[str, Any]]:
        result = await self._request("GET", API_SCENE_LOGS.format(id=scene_id))
        return _list_result(result, "logs")

    async def run_scene(self, scene_id: int) -> None:
        await self._request("POST", API_SCENE_ACTIVATE.format(id=scene_id))

    async def create_scene(self, name: str, lua: str) -> int:
        """Create a code-type scene and return its ID."""
        result = await self._request(
            "POST", API_SCENES, json={"name": name, "type": "code", "lua": lua}
        )
        if isinstance(result, dict) and result.get("id"):
            return int(result["id"])
        raise SinumConnectionError(f"Scene creation failed: {result}")

    async def patch_scene_lua(self, scene_id: int, lua: str) -> None:
        """Replace the Lua code of an existing scene."""
        await self._request("PATCH", API_SCENE.format(id=scene_id), json={"lua": lua})

    async def delete_scene(self, scene_id: int) -> None:
        """Delete a scene by ID."""
        await self._request("DELETE", API_SCENE.format(id=scene_id))

    async def find_scene_by_name(self, name: str) -> int | None:
        """Return the ID of the first scene matching *name*, or None."""
        scenes = await self.get_scenes()
        for s in scenes:
            if s.get("name") == name:
                return int(s["id"])
        return None

    async def get_or_create_scene(self, name: str) -> int:
        """Return ID of a named scene, creating it if it doesn't exist."""
        existing = await self.find_scene_by_name(name)
        if existing is not None:
            return existing
        return await self.create_scene(name, "-- HA RGB placeholder")

    # ------------------------------------------------------------ automations

    async def get_automations(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_AUTOMATIONS)
        return _list_result(result, "automations")

    async def get_automation(self, automation_id: int) -> dict[str, Any]:
        result = await self._request("GET", API_AUTOMATION.format(id=automation_id))
        return result if isinstance(result, dict) else {}

    async def get_automation_lua(self, automation_id: int) -> dict[str, Any]:
        result = await self._request("GET", API_AUTOMATION_LUA.format(id=automation_id))
        return result if isinstance(result, dict) else {}

    async def get_automation_lua_extensions(self, automation_id: int) -> list[dict[str, Any]]:
        result = await self._request("GET", API_AUTOMATION_LUA_EXTENSIONS.format(id=automation_id))
        return _list_result(result, "lua_extensions", "extensions")

    async def get_automation_schema(self, automation_id: int) -> dict[str, Any]:
        result = await self._request("GET", API_AUTOMATION_SCHEMA.format(id=automation_id))
        return result if isinstance(result, dict) else {}

    async def get_automation_logs(self, automation_id: int) -> list[dict[str, Any]]:
        result = await self._request("GET", API_AUTOMATION_LOGS.format(id=automation_id))
        return _list_result(result, "logs")

    # ------------------------------------------------------------ variables

    async def get_variables(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_VARIABLES)
        return _list_result(result, "variables")

    async def set_variable(self, variable_id: int, value: Any) -> dict[str, Any]:
        return await self._request(
            "PATCH", API_VARIABLE.format(id=variable_id), json={"value": value}
        )

    # ------------------------------------------------------------- schedules

    async def get_schedules(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_SCHEDULES)
        return _list_result(result, "schedules")

    async def get_schedule(self, schedule_id: int) -> dict[str, Any]:
        result = await self._request("GET", API_SCHEDULE.format(id=schedule_id))
        return result if isinstance(result, dict) else {}

    async def patch_schedule(self, schedule_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        result = await self._request("PATCH", API_SCHEDULE.format(id=schedule_id), json=payload)
        return result if isinstance(result, dict) else {}

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

    async def post_video_stream_offer(self, device_id: int, offer_sdp: str, session_id: str) -> None:
        """POST a WebRTC SDP offer to the hub for the given camera device."""
        payload = {
            "type": "offer",
            "data": {
                "session_id": session_id,
                "from": "ha-client",
                "to": str(device_id),
                "description": {
                    "ice_servers": [{"urls": "stun:stun.l.google.com:19302"}],
                    "sdp": offer_sdp,
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

    # -------------------------------------------------------------- weather

    async def get_weather(self) -> dict[str, Any]:
        return await self._request("GET", API_WEATHER)

    # --------------------------------------------------------------- energy

    async def get_energy(self) -> dict[str, Any]:
        return await self._request("GET", API_ENERGY)

    async def get_energy_center_associations(self) -> dict[str, Any]:
        result = await self._request("GET", API_ENERGY_CENTER_ASSOCIATIONS)
        return result if isinstance(result, dict) else {}

    async def get_energy_center_flow_monitor(self) -> dict[str, Any]:
        result = await self._request("GET", API_ENERGY_CENTER_FLOW_MONITOR)
        return result if isinstance(result, dict) else {}

    async def get_energy_center_prices(self) -> dict[str, Any]:
        result = await self._request("GET", API_ENERGY_CENTER_PRICES)
        return result if isinstance(result, dict) else {}

    async def get_energy_center_prices_settings(self) -> dict[str, Any]:
        result = await self._request("GET", API_ENERGY_CENTER_PRICES_SETTINGS)
        return result if isinstance(result, dict) else {}

    async def get_energy_center_prices_sources(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_ENERGY_CENTER_PRICES_SOURCES)
        return _list_result(result, "sources")

    async def get_energy_center_storage(self) -> dict[str, Any]:
        result = await self._request("GET", API_ENERGY_CENTER_STORAGE)
        return result if isinstance(result, dict) else {}

    async def get_energy_center_consumption(self) -> dict[str, Any]:
        result = await self._request("GET", API_ENERGY_CENTER_CONSUMPTION)
        return result if isinstance(result, dict) else {}

    async def get_energy_center_production(self) -> dict[str, Any]:
        result = await self._request("GET", API_ENERGY_CENTER_PRODUCTION)
        return result if isinstance(result, dict) else {}

    @staticmethod
    def _energy_center_keys() -> tuple[str, ...]:
        return (
            "associations",
            "flow_monitor",
            "prices",
            "prices_settings",
            "prices_sources",
            "storage",
            "consumption",
            "production",
        )

    def _energy_center_getters(self) -> tuple[Any, ...]:
        return (
            self.get_energy_center_associations,
            self.get_energy_center_flow_monitor,
            self.get_energy_center_prices,
            self.get_energy_center_prices_settings,
            self.get_energy_center_prices_sources,
            self.get_energy_center_storage,
            self.get_energy_center_consumption,
            self.get_energy_center_production,
        )

    async def _safe_get_energy_center_value(self, getter: Any) -> Any:
        try:
            return await getter()
        except Exception:
            return None

    @staticmethod
    def _build_energy_center_summary(keys: tuple[str, ...], results: list[Any]) -> dict[str, Any]:
        available, missing = _partition_energy_results(keys, results)
        if not available:
            raise SinumConnectionError("Energy Center endpoints unavailable")
        return {
            **available,
            "available_endpoints": list(available.keys()),
            "missing_endpoints": missing,
        }

    async def get_energy_center_summary(self) -> dict[str, Any]:
        keys = self._energy_center_keys()
        getters = self._energy_center_getters()
        results = await asyncio.gather(
            *(self._safe_get_energy_center_value(getter) for getter in getters)
        )
        return self._build_energy_center_summary(keys, list(results))

    # ----------------------------------------- Lua HTTP server (optional)
    # Only available when sinapse_api.lua is installed on the hub.
    # Provides Wi-Fi signal and SSID — not exposed by the regular REST API.

    async def get_lua_hub_info(self) -> dict[str, Any]:
        return await self._request("GET", API_LUA_INFO)

    # -------------------------------------------------- temperature encoding

    @staticmethod
    def decode_temperature(raw: int) -> float:
        return raw / TEMP_SCALE

    @staticmethod
    def encode_temperature(celsius: float) -> int:
        return round(celsius * TEMP_SCALE)
