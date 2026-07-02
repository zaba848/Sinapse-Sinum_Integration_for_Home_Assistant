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

        result = await flow.async_step_user({"host": "10.0.0.1", "auth_mode": AUTH_MODE_PASSWORD})
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

            result = await flow.async_step_token({CONF_API_TOKEN: "tok", "scan_interval": 30})
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


class TestReauthPasswordPath:
    @pytest.fixture
    def mock_aiohttp_session(self):
        with patch(
            "custom_components.sinum.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ):
            yield

    @pytest.mark.asyncio
    async def test_reauth_password_path_success(self, hass, mock_aiohttp_session):
        """Reauth confirm with password auth_mode calls _make_client with username/password."""
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
                CONF_AUTH_MODE: AUTH_MODE_PASSWORD,
                "username": "admin",
                "password": "old",
            }
            flow._get_reauth_entry = MagicMock(return_value=mock_entry)
            flow._host = "192.168.1.100"
            flow.async_update_reload_and_abort = MagicMock(
                return_value={"type": "abort", "reason": "reauth_successful"}
            )

            result = await flow.async_step_reauth_confirm(
                {"username": "admin", "password": "newpass", "scan_interval": 30}
            )

        assert result["type"] == "abort"
        assert result["reason"] == "reauth_successful"

    @pytest.mark.asyncio
    async def test_reauth_cannot_connect(self, hass, mock_aiohttp_session):
        """Reauth SinumConnectionError → shows form with cannot_connect error."""
        with patch("custom_components.sinum.config_flow.SinumClient") as MockClient:
            client = MagicMock()
            client.test_connection = AsyncMock(side_effect=SinumConnectionError("timeout"))
            MockClient.return_value = client

            from custom_components.sinum.config_flow import SinumConfigFlow

            flow = SinumConfigFlow()
            flow.hass = hass
            flow.context = {}

            mock_entry = MagicMock()
            mock_entry.data = {
                "host": "192.168.1.100",
                CONF_AUTH_MODE: AUTH_MODE_TOKEN,
                CONF_API_TOKEN: "tok",
            }
            flow._get_reauth_entry = MagicMock(return_value=mock_entry)
            flow._host = "192.168.1.100"

            result = await flow.async_step_reauth_confirm(
                {CONF_API_TOKEN: "tok2", "scan_interval": 30}
            )

        assert result["type"] == "form"
        assert result["errors"]["base"] == "cannot_connect"


class TestNormalizeHostInput:
    """Direct tests for _normalize_host_input edge cases."""

    def _normalize(self, value: str) -> str:
        from custom_components.sinum.config_flow import _normalize_host_input
        return _normalize_host_input(value)

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="empty host"):
            self._normalize("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="empty host"):
            self._normalize("   ")

    def test_unsupported_scheme_raises(self):
        with pytest.raises(ValueError, match="unsupported scheme"):
            self._normalize("ftp://192.168.1.100")

    def test_url_with_scheme_but_no_netloc_raises(self):
        with pytest.raises(ValueError, match="missing host"):
            self._normalize("http://")

    def test_url_with_path_raises(self):
        with pytest.raises(ValueError, match="path/query/fragment not allowed"):
            self._normalize("http://192.168.1.100/api")

    def test_url_with_query_raises(self):
        with pytest.raises(ValueError, match="path/query/fragment not allowed"):
            self._normalize("http://192.168.1.100?foo=bar")

    def test_url_with_whitespace_netloc_raises(self):
        # http://  / — scheme present, netloc is whitespace, path is /
        with pytest.raises(ValueError, match="invalid host"):
            self._normalize("http://  /")

    def test_plain_ip_accepted(self):
        assert self._normalize("192.168.1.100") == "192.168.1.100"

    def test_http_url_accepted(self):
        assert self._normalize("http://192.168.1.100") == "192.168.1.100"


class TestWebsocketPath:
    """Tests for _websocket_path validator."""

    def _ws_path(self, value: str) -> str:
        from custom_components.sinum.config_flow import _websocket_path
        return _websocket_path(value)

    def test_empty_returns_default(self):
        from custom_components.sinum.const import DEFAULT_WS_PATH
        assert self._ws_path("") == DEFAULT_WS_PATH
        assert self._ws_path("   ") == DEFAULT_WS_PATH

    def test_full_url_raises(self):
        import voluptuous as vol
        with pytest.raises(vol.Invalid, match="endpoint path"):
            self._ws_path("ws://hub.local/api/v1/ws")

    def test_https_url_raises(self):
        import voluptuous as vol
        with pytest.raises(vol.Invalid, match="endpoint path"):
            self._ws_path("https://hub.local/api/v1/ws")

    def test_path_without_slash_gets_prefixed(self):
        assert self._ws_path("api/v1/ws") == "/api/v1/ws"

    def test_path_with_slash_returned_as_is(self):
        assert self._ws_path("/api/v1/ws") == "/api/v1/ws"


class TestProbeRetryExhausted:
    """Line 277: _run_probe_with_retry raises when all attempts return _PROBE_MISSING."""

    @pytest.mark.asyncio
    async def test_run_probe_raises_after_exhausted_retries(self, hass, mock_aiohttp_session):
        from unittest.mock import AsyncMock, patch

        from custom_components.sinum.api import SinumConnectionError
        from custom_components.sinum.config_flow import SinumConfigFlow, _PROBE_MISSING

        flow = SinumConfigFlow()
        flow.hass = hass
        flow._host = "192.168.1.100"

        with patch(
            "custom_components.sinum.config_flow._try_probe",
            new=AsyncMock(return_value=_PROBE_MISSING),
        ):
            with pytest.raises(SinumConnectionError, match="probe failed after retries"):
                await flow._run_probe_with_retry(AsyncMock())


class TestHubNameFromPasswordGenericError:
    """Lines 317-318: generic exception from get_hub_info after successful login."""

    @pytest.mark.asyncio
    async def test_get_hub_info_generic_error_returns_unknown(self, hass, mock_aiohttp_session):
        with patch("custom_components.sinum.config_flow.SinumClient") as MockClient:
            client = MagicMock()
            client.login = AsyncMock(return_value=None)
            client.get_hub_info = AsyncMock(side_effect=RuntimeError("unexpected"))
            MockClient.return_value = client

            from custom_components.sinum.config_flow import SinumConfigFlow

            flow = SinumConfigFlow()
            flow.hass = hass
            flow._host = "192.168.1.100"

            result = await flow.async_step_password(
                {"username": "admin", "password": "pass", "scan_interval": 30}
            )

        assert result["errors"]["base"] == "unknown"
