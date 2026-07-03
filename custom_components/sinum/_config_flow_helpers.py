"""Pure helper functions and schemas for Sinum config flow."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit

import voluptuous as vol
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME

from .api import SinumAuthError, SinumConnectionError
from .const import (
    AUTH_MODE_PASSWORD,
    AUTH_MODE_TOKEN,
    CONF_API_TOKEN,
    CONF_AUTH_MODE,
    CONF_HOST,
    CONF_MQTT_CLIENT_ID,
    CONF_MQTT_ENABLED,
    CONF_MQTT_SCENE_ID,
    CONF_MQTT_TOPIC_PREFIX,
    CONF_WS_ENABLED,
    CONF_WS_PATH,
    DEFAULT_MQTT_CLIENT_ID,
    DEFAULT_MQTT_SCENE_ID,
    DEFAULT_MQTT_TOPIC_PREFIX,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_WS_PATH,
)

_LOGGER = logging.getLogger(__name__)

_PROBE_RETRIES = 2
_PROBE_RETRY_DELAY = 0.5
_REAUTH_MAX_FAILS = 5
_REAUTH_COOLDOWN_SEC = 300

_PROBE_MISSING: object = object()

# ── Config flow schemas ────────────────────────────────────────────────────────

STEP_AUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_AUTH_MODE, default=AUTH_MODE_TOKEN): vol.In(
            [AUTH_MODE_TOKEN, AUTH_MODE_PASSWORD]
        ),
    }
)

STEP_TOKEN_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_TOKEN): str,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            int, vol.Range(min=10, max=300)
        ),
    }
)

STEP_PASSWORD_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            int, vol.Range(min=10, max=300)
        ),
    }
)


# ── Probe helpers ──────────────────────────────────────────────────────────────


async def _try_probe(
    operation: Callable[[], Awaitable[Any]],
    attempt: int,
) -> Any:
    """Run one probe attempt; return result on success, _PROBE_MISSING on retry."""
    try:
        return await operation()
    except SinumAuthError:
        raise
    except SinumConnectionError:
        if attempt < _PROBE_RETRIES:
            await asyncio.sleep(_PROBE_RETRY_DELAY)
            return _PROBE_MISSING
        raise


# ── Reauth helpers ─────────────────────────────────────────────────────────────


def _reauth_schema(auth_mode: str) -> vol.Schema:
    return STEP_TOKEN_SCHEMA if auth_mode == AUTH_MODE_TOKEN else STEP_PASSWORD_SCHEMA


def _reauth_store_key(entry_id: str) -> str:
    return f"sinum_reauth_{entry_id}"


def _reauth_cooldown_remaining(hass: Any, entry_id: str) -> float:
    store: dict[str, Any] = hass.data.get(_reauth_store_key(entry_id), {})
    return max(0.0, store.get("blocked_until", 0.0) - time.monotonic())


def _reauth_record_failure(hass: Any, entry_id: str) -> None:
    key = _reauth_store_key(entry_id)
    store: dict[str, Any] = hass.data.get(key, {"fails": 0, "blocked_until": 0.0})
    store["fails"] = store["fails"] + 1
    if store["fails"] >= _REAUTH_MAX_FAILS:
        store["blocked_until"] = time.monotonic() + _REAUTH_COOLDOWN_SEC
        _LOGGER.warning(
            "Sinum reauth blocked after %d failures for entry %s", store["fails"], entry_id
        )
    hass.data[key] = store


def _reauth_reset(hass: Any, entry_id: str) -> None:
    hass.data.pop(_reauth_store_key(entry_id), None)


# ── Host input validation ──────────────────────────────────────────────────────


def _normalize_host_input(value: str) -> str:
    """Normalize host input from GUI and reject malformed endpoint strings."""
    raw = value.strip()
    if not raw:
        raise ValueError("empty host")
    parsed = urlsplit(raw)
    host = _extract_host_from_scheme(parsed, raw) if parsed.scheme else _extract_plain_host(raw)
    return _validate_extracted_host(host)


def _validate_extracted_host(host: str) -> str:
    host = host.strip().strip("/")
    if not host or " " in host:
        raise ValueError("invalid host")
    return host


def _extract_host_from_scheme(parsed: Any, raw: str) -> str:
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("unsupported scheme")
    if not parsed.netloc:
        raise ValueError("missing host")
    _reject_url_suffix(parsed)
    return parsed.netloc


def _reject_url_suffix(parsed: Any) -> None:
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("path/query/fragment not allowed")


def _extract_plain_host(raw: str) -> str:
    if any(ch in raw for ch in "/?#"):
        raise ValueError("path/query/fragment not allowed")
    return raw


# ── Options-flow validators ────────────────────────────────────────────────────


def _mqtt_topic_prefix(value: str) -> str:
    """Validate and normalize MQTT topic prefix for one Sinum hub."""
    prefix = value.strip().strip("/")
    if not prefix:
        prefix = DEFAULT_MQTT_TOPIC_PREFIX
    if "#" in prefix or "+" in prefix:
        raise vol.Invalid("MQTT wildcards are not allowed in topic prefix")
    return prefix


def _websocket_path(value: str) -> str:
    """Validate websocket endpoint path on the Sinum hub."""
    path = value.strip()
    if not path:
        return DEFAULT_WS_PATH
    if path.startswith(("ws://", "wss://", "http://", "https://")):
        raise vol.Invalid("Provide only endpoint path, e.g. /api/v1/events")
    return path if path.startswith("/") else f"/{path}"


def _normalize_options_input(user_input: dict[str, Any]) -> dict[str, Any]:
    data = dict(user_input)
    if CONF_MQTT_TOPIC_PREFIX in data:
        data[CONF_MQTT_TOPIC_PREFIX] = _mqtt_topic_prefix(data[CONF_MQTT_TOPIC_PREFIX])
    return data


def _options_schema(option_value: Callable[[str, object], object]) -> vol.Schema:
    """Build the options-flow schema with persisted options as defaults."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=option_value(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): vol.All(int, vol.Range(min=10, max=300)),
            vol.Optional(
                CONF_MQTT_ENABLED,
                default=option_value(CONF_MQTT_ENABLED, False),
            ): bool,
            vol.Optional(
                CONF_MQTT_TOPIC_PREFIX,
                default=option_value(CONF_MQTT_TOPIC_PREFIX, DEFAULT_MQTT_TOPIC_PREFIX),
            ): _mqtt_topic_prefix,
            vol.Optional(
                CONF_MQTT_SCENE_ID,
                default=option_value(CONF_MQTT_SCENE_ID, DEFAULT_MQTT_SCENE_ID),
            ): vol.All(int, vol.Range(min=1)),
            vol.Optional(
                CONF_MQTT_CLIENT_ID,
                default=option_value(CONF_MQTT_CLIENT_ID, DEFAULT_MQTT_CLIENT_ID),
            ): vol.All(int, vol.Range(min=1)),
            vol.Optional(
                CONF_WS_ENABLED,
                default=option_value(CONF_WS_ENABLED, True),
            ): bool,
            vol.Optional(
                CONF_WS_PATH,
                default=option_value(CONF_WS_PATH, DEFAULT_WS_PATH),
            ): _websocket_path,
        }
    )
