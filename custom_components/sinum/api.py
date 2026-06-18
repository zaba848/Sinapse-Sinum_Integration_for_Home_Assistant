from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from .const import (
    API_ALARM_COMMAND,
    API_ALARM_DEVICE,
    API_ALARM_DEVICES,
    API_ENERGY,
    API_FLOORS,
    API_INFO,
    API_LOGIN,
    API_LORA_DEVICE,
    API_LORA_DEVICES,
    API_LUA_INFO,
    API_PARENT_DEVICES,
    API_REFRESH,
    API_ROOMS,
    API_SBUS_DEVICE,
    API_SBUS_DEVICES,
    API_SCENE,
    API_SCENE_ACTIVATE,
    API_SCENES,
    API_SCHEDULES,
    API_VARIABLE,
    API_VARIABLES,
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

REQUEST_TIMEOUT = 30


class SinumAuthError(Exception):
    pass


class SinumConnectionError(Exception):
    pass


class SinumClient:
    """Async HTTP client for the Sinum EH-01 hub REST API.

    Authentication modes:
    - Static API token  (preferred — never expires, created in Sinum app)
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

    @property
    def base_url(self) -> str:
        if self._host.startswith("http"):
            return self._host
        return f"http://{self._host}"

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

    async def login(self) -> None:
        """Authenticate with username/password and obtain JWT + refresh token."""
        if self._api_token:
            return  # Static token — no login needed
        if not self._username or not self._password:
            raise SinumAuthError("No credentials provided")
        payload = {
            "username": self._username,
            "password": self._password,
            "os_info": "HomeAssistant",
            "device_info": "Sinapse",
            "uuid_device": "sinapse-ha-integration",
        }
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                resp = await self._session.post(self._url(API_LOGIN), json=payload, ssl=False)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise SinumConnectionError(f"Cannot connect to {self._host}: {err}") from err

        if resp.status == 401:
            raise SinumAuthError("Invalid credentials")
        if resp.status != 200:
            raise SinumConnectionError(f"Login failed with status {resp.status}")

        body = await resp.json()
        data = body.get("data", body)
        self._jwt = data[ATTR_SESSION]
        self._refresh_token = data.get(ATTR_REFRESH_TOKEN)
        _LOGGER.debug("Login successful for %s", self._host)

    async def _refresh_jwt(self) -> bool:
        """Try to renew JWT using the refresh token. Returns True on success."""
        if not self._refresh_token:
            return False
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                resp = await self._session.post(
                    self._url(API_REFRESH),
                    json={ATTR_REFRESH_TOKEN: self._refresh_token},
                    ssl=False,
                )
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False

        if resp.status != 200:
            return False

        body = await resp.json()
        data = body.get("data", body)
        if ATTR_SESSION in data:
            self._jwt = data[ATTR_SESSION]
            self._refresh_token = data.get(ATTR_REFRESH_TOKEN, self._refresh_token)
            _LOGGER.debug("JWT refreshed successfully for %s", self._host)
            return True
        return False

    async def test_connection(self) -> None:
        """Verify connection and auth by fetching hub info."""
        await self.get_hub_info()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self._api_token and not self._jwt:
            await self.login()

        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                resp = await self._session.request(
                    method, self._url(path), headers=self._headers(), ssl=False, **kwargs
                )
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise SinumConnectionError(f"Request failed: {err}") from err

        if resp.status == 401:
            if self._api_token:
                raise SinumAuthError("API token rejected by hub")
            _LOGGER.debug("Auth expired, refreshing")
            refreshed = await self._refresh_jwt()
            if not refreshed:
                self._jwt = None
                await self.login()
            async with asyncio.timeout(REQUEST_TIMEOUT):
                resp = await self._session.request(
                    method, self._url(path), headers=self._headers(), ssl=False, **kwargs
                )

        # 304 means no change (PATCH returned same data) — treat as success
        if resp.status == 304:
            return {}

        # 408 is hub-side bus timeout (firmware alpha behaviour) — raise as connection error
        # so coordinator logs a warning and retries on next poll instead of crashing
        if resp.status == 408:
            raise SinumConnectionError(f"Hub internal timeout for {path} (bus may be busy)")

        if resp.status == 422:
            try:
                body = await resp.json()
                errors = body.get("error", {}).get("errors", {})
                details = "; ".join(
                    f"{k}: {v.get('text', v)}" if isinstance(v, dict) else f"{k}: {v}"
                    for k, v in errors.items()
                )
            except Exception:
                details = f"status {resp.status}"
            raise SinumConnectionError(f"Validation error for {path}: {details}")

        if resp.status not in (200, 201, 204):
            raise SinumConnectionError(f"API error {resp.status} for {path}")

        if resp.status == 204 or resp.content_length == 0:
            return {}

        body = await resp.json()
        # Unwrap {"data": ...} envelope present on all Sinum API responses
        return body.get("data", body)

    # ------------------------------------------------------------------ hub info

    async def get_hub_info(self) -> dict[str, Any]:
        return await self._request("GET", API_INFO)

    # ------------------------------------------------------------------ rooms

    async def get_rooms(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_ROOMS)
        return result if isinstance(result, list) else []

    # ----------------------------------------------------------------- floors

    async def get_floors(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_FLOORS)
        return result if isinstance(result, list) else []

    # --------------------------------------------------------- parent devices

    async def get_parent_devices(self) -> list[dict[str, Any]]:
        """Return a flat list of all parent devices across all classes."""
        result = await self._request("GET", API_PARENT_DEVICES)
        if not isinstance(result, dict):
            return []
        flat: list[dict[str, Any]] = []
        for devices in result.values():
            if isinstance(devices, list):
                flat.extend(devices)
        return flat

    # --------------------------------------------------------- virtual devices

    async def get_virtual_devices(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_VIRTUAL_DEVICES)
        return result if isinstance(result, list) else []

    async def get_virtual_device(self, device_id: int) -> dict[str, Any]:
        return await self._request("GET", API_VIRTUAL_DEVICE.format(id=device_id))

    async def patch_virtual_device(self, device_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PATCH", API_VIRTUAL_DEVICE.format(id=device_id), json=payload)

    # ----------------------------------------------------------- WTP devices

    async def get_wtp_devices(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_WTP_DEVICES)
        return result if isinstance(result, list) else []

    async def get_wtp_device(self, device_id: int) -> dict[str, Any]:
        return await self._request("GET", API_WTP_DEVICE.format(id=device_id))

    async def patch_wtp_device(self, device_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PATCH", API_WTP_DEVICE.format(id=device_id), json=payload)

    # ----------------------------------------------------------- SBUS devices

    async def get_sbus_devices(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_SBUS_DEVICES)
        return result if isinstance(result, list) else []

    async def get_sbus_device(self, device_id: int) -> dict[str, Any]:
        return await self._request("GET", API_SBUS_DEVICE.format(id=device_id))

    async def patch_sbus_device(self, device_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PATCH", API_SBUS_DEVICE.format(id=device_id), json=payload)

    # --------------------------------------------------------------- scenes

    async def get_scenes(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_SCENES)
        return result if isinstance(result, list) else []

    async def run_scene(self, scene_id: int) -> None:
        await self._request("POST", API_SCENE_ACTIVATE.format(id=scene_id))

    # ------------------------------------------------------------ variables

    async def get_variables(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_VARIABLES)
        return result if isinstance(result, list) else []

    async def set_variable(self, variable_id: int, value: Any) -> dict[str, Any]:
        return await self._request(
            "PATCH", API_VARIABLE.format(id=variable_id), json={"value": value}
        )

    # ------------------------------------------------------------- schedules

    async def get_schedules(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_SCHEDULES)
        return result if isinstance(result, list) else []

    # --------------------------------------------------------------- alarms

    async def get_alarm_devices(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_ALARM_DEVICES)
        return result if isinstance(result, list) else []

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
        return result if isinstance(result, list) else []

    async def get_lora_device(self, device_id: int) -> dict[str, Any]:
        return await self._request("GET", API_LORA_DEVICE.format(id=device_id))

    async def patch_lora_device(self, device_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PATCH", API_LORA_DEVICE.format(id=device_id), json=payload)

    # ---------------------------------------------------------- notifications

    async def send_notification(self, title: str, message: str) -> None:
        payload = {"title": title, "message": message}
        await self._request("POST", "/api/v1/notifications", json=payload)

    # -------------------------------------------------------------- weather

    async def get_weather(self) -> dict[str, Any]:
        return await self._request("GET", API_WEATHER)

    # --------------------------------------------------------------- energy

    async def get_energy(self) -> dict[str, Any]:
        return await self._request("GET", API_ENERGY)

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
