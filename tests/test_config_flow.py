"""Tests for Sinum config flow."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sinum.api import SinumAuthError, SinumConnectionError
from custom_components.sinum.const import (
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


@pytest.fixture
def mock_aiohttp_session():
    with patch(
        "custom_components.sinum.config_flow.async_get_clientsession",
        return_value=MagicMock(),
    ):
        yield


class TestConfigFlowToken:
    @pytest.mark.asyncio
    async def test_token_flow_success(self, hass, mock_aiohttp_session):
        with patch(
            "custom_components.sinum.config_flow.SinumClient"
        ) as MockClient:
            client = MagicMock()
            client.get_hub_info = AsyncMock(return_value={"name": "tablica-wtp"})
            MockClient.return_value = client

            from custom_components.sinum.config_flow import SinumConfigFlow

            flow = SinumConfigFlow()
            flow.hass = hass
            flow.context = {}

            result = await flow.async_step_user(
                {"host": "192.168.1.100", "auth_mode": AUTH_MODE_TOKEN}
            )
            assert result["type"] == "form"
            assert result["step_id"] == "token"

            result2 = await flow.async_step_token(
                {CONF_API_TOKEN: "mytoken", "scan_interval": 30}
            )
            assert result2["type"] == "create_entry"
            assert result2["data"][CONF_API_TOKEN] == "mytoken"
            assert result2["data"][CONF_AUTH_MODE] == AUTH_MODE_TOKEN
            assert result2["title"] == "Sinum (tablica-wtp)"

    @pytest.mark.asyncio
    async def test_token_flow_invalid_auth(self, hass, mock_aiohttp_session):
        with patch("custom_components.sinum.config_flow.SinumClient") as MockClient:
            client = MagicMock()
            client.get_hub_info = AsyncMock(side_effect=SinumAuthError("bad"))
            MockClient.return_value = client

            from custom_components.sinum.config_flow import SinumConfigFlow

            flow = SinumConfigFlow()
            flow.hass = hass
            flow._host = "192.168.1.100"
            flow._auth_mode = AUTH_MODE_TOKEN

            result = await flow.async_step_token(
                {CONF_API_TOKEN: "bad-token", "scan_interval": 30}
            )
            assert result["type"] == "form"
            assert result["errors"]["base"] == "invalid_auth"

    @pytest.mark.asyncio
    async def test_token_flow_cannot_connect(self, hass, mock_aiohttp_session):
        with patch("custom_components.sinum.config_flow.SinumClient") as MockClient:
            client = MagicMock()
            client.get_hub_info = AsyncMock(
                side_effect=SinumConnectionError("timeout")
            )
            MockClient.return_value = client

            from custom_components.sinum.config_flow import SinumConfigFlow

            flow = SinumConfigFlow()
            flow.hass = hass
            flow._host = "192.168.1.100"
            flow._auth_mode = AUTH_MODE_TOKEN

            result = await flow.async_step_token(
                {CONF_API_TOKEN: "tok", "scan_interval": 30}
            )
            assert result["errors"]["base"] == "cannot_connect"


class TestConfigFlowPassword:
    @pytest.mark.asyncio
    async def test_password_flow_success(self, hass, mock_aiohttp_session):
        with patch("custom_components.sinum.config_flow.SinumClient") as MockClient:
            client = MagicMock()
            client.login = AsyncMock(return_value=None)
            client.get_hub_info = AsyncMock(return_value={"name": "tablica-sbus"})
            MockClient.return_value = client

            from custom_components.sinum.config_flow import SinumConfigFlow

            flow = SinumConfigFlow()
            flow.hass = hass
            flow.context = {}
            flow._host = "192.168.1.100"

            result = await flow.async_step_password(
                {"username": "admin", "password": "secret", "scan_interval": 60}
            )
            assert result["type"] == "create_entry"
            assert result["data"]["username"] == "admin"
            assert result["data"][CONF_AUTH_MODE] == AUTH_MODE_PASSWORD
            assert result["title"] == "Sinum (tablica-sbus)"


class TestOptionsFlow:
    @pytest.mark.asyncio
    async def test_options_flow_returns_form(self, hass):
        from custom_components.sinum.config_flow import SinumOptionsFlow

        entry = MagicMock()
        entry.data = {"scan_interval": 30, CONF_MQTT_ENABLED: False}
        entry.options = {}

        flow = SinumOptionsFlow(entry)
        flow.hass = hass

        result = await flow.async_step_init(None)
        assert result["type"] == "form"
        assert result["step_id"] == "init"

    @pytest.mark.asyncio
    async def test_options_flow_prefers_saved_options_for_defaults(self, hass):
        from custom_components.sinum.config_flow import SinumOptionsFlow

        entry = MagicMock()
        entry.data = {"scan_interval": 30, CONF_MQTT_ENABLED: False}
        entry.options = {"scan_interval": 45, CONF_MQTT_ENABLED: True}

        flow = SinumOptionsFlow(entry)
        flow.hass = hass

        result = await flow.async_step_init(None)

        defaults = result["data_schema"]({})
        assert defaults["scan_interval"] == 45
        assert defaults[CONF_MQTT_ENABLED] is True
        assert defaults[CONF_MQTT_TOPIC_PREFIX] == DEFAULT_MQTT_TOPIC_PREFIX

    @pytest.mark.asyncio
    async def test_options_flow_saves_values(self, hass):
        from custom_components.sinum.config_flow import SinumOptionsFlow

        entry = MagicMock()
        entry.data = {"scan_interval": 30, CONF_MQTT_ENABLED: False}
        entry.options = {}

        flow = SinumOptionsFlow(entry)
        flow.hass = hass

        result = await flow.async_step_init(
            {
                "scan_interval": 60,
                CONF_MQTT_ENABLED: True,
                CONF_MQTT_TOPIC_PREFIX: "/sinum/tablica-wtp/",
            }
        )
        assert result["type"] == "create_entry"
        assert result["data"]["scan_interval"] == 60
        assert result["data"][CONF_MQTT_ENABLED] is True
        assert result["data"][CONF_MQTT_TOPIC_PREFIX] == "sinum/tablica-wtp"

    @pytest.mark.asyncio
    async def test_options_flow_rejects_mqtt_wildcard_prefix(self, hass):
        from custom_components.sinum.config_flow import SinumOptionsFlow

        entry = MagicMock()
        entry.data = {"scan_interval": 30, CONF_MQTT_ENABLED: False}
        entry.options = {}

        flow = SinumOptionsFlow(entry)
        flow.hass = hass

        result = await flow.async_step_init(None)
        schema = result["data_schema"]
        with pytest.raises(Exception):
            schema(
                {
                    "scan_interval": 60,
                    CONF_MQTT_ENABLED: True,
                    CONF_MQTT_TOPIC_PREFIX: "sinum/+",
                }
            )

    def test_mqtt_topic_prefix_empty_value_falls_back_to_default(self):
        from custom_components.sinum.config_flow import _mqtt_topic_prefix

        assert _mqtt_topic_prefix(" / ") == DEFAULT_MQTT_TOPIC_PREFIX


class TestReauthFlow:
    @pytest.mark.asyncio
    async def test_reauth_flow_shows_form(self, hass, mock_aiohttp_session):
        """Lines 177, 182-186: async_step_reauth → async_step_reauth_confirm with None shows form."""
        from custom_components.sinum.config_flow import SinumConfigFlow

        flow = SinumConfigFlow()
        flow.hass = hass
        flow.context = {}

        mock_entry = MagicMock()
        mock_entry.data = {
            "host": "192.168.1.100",
            CONF_AUTH_MODE: AUTH_MODE_TOKEN,
            CONF_API_TOKEN: "old_token",
        }
        flow._get_reauth_entry = MagicMock(return_value=mock_entry)

        # async_step_reauth delegates to async_step_reauth_confirm with no input
        result = await flow.async_step_reauth({})
        assert result["type"] == "form"
        assert result["step_id"] == "reauth_confirm"

    @pytest.mark.asyncio
    async def test_reauth_flow_success(self, hass, mock_aiohttp_session):
        """Lines 187-203: success path aborts with reauth_successful."""
        with patch("custom_components.sinum.config_flow.SinumClient") as MockClient:
            client = MagicMock()
            client.test_connection = AsyncMock(return_value=None)
            MockClient.return_value = client

            from custom_components.sinum.config_flow import SinumConfigFlow

            flow = SinumConfigFlow()
            flow.hass = hass
            flow.context = {}

            mock_entry = MagicMock()
            mock_entry.data = {
                "host": "192.168.1.100",
                CONF_AUTH_MODE: AUTH_MODE_TOKEN,
                CONF_API_TOKEN: "old_token",
            }
            flow._get_reauth_entry = MagicMock(return_value=mock_entry)
            flow._host = "192.168.1.100"
            # Stub out the HA method that reloads and aborts
            flow.async_update_reload_and_abort = MagicMock(
                return_value={"type": "abort", "reason": "reauth_successful"}
            )

            result = await flow.async_step_reauth_confirm(
                {CONF_API_TOKEN: "new_token", "scan_interval": 30}
            )

        assert result["type"] == "abort"
        assert result["reason"] == "reauth_successful"
        flow.async_update_reload_and_abort.assert_called_once()

    @pytest.mark.asyncio
    async def test_reauth_flow_invalid_auth(self, hass, mock_aiohttp_session):
        """Lines 198-199: SinumAuthError in reauth → shows form with invalid_auth error."""
        from custom_components.sinum.api import SinumAuthError

        with patch("custom_components.sinum.config_flow.SinumClient") as MockClient:
            client = MagicMock()
            client.test_connection = AsyncMock(side_effect=SinumAuthError("bad"))
            MockClient.return_value = client

            from custom_components.sinum.config_flow import SinumConfigFlow

            flow = SinumConfigFlow()
            flow.hass = hass
            flow.context = {}

            mock_entry = MagicMock()
            mock_entry.data = {
                "host": "192.168.1.100",
                CONF_AUTH_MODE: AUTH_MODE_TOKEN,
                CONF_API_TOKEN: "old_token",
            }
            flow._get_reauth_entry = MagicMock(return_value=mock_entry)
            flow._host = "192.168.1.100"

            result = await flow.async_step_reauth_confirm(
                {CONF_API_TOKEN: "wrong_token", "scan_interval": 30}
            )

        assert result["type"] == "form"
        assert result["errors"]["base"] == "invalid_auth"
