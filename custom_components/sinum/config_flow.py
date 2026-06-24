from __future__ import annotations

import logging
from typing import Any

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
    CONF_MQTT_ENABLED,
    CONF_MQTT_TOPIC_PREFIX,
    DEFAULT_MQTT_TOPIC_PREFIX,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

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
            self._host = user_input[CONF_HOST].strip()
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
            client = self._make_client(api_token=token)
            hub_name: str | None = None
            try:
                hub_info = await client.get_hub_info()
                hub_name = hub_info.get("name") or hub_info.get("hostname")
            except SinumAuthError:
                errors["base"] = "invalid_auth"
            except SinumConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error connecting to Sinum")
                errors["base"] = "unknown"
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
            client = self._make_client(
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
            )
            hub_name: str | None = None
            try:
                await client.login()
                hub_info = await client.get_hub_info()
                hub_name = hub_info.get("name") or hub_info.get("hostname")
            except SinumAuthError:
                errors["base"] = "invalid_auth"
            except SinumConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error connecting to Sinum")
                errors["base"] = "unknown"
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

    # ------------------------------------------------------------ reconfigure

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow changing host and credentials without removing the integration."""
        self._reconfigure = True
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            self._host = user_input[CONF_HOST].strip()
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

        if user_input is not None:
            self._host = entry.data[CONF_HOST]
            if auth_mode == AUTH_MODE_TOKEN:
                client = self._make_client(api_token=user_input[CONF_API_TOKEN])
            else:
                client = self._make_client(
                    username=user_input[CONF_USERNAME],
                    password=user_input[CONF_PASSWORD],
                )
            try:
                await client.test_connection()
            except SinumAuthError:
                errors["base"] = "invalid_auth"
            except SinumConnectionError:
                errors["base"] = "cannot_connect"
            else:
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

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        current_interval = self._entry.options.get(
            CONF_SCAN_INTERVAL,
            self._entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        current_mqtt = self._entry.options.get(
            CONF_MQTT_ENABLED,
            self._entry.data.get(CONF_MQTT_ENABLED, False),
        )
        current_mqtt_prefix = self._entry.options.get(
            CONF_MQTT_TOPIC_PREFIX,
            self._entry.data.get(CONF_MQTT_TOPIC_PREFIX, DEFAULT_MQTT_TOPIC_PREFIX),
        )

        if user_input is not None:
            if CONF_MQTT_TOPIC_PREFIX in user_input:
                user_input[CONF_MQTT_TOPIC_PREFIX] = _mqtt_topic_prefix(
                    user_input[CONF_MQTT_TOPIC_PREFIX]
                )
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Optional(CONF_SCAN_INTERVAL, default=current_interval): vol.All(
                    int, vol.Range(min=10, max=300)
                ),
                vol.Optional(CONF_MQTT_ENABLED, default=current_mqtt): bool,
                vol.Optional(
                    CONF_MQTT_TOPIC_PREFIX,
                    default=current_mqtt_prefix,
                ): _mqtt_topic_prefix,
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
