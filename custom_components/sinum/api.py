from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import aiohttp

from ._api_devices import DevicesMixin
from ._api_energy import EnergyMixin
from ._api_scene import SceneMixin
from .const import (
    API_LOGIN,
    API_REFRESH,
    ATTR_REFRESH_TOKEN,
    ATTR_SESSION,
)

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = 25


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


class SinumClient(DevicesMixin, SceneMixin, EnergyMixin):
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
