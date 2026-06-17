"""Extended config flow tests covering password errors, reauth, and edge cases."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sinum.api import SinumAuthError, SinumConnectionError
from custom_components.sinum.const import (
    AUTH_MODE_PASSWORD,
    AUTH_MODE_TOKEN,
    CONF_API_TOKEN,
    CONF_AUTH_MODE,
)


@pytest.fixture
def mock_aiohttp_session():
    with patch(
        "custom_components.sinum.config_flow.async_get_clientsession",
        return_value=MagicMock(),
    ):
        yield


class TestConfigFlowUserStep:
    @pytest.mark.asyncio
    async def test_user_step_no_input_shows_form(self, hass, mock_aiohttp_session):
        from custom_components.sinum.config_flow import SinumConfigFlow

        flow = SinumConfigFlow()
        flow.hass = hass
        flow.context = {}

        result = await flow.async_step_user(None)
        assert result["type"] == "form"
        assert result["step_id"] == "user"

    @pytest.mark.asyncio
    async def test_user_step_password_mode_routes_to_password(self, hass, mock_aiohttp_session):
        from custom_components.sinum.config_flow import SinumConfigFlow

        flow = SinumConfigFlow()
        flow.hass = hass
        flow.context = {}

        result = await flow.async_step_user(
            {"host": "10.0.0.1", "auth_mode": AUTH_MODE_PASSWORD}
        )
        # Should show the password form
        assert result["type"] == "form"
        assert result["step_id"] == "password"


class TestConfigFlowTokenErrors:
    @pytest.mark.asyncio
    async def test_token_unknown_exception_sets_unknown_error(self, hass, mock_aiohttp_session):
        with patch("custom_components.sinum.config_flow.SinumClient") as MockClient:
            client = MagicMock()
            client.test_connection = AsyncMock(side_effect=RuntimeError("surprise"))
            MockClient.return_value = client

            from custom_components.sinum.config_flow import SinumConfigFlow

            flow = SinumConfigFlow()
            flow.hass = hass
            flow._host = "192.168.1.100"

            result = await flow.async_step_token(
                {CONF_API_TOKEN: "tok", "scan_interval": 30}
            )
            assert result["errors"]["base"] == "unknown"


class TestConfigFlowPasswordErrors:
    @pytest.mark.asyncio
    async def test_password_invalid_auth(self, hass, mock_aiohttp_session):
        with patch("custom_components.sinum.config_flow.SinumClient") as MockClient:
            client = MagicMock()
            client.login = AsyncMock(side_effect=SinumAuthError("bad"))
            client.test_connection = AsyncMock(return_value=None)
            MockClient.return_value = client

            from custom_components.sinum.config_flow import SinumConfigFlow

            flow = SinumConfigFlow()
            flow.hass = hass
            flow._host = "192.168.1.100"

            result = await flow.async_step_password(
                {"username": "bad", "password": "wrong", "scan_interval": 30}
            )
            assert result["errors"]["base"] == "invalid_auth"

    @pytest.mark.asyncio
    async def test_password_cannot_connect(self, hass, mock_aiohttp_session):
        with patch("custom_components.sinum.config_flow.SinumClient") as MockClient:
            client = MagicMock()
            client.login = AsyncMock(side_effect=SinumConnectionError("down"))
            client.test_connection = AsyncMock(return_value=None)
            MockClient.return_value = client

            from custom_components.sinum.config_flow import SinumConfigFlow

            flow = SinumConfigFlow()
            flow.hass = hass
            flow._host = "192.168.1.100"

            result = await flow.async_step_password(
                {"username": "admin", "password": "secret", "scan_interval": 30}
            )
            assert result["errors"]["base"] == "cannot_connect"

    @pytest.mark.asyncio
    async def test_password_unknown_exception(self, hass, mock_aiohttp_session):
        with patch("custom_components.sinum.config_flow.SinumClient") as MockClient:
            client = MagicMock()
            client.login = AsyncMock(side_effect=RuntimeError("surprise"))
            client.test_connection = AsyncMock(return_value=None)
            MockClient.return_value = client

            from custom_components.sinum.config_flow import SinumConfigFlow

            flow = SinumConfigFlow()
            flow.hass = hass
            flow._host = "192.168.1.100"

            result = await flow.async_step_password(
                {"username": "admin", "password": "secret", "scan_interval": 30}
            )
            assert result["errors"]["base"] == "unknown"

    @pytest.mark.asyncio
    async def test_password_no_input_shows_form(self, hass, mock_aiohttp_session):
        from custom_components.sinum.config_flow import SinumConfigFlow

        flow = SinumConfigFlow()
        flow.hass = hass
        flow._host = "10.0.0.1"

        result = await flow.async_step_password(None)
        assert result["type"] == "form"
        assert result["step_id"] == "password"


class TestOptionsFlowGetMethod:
    def test_async_get_options_flow_returns_options_flow(self):
        from custom_components.sinum.config_flow import SinumConfigFlow, SinumOptionsFlow

        entry = MagicMock()
        result = SinumConfigFlow.async_get_options_flow(entry)
        assert isinstance(result, SinumOptionsFlow)
