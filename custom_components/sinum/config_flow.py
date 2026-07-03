from __future__ import annotations

import logging
from typing import Any, TypeVar, cast

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ._config_flow_helpers import (  # noqa: F401
    _PROBE_MISSING,
    _PROBE_RETRIES,
    _PROBE_RETRY_DELAY,
    _REAUTH_COOLDOWN_SEC,
    _REAUTH_MAX_FAILS,
    STEP_AUTH_SCHEMA,
    STEP_PASSWORD_SCHEMA,
    STEP_TOKEN_SCHEMA,
    _extract_host_from_scheme,
    _extract_plain_host,
    _mqtt_topic_prefix,
    _normalize_host_input,
    _reauth_cooldown_remaining,
    _reauth_record_failure,
    _reauth_reset,
    _reauth_schema,
    _reauth_store_key,
    _reject_url_suffix,
    _try_probe,
    _validate_extracted_host,
    _websocket_path,
)
from .api import SinumAuthError, SinumClient, SinumConnectionError
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
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_WS_ENABLED,
    CONF_WS_PATH,
    DEFAULT_MQTT_CLIENT_ID,
    DEFAULT_MQTT_SCENE_ID,
    DEFAULT_MQTT_TOPIC_PREFIX,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_WS_PATH,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


class SinumConfigFlow(ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    VERSION = 1

    def __init__(self) -> None:
        self._host: str = ""
        self._auth_mode: str = AUTH_MODE_TOKEN
        self._reconfigure: bool = False

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            next_step = await self._process_host_auth_input(user_input, errors)
            if next_step is not None:
                return next_step

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_AUTH_SCHEMA,
            errors=errors,
            description_placeholders={
                "token_mode": AUTH_MODE_TOKEN,
                "password_mode": AUTH_MODE_PASSWORD,
            },
        )

    async def _process_host_auth_input(
        self, user_input: dict[str, Any], errors: dict[str, str]
    ) -> ConfigFlowResult | None:
        try:
            self._host = _normalize_host_input(user_input[CONF_HOST])
        except ValueError:
            errors["base"] = "invalid_host"
            return None
        self._auth_mode = user_input[CONF_AUTH_MODE]
        if self._auth_mode == AUTH_MODE_TOKEN:
            return await self.async_step_token()
        return await self.async_step_password()

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

    async def _run_probe_with_retry(self, operation: Any) -> Any:
        for attempt in range(1, _PROBE_RETRIES + 1):
            result = await _try_probe(operation, attempt)
            if result is not _PROBE_MISSING:
                return cast(T, result)
        raise SinumConnectionError("probe failed after retries")

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
            next_step = await self._process_host_auth_input(user_input, errors)
            if next_step is not None:
                return next_step
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

    async def async_step_reauth(self, _entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        auth_mode = entry.data.get(CONF_AUTH_MODE, AUTH_MODE_PASSWORD)
        schema = _reauth_schema(auth_mode)

        cooldown = _reauth_cooldown_remaining(self.hass, entry.entry_id)
        if cooldown > 0:
            return self._reauth_cooldown_form(schema, cooldown)

        if user_input is not None:
            next_step = await self._process_reauth_input(entry, auth_mode, user_input, errors)
            if next_step is not None:
                return next_step

        return self.async_show_form(step_id="reauth_confirm", data_schema=schema, errors=errors)

    def _reauth_cooldown_form(self, schema: Any, remaining: float) -> ConfigFlowResult:
        minutes = max(1, int(remaining // 60) + 1)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors={"base": "too_many_attempts"},
            description_placeholders={"minutes": str(minutes)},
        )

    async def _process_reauth_input(
        self,
        entry: Any,
        auth_mode: str,
        user_input: dict[str, Any],
        errors: dict[str, str],
    ) -> ConfigFlowResult | None:
        self._host = entry.data[CONF_HOST]
        client = self._reauth_client(auth_mode, user_input)
        error = await self._test_connection_error(client)
        if error:
            _reauth_record_failure(self.hass, entry.entry_id)
            errors["base"] = error
            return None
        _reauth_reset(self.hass, entry.entry_id)
        return self.async_update_reload_and_abort(entry, data={**entry.data, **user_input})


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
                vol.Optional(
                    CONF_WS_ENABLED,
                    default=self._opt(CONF_WS_ENABLED, True),
                ): bool,
                vol.Optional(
                    CONF_WS_PATH,
                    default=self._opt(CONF_WS_PATH, DEFAULT_WS_PATH),
                ): _websocket_path,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
