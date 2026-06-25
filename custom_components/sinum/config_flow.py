from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar
from urllib.parse import urlsplit

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SinumAuthError, SinumClient, SinumConnectionError
from .const import (
    AUTH_MODE_PASSWORD,
    AUTH_MODE_TOKEN,
    CONF_API_TOKEN,
    CONF_AUTH_MODE,
    CONF_MQTT_CLIENT_ID,
    CONF_MQTT_ENABLED,
    CONF_MQTT_SCENE_ID,
    CONF_MQTT_TOPIC_PREFIX,
    DEFAULT_MQTT_CLIENT_ID,
    DEFAULT_MQTT_SCENE_ID,
    DEFAULT_MQTT_TOPIC_PREFIX,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

_PROBE_RETRIES = 2
_PROBE_RETRY_DELAY = 0.5
_REAUTH_MAX_FAILS = 5
_REAUTH_COOLDOWN_SEC = 300  # 5 minutes after 5 bad attempts
T = TypeVar("T")


def _reauth_store_key(entry_id: str) -> str:
    return f"sinum_reauth_{entry_id}"


def _reauth_cooldown_remaining(hass: Any, entry_id: str) -> float:
    """Return seconds remaining in cooldown, 0 if not blocked."""
    store: dict[str, Any] = hass.data.get(_reauth_store_key(entry_id), {})
    return max(0.0, store.get("blocked_until", 0.0) - time.monotonic())


def _reauth_record_failure(hass: Any, entry_id: str) -> None:
    key = _reauth_store_key(entry_id)
    store: dict[str, Any] = hass.data.get(key, {"fails": 0, "blocked_until": 0.0})
    store["fails"] = store["fails"] + 1
    if store["fails"] >= _REAUTH_MAX_FAILS:
        store["blocked_until"] = time.monotonic() + _REAUTH_COOLDOWN_SEC
        _LOGGER.warning("Sinum reauth blocked after %d failures for entry %s", store["fails"], entry_id)
    hass.data[key] = store


def _reauth_reset(hass: Any, entry_id: str) -> None:
    hass.data.pop(_reauth_store_key(entry_id), None)


def _normalize_host_input(value: str) -> str:
    """Normalize host input from GUI and reject malformed endpoint strings."""
    raw = value.strip()
    if not raw:
        raise ValueError("empty host")

    parsed = urlsplit(raw)
    if parsed.scheme:
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("unsupported scheme")
        if not parsed.netloc:
            raise ValueError("missing host")
        if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("path/query/fragment not allowed")
        host = parsed.netloc
    else:
        if any(ch in raw for ch in "/?#"):
            raise ValueError("path/query/fragment not allowed")
        host = raw

    host = host.strip().strip("/")
    if not host or " " in host:
        raise ValueError("invalid host")
    return host


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


class SinumConfigFlow(ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    VERSION = 1

    def __init__(self) -> None:
        self._host: str = ""
        self._auth_mode: str = AUTH_MODE_TOKEN
        self._reconfigure: bool = False

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self._host = _normalize_host_input(user_input[CONF_HOST])
            except ValueError:
                errors["base"] = "invalid_host"
            else:
                self._auth_mode = user_input[CONF_AUTH_MODE]
                if self._auth_mode == AUTH_MODE_TOKEN:
                    return await self.async_step_token()
                return await self.async_step_password()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_AUTH_SCHEMA,
            errors=errors,
            description_placeholders={
                "token_mode": AUTH_MODE_TOKEN,
                "password_mode": AUTH_MODE_PASSWORD,
            },
        )

    async def async_step_token(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_API_TOKEN].strip()
            hub_name, error = await self._hub_name_from_token(token)
            if error:
                errors["base"] = error
            else:
                return await self._create_entry(
                    {
                        CONF_HOST: self._host,
                        CONF_AUTH_MODE: AUTH_MODE_TOKEN,
                        CONF_API_TOKEN: token,
                        CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                    },
                    hub_name=hub_name,
                )

        return self.async_show_form(
            step_id="token",
            data_schema=STEP_TOKEN_SCHEMA,
            errors=errors,
            description_placeholders={"host": self._host},
        )

    async def async_step_password(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            hub_name, error = await self._hub_name_from_password(
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            if error:
                errors["base"] = error
            else:
                return await self._create_entry(
                    {
                        CONF_HOST: self._host,
                        CONF_AUTH_MODE: AUTH_MODE_PASSWORD,
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                    },
                    hub_name=hub_name,
                )

        return self.async_show_form(
            step_id="password",
            data_schema=STEP_PASSWORD_SCHEMA,
            errors=errors,
            description_placeholders={"host": self._host},
        )

    async def _create_entry(
        self, data: dict[str, Any], hub_name: str | None = None
    ) -> ConfigFlowResult:
        if self._reconfigure:
            entry = self._get_reconfigure_entry()
            return self.async_update_reload_and_abort(entry, data={**entry.data, **data})
        unique_id = f"sinum_{self._host.replace('.', '_').replace(':', '_')}"
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()
        display = hub_name or self._host
        return self.async_create_entry(title=f"Sinum ({display})", data=data)

    def _make_client(self, **kwargs: Any) -> SinumClient:
        session = async_get_clientsession(self.hass, verify_ssl=False)
        return SinumClient(self._host, session, **kwargs)

    async def _run_probe_with_retry(self, operation: Callable[[], Awaitable[T]]) -> T:
        last_error: Exception | None = None
        for attempt in range(1, _PROBE_RETRIES + 1):
            try:
                return await operation()
            except SinumAuthError:
                raise
            except SinumConnectionError as err:
                last_error = err
                if attempt == _PROBE_RETRIES:
                    raise
                await asyncio.sleep(_PROBE_RETRY_DELAY)
        raise SinumConnectionError(str(last_error) if last_error else "probe failed")

    @staticmethod
    def _map_auth_exception(exc: Exception) -> str:
        if isinstance(exc, SinumAuthError):
            return "invalid_auth"
        if isinstance(exc, SinumConnectionError):
            return "cannot_connect"
        _LOGGER.exception("Unexpected error connecting to Sinum")
        return "unknown"

    @staticmethod
    def _hub_name_from_info(hub_info: dict[str, Any]) -> str | None:
        return hub_info.get("name") or hub_info.get("hostname")

    async def _hub_name_from_token(self, token: str) -> tuple[str | None, str | None]:
        client = self._make_client(api_token=token)
        try:
            hub_info = await self._run_probe_with_retry(client.get_hub_info)
        except Exception as exc:
            return None, self._map_auth_exception(exc)
        return self._hub_name_from_info(hub_info), None

    async def _hub_name_from_password(
        self, username: str, password: str
    ) -> tuple[str | None, str | None]:
        client = self._make_client(username=username, password=password)
        try:
            await self._run_probe_with_retry(client.login)
        except Exception as exc:
            return None, self._map_auth_exception(exc)

        try:
            hub_info = await self._run_probe_with_retry(client.get_hub_info)
        except SinumConnectionError:
            # Fallback: login was accepted but /info may be temporarily busy.
            _LOGGER.warning(
                "Hub info unavailable after successful login, using host as fallback title"
            )
            return None, None
        except Exception as exc:
            return None, self._map_auth_exception(exc)
        return self._hub_name_from_info(hub_info), None

    def _reauth_client(self, auth_mode: str, user_input: dict[str, Any]) -> SinumClient:
        if auth_mode == AUTH_MODE_TOKEN:
            return self._make_client(api_token=user_input[CONF_API_TOKEN])
        return self._make_client(
            username=user_input[CONF_USERNAME],
            password=user_input[CONF_PASSWORD],
        )

    async def _test_connection_error(self, client: SinumClient) -> str | None:
        try:
            await client.test_connection()
        except Exception as exc:
            return self._map_auth_exception(exc)
        return None

    # ------------------------------------------------------------ reconfigure

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow changing host and credentials without removing the integration."""
        self._reconfigure = True
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self._host = _normalize_host_input(user_input[CONF_HOST])
            except ValueError:
                errors["base"] = "invalid_host"
            else:
                self._auth_mode = user_input[CONF_AUTH_MODE]
                if self._auth_mode == AUTH_MODE_TOKEN:
                    return await self.async_step_token()
                return await self.async_step_password()
        self._host = entry.data.get(CONF_HOST, "")
        self._auth_mode = entry.data.get(CONF_AUTH_MODE, AUTH_MODE_TOKEN)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=self._host): str,
                    vol.Required(CONF_AUTH_MODE, default=self._auth_mode): vol.In(
                        [AUTH_MODE_TOKEN, AUTH_MODE_PASSWORD]
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "token_mode": AUTH_MODE_TOKEN,
                "password_mode": AUTH_MODE_PASSWORD,
            },
        )

    # ----------------------------------------------------------------- reauth

    @staticmethod
    def async_get_options_flow(config_entry: Any) -> SinumOptionsFlow:
        return SinumOptionsFlow(config_entry)

    # ----------------------------------------------------------------- reauth

    async def async_step_reauth(self, _entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        auth_mode = entry.data.get(CONF_AUTH_MODE, AUTH_MODE_PASSWORD)
        schema = STEP_TOKEN_SCHEMA if auth_mode == AUTH_MODE_TOKEN else STEP_PASSWORD_SCHEMA

        remaining = _reauth_cooldown_remaining(self.hass, entry.entry_id)
        if remaining > 0:
            minutes = max(1, int(remaining // 60) + 1)
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=schema,
                errors={"base": "too_many_attempts"},
                description_placeholders={"minutes": str(minutes)},
            )

        if user_input is not None:
            self._host = entry.data[CONF_HOST]
            client = self._reauth_client(auth_mode, user_input)
            error = await self._test_connection_error(client)
            if error:
                _reauth_record_failure(self.hass, entry.entry_id)
                errors["base"] = error
            else:
                _reauth_reset(self.hass, entry.entry_id)
                return self.async_update_reload_and_abort(entry, data={**entry.data, **user_input})

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
        )


class SinumOptionsFlow(OptionsFlow):
    """Options flow: change scan interval and MQTT settings."""

    def __init__(self, config_entry: Any) -> None:
        self._entry = config_entry

    def _opt(self, key: str, default: object) -> object:
        return self._entry.options.get(key, self._entry.data.get(key, default))

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            if CONF_MQTT_TOPIC_PREFIX in user_input:
                user_input[CONF_MQTT_TOPIC_PREFIX] = _mqtt_topic_prefix(
                    user_input[CONF_MQTT_TOPIC_PREFIX]
                )
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=self._opt(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(int, vol.Range(min=10, max=300)),
                vol.Optional(
                    CONF_MQTT_ENABLED,
                    default=self._opt(CONF_MQTT_ENABLED, False),
                ): bool,
                vol.Optional(
                    CONF_MQTT_TOPIC_PREFIX,
                    default=self._opt(CONF_MQTT_TOPIC_PREFIX, DEFAULT_MQTT_TOPIC_PREFIX),
                ): _mqtt_topic_prefix,
                vol.Optional(
                    CONF_MQTT_SCENE_ID,
                    default=self._opt(CONF_MQTT_SCENE_ID, DEFAULT_MQTT_SCENE_ID),
                ): vol.All(int, vol.Range(min=1)),
                vol.Optional(
                    CONF_MQTT_CLIENT_ID,
                    default=self._opt(CONF_MQTT_CLIENT_ID, DEFAULT_MQTT_CLIENT_ID),
                ): vol.All(int, vol.Range(min=1)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)


def _mqtt_topic_prefix(value: str) -> str:
    """Validate and normalize MQTT topic prefix for one Sinum hub."""
    prefix = value.strip().strip("/")
    if not prefix:
        prefix = DEFAULT_MQTT_TOPIC_PREFIX
    if "#" in prefix or "+" in prefix:
        raise vol.Invalid("MQTT wildcards are not allowed in topic prefix")
    return prefix
