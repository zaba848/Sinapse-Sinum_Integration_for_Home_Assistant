"""Tests for Sinum config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol

from custom_components.sinum.api import SinumAuthError, SinumConnectionError
from custom_components.sinum.const import (
    AUTH_MODE_PASSWORD,
    AUTH_MODE_TOKEN,
    CONF_API_TOKEN,
    CONF_AUTH_MODE,
    CONF_MQTT_ENABLED,
    CONF_MQTT_TOPIC_PREFIX,
    DEFAULT_MQTT_TOPIC_PREFIX,
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
        with patch("custom_components.sinum.config_flow.SinumClient") as MockClient:
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

            result2 = await flow.async_step_token({CONF_API_TOKEN: "mytoken", "scan_interval": 30})
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

            result = await flow.async_step_token({CONF_API_TOKEN: "bad-token", "scan_interval": 30})
            assert result["type"] == "form"
            assert result["errors"]["base"] == "invalid_auth"

    @pytest.mark.asyncio
    async def test_token_flow_cannot_connect(self, hass, mock_aiohttp_session):
        with patch("custom_components.sinum.config_flow.SinumClient") as MockClient:
            client = MagicMock()
            client.get_hub_info = AsyncMock(side_effect=SinumConnectionError("timeout"))
            MockClient.return_value = client

            from custom_components.sinum.config_flow import SinumConfigFlow

            flow = SinumConfigFlow()
            flow.hass = hass
            flow._host = "192.168.1.100"
            flow._auth_mode = AUTH_MODE_TOKEN

            result = await flow.async_step_token({CONF_API_TOKEN: "tok", "scan_interval": 30})
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
        with pytest.raises(vol.Invalid):
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


class TestReconfigureFlow:
    """Tests for async_step_reconfigure (change host/creds without reinstall)."""

    @pytest.mark.asyncio
    async def test_reconfigure_shows_form_prefilled(self, hass, mock_aiohttp_session):
        """Step reconfigure shows form pre-filled with current host and auth_mode."""
        from custom_components.sinum.config_flow import SinumConfigFlow

        flow = SinumConfigFlow()
        flow.hass = hass
        flow.context = {}

        mock_entry = MagicMock()
        mock_entry.data = {
            "host": "10.0.0.1",
            CONF_AUTH_MODE: AUTH_MODE_TOKEN,
            CONF_API_TOKEN: "old_token",
        }
        flow._get_reconfigure_entry = MagicMock(return_value=mock_entry)

        result = await flow.async_step_reconfigure(None)

        assert result["type"] == "form"
        assert result["step_id"] == "reconfigure"

    @pytest.mark.asyncio
    async def test_reconfigure_token_success(self, hass, mock_aiohttp_session):
        """Reconfigure with token → updates entry data and reloads."""
        with patch("custom_components.sinum.config_flow.SinumClient") as MockClient:
            client = MagicMock()
            client.get_hub_info = AsyncMock(return_value={"name": "tablica-new"})
            MockClient.return_value = client

            from custom_components.sinum.config_flow import SinumConfigFlow

            flow = SinumConfigFlow()
            flow.hass = hass
            flow.context = {}

            mock_entry = MagicMock()
            mock_entry.data = {
                "host": "10.0.0.1",
                CONF_AUTH_MODE: AUTH_MODE_TOKEN,
                CONF_API_TOKEN: "old_token",
            }
            flow._get_reconfigure_entry = MagicMock(return_value=mock_entry)
            flow.async_update_reload_and_abort = MagicMock(
                return_value={"type": "abort", "reason": "reconfigure_successful"}
            )

            # Step 1: reconfigure form
            await flow.async_step_reconfigure(None)
            # Step 2: submit new host + auth_mode
            await flow.async_step_reconfigure(
                {"host": "10.0.0.200", CONF_AUTH_MODE: AUTH_MODE_TOKEN}
            )
            # Step 3: submit token credentials
            result = await flow.async_step_token({CONF_API_TOKEN: "new_token", "scan_interval": 30})

        assert result["type"] == "abort"
        flow.async_update_reload_and_abort.assert_called_once()

    @pytest.mark.asyncio
    async def test_reconfigure_password_success(self, hass, mock_aiohttp_session):
        """Reconfigure with password → updates entry data."""
        with patch("custom_components.sinum.config_flow.SinumClient") as MockClient:
            client = MagicMock()
            client.login = AsyncMock(return_value=None)
            client.get_hub_info = AsyncMock(return_value={"name": "hub"})
            MockClient.return_value = client

            from custom_components.sinum.config_flow import SinumConfigFlow

            flow = SinumConfigFlow()
            flow.hass = hass
            flow.context = {}

            mock_entry = MagicMock()
            mock_entry.data = {
                "host": "10.0.0.1",
                CONF_AUTH_MODE: AUTH_MODE_PASSWORD,
                "username": "admin",
                "password": "old",
            }
            flow._get_reconfigure_entry = MagicMock(return_value=mock_entry)
            flow.async_update_reload_and_abort = MagicMock(
                return_value={"type": "abort", "reason": "reconfigure_successful"}
            )

            await flow.async_step_reconfigure(None)
            await flow.async_step_reconfigure(
                {"host": "10.0.0.1", CONF_AUTH_MODE: AUTH_MODE_PASSWORD}
            )
            result = await flow.async_step_password(
                {"username": "admin", "password": "new_pass", "scan_interval": 30}
            )

        assert result["type"] == "abort"
        flow.async_update_reload_and_abort.assert_called_once()

    @pytest.mark.asyncio
    async def test_reconfigure_connection_error(self, hass, mock_aiohttp_session):
        """Reconfigure with unreachable host → shows form with cannot_connect error."""
        with patch("custom_components.sinum.config_flow.SinumClient") as MockClient:
            client = MagicMock()
            client.get_hub_info = AsyncMock(side_effect=SinumConnectionError("timeout"))
            MockClient.return_value = client

            from custom_components.sinum.config_flow import SinumConfigFlow

            flow = SinumConfigFlow()
            flow.hass = hass
            flow.context = {}

            mock_entry = MagicMock()
            mock_entry.data = {"host": "10.0.0.1", CONF_AUTH_MODE: AUTH_MODE_TOKEN}
            flow._get_reconfigure_entry = MagicMock(return_value=mock_entry)

            await flow.async_step_reconfigure(None)
            await flow.async_step_reconfigure(
                {"host": "10.0.0.200", CONF_AUTH_MODE: AUTH_MODE_TOKEN}
            )
            result = await flow.async_step_token({CONF_API_TOKEN: "tok", "scan_interval": 30})

        assert result["type"] == "form"
        assert result["errors"]["base"] == "cannot_connect"


class TestMigrateEntry:
    """Tests for async_migrate_entry."""

    @pytest.mark.asyncio
    async def test_migrate_backfills_auth_mode(self, hass):
        """Entries missing auth_mode get AUTH_MODE_TOKEN backfilled."""
        from custom_components.sinum import async_migrate_entry

        mock_entry = MagicMock()
        mock_entry.version = 1
        mock_entry.data = {"host": "10.0.0.1", "api_token": "tok"}

        hass.config_entries = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()

        result = await async_migrate_entry(hass, mock_entry)

        assert result is True
        hass.config_entries.async_update_entry.assert_called_once()
        call_kwargs = hass.config_entries.async_update_entry.call_args[1]
        assert call_kwargs["data"][CONF_AUTH_MODE] == AUTH_MODE_TOKEN

    @pytest.mark.asyncio
    async def test_migrate_skips_if_auth_mode_present(self, hass):
        """Entries that already have auth_mode are not modified."""
        from custom_components.sinum import async_migrate_entry

        mock_entry = MagicMock()
        mock_entry.version = 1
        mock_entry.data = {
            "host": "10.0.0.1",
            CONF_AUTH_MODE: AUTH_MODE_PASSWORD,
            "username": "admin",
            "password": "pass",
        }

        hass.config_entries = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()

        result = await async_migrate_entry(hass, mock_entry)

        assert result is True
        hass.config_entries.async_update_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_migrate_rejects_unknown_version(self, hass):
        """Entries with version > 1 cannot be migrated — returns False."""
        from custom_components.sinum import async_migrate_entry

        mock_entry = MagicMock()
        mock_entry.version = 99
        mock_entry.data = {}

        result = await async_migrate_entry(hass, mock_entry)

        assert result is False


class TestConfigFlowUserStep:
    """Cover async_step_user show-form branch (lines 71-75) and password dispatch."""

    @pytest.mark.asyncio
    async def test_user_step_shows_form_when_no_input(self, hass, mock_aiohttp_session):
        from custom_components.sinum.config_flow import SinumConfigFlow

        flow = SinumConfigFlow()
        flow.hass = hass
        flow.context = {}

        result = await flow.async_step_user(None)

        assert result["type"] == "form"
        assert result["step_id"] == "user"

    @pytest.mark.asyncio
    async def test_user_step_dispatches_to_password(self, hass, mock_aiohttp_session):
        """user input with AUTH_MODE_PASSWORD should open the password step."""
        from custom_components.sinum.config_flow import SinumConfigFlow

        flow = SinumConfigFlow()
        flow.hass = hass
        flow.context = {}

        # stub password step to avoid making real connections
        async def _fake_password():
            return {"type": "form", "step_id": "password", "errors": {}}

        flow.async_step_password = lambda **_kw: _fake_password()

        result = await flow.async_step_user({"host": "192.168.1.1", "auth_mode": "password"})

        assert result["step_id"] == "password"


class TestConfigFlowTokenUnknownError:
    """Cover the bare Exception branch in async_step_token (lines 94-96)."""

    @pytest.mark.asyncio
    async def test_token_flow_unknown_exception(self, hass, mock_aiohttp_session):
        with patch("custom_components.sinum.config_flow.SinumClient") as MockClient:
            client = MagicMock()
            client.get_hub_info = AsyncMock(side_effect=RuntimeError("unexpected"))
            MockClient.return_value = client

            from custom_components.sinum.config_flow import SinumConfigFlow

            flow = SinumConfigFlow()
            flow.hass = hass
            flow._host = "192.168.1.100"

            result = await flow.async_step_token({"api_token": "tok", "scan_interval": 30})

        assert result["type"] == "form"
        assert result["errors"]["base"] == "unknown"


class TestConfigFlowPasswordEdgeCases:
    """Cover remaining password-step error paths (lines 126-132, 144)."""

    @pytest.mark.asyncio
    async def test_password_invalid_auth(self, hass, mock_aiohttp_session):
        with patch("custom_components.sinum.config_flow.SinumClient") as MockClient:
            client = MagicMock()
            client.login = AsyncMock(side_effect=SinumAuthError("bad"))
            MockClient.return_value = client

            from custom_components.sinum.config_flow import SinumConfigFlow

            flow = SinumConfigFlow()
            flow.hass = hass
            flow._host = "192.168.1.100"

            result = await flow.async_step_password(
                {"username": "u", "password": "p", "scan_interval": 30}
            )

        assert result["type"] == "form"
        assert result["errors"]["base"] == "invalid_auth"

    @pytest.mark.asyncio
    async def test_password_cannot_connect(self, hass, mock_aiohttp_session):
        with patch("custom_components.sinum.config_flow.SinumClient") as MockClient:
            client = MagicMock()
            client.login = AsyncMock(side_effect=SinumConnectionError("timeout"))
            MockClient.return_value = client

            from custom_components.sinum.config_flow import SinumConfigFlow

            flow = SinumConfigFlow()
            flow.hass = hass
            flow._host = "192.168.1.100"

            result = await flow.async_step_password(
                {"username": "u", "password": "p", "scan_interval": 30}
            )

        assert result["errors"]["base"] == "cannot_connect"

    @pytest.mark.asyncio
    async def test_password_unknown_exception(self, hass, mock_aiohttp_session):
        with patch("custom_components.sinum.config_flow.SinumClient") as MockClient:
            client = MagicMock()
            client.login = AsyncMock(side_effect=RuntimeError("boom"))
            MockClient.return_value = client

            from custom_components.sinum.config_flow import SinumConfigFlow

            flow = SinumConfigFlow()
            flow.hass = hass
            flow._host = "192.168.1.100"

            result = await flow.async_step_password(
                {"username": "u", "password": "p", "scan_interval": 30}
            )

        assert result["errors"]["base"] == "unknown"

    @pytest.mark.asyncio
    async def test_password_step_shows_form_when_no_input(self, hass):
        """Line 144: show form when user_input is None."""
        from custom_components.sinum.config_flow import SinumConfigFlow

        flow = SinumConfigFlow()
        flow.hass = hass
        flow._host = "192.168.1.100"

        result = await flow.async_step_password(None)

        assert result["type"] == "form"
        assert result["step_id"] == "password"


class TestReauthPasswordMode:
    """Cover reauth flow with AUTH_MODE_PASSWORD credential path (lines 189-194)."""

    @pytest.mark.asyncio
    async def test_reauth_password_success(self, hass, mock_aiohttp_session):
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
                "auth_mode": "password",
                "username": "admin",
                "password": "old",
            }
            flow._get_reauth_entry = MagicMock(return_value=mock_entry)
            flow.async_update_reload_and_abort = MagicMock(
                return_value={"type": "abort", "reason": "reauth_successful"}
            )

            result = await flow.async_step_reauth_confirm(
                {"username": "admin", "password": "new_pass", "scan_interval": 30}
            )

        assert result["type"] == "abort"

    @pytest.mark.asyncio
    async def test_reauth_cannot_connect(self, hass, mock_aiohttp_session):
        """Line 198: SinumConnectionError in reauth → cannot_connect."""
        with patch("custom_components.sinum.config_flow.SinumClient") as MockClient:
            client = MagicMock()
            client.test_connection = AsyncMock(side_effect=SinumConnectionError("unreachable"))
            MockClient.return_value = client

            from custom_components.sinum.config_flow import SinumConfigFlow

            flow = SinumConfigFlow()
            flow.hass = hass
            flow.context = {}

            mock_entry = MagicMock()
            mock_entry.data = {
                "host": "192.168.1.100",
                "auth_mode": "token",
                "api_token": "tok",
            }
            flow._get_reauth_entry = MagicMock(return_value=mock_entry)

            result = await flow.async_step_reauth_confirm({"api_token": "tok", "scan_interval": 30})

        assert result["errors"]["base"] == "cannot_connect"


class TestConfigFlowFailsafeAndFallback:
    @pytest.mark.asyncio
    async def test_user_step_rejects_invalid_host_with_path(self, hass, mock_aiohttp_session):
        from custom_components.sinum.config_flow import SinumConfigFlow

        flow = SinumConfigFlow()
        flow.hass = hass
        flow.context = {}

        result = await flow.async_step_user(
            {"host": "http://10.0.0.1/api", "auth_mode": AUTH_MODE_TOKEN}
        )

        assert result["type"] == "form"
        assert result["errors"]["base"] == "invalid_host"

    @pytest.mark.asyncio
    async def test_reconfigure_rejects_invalid_host(self, hass, mock_aiohttp_session):
        from custom_components.sinum.config_flow import SinumConfigFlow

        flow = SinumConfigFlow()
        flow.hass = hass
        flow.context = {}

        mock_entry = MagicMock()
        mock_entry.data = {"host": "10.0.0.1", CONF_AUTH_MODE: AUTH_MODE_TOKEN}
        flow._get_reconfigure_entry = MagicMock(return_value=mock_entry)

        result = await flow.async_step_reconfigure(
            {"host": "10.0.0.1/path", CONF_AUTH_MODE: AUTH_MODE_TOKEN}
        )

        assert result["type"] == "form"
        assert result["errors"]["base"] == "invalid_host"

    @pytest.mark.asyncio
    async def test_probe_retry_succeeds_after_transient_connection_error(
        self, hass, mock_aiohttp_session
    ):
        from custom_components.sinum.config_flow import SinumConfigFlow

        flow = SinumConfigFlow()
        flow.hass = hass

        calls = {"count": 0}

        async def _op():
            calls["count"] += 1
            if calls["count"] == 1:
                raise SinumConnectionError("temporary")
            return "ok"

        result = await flow._run_probe_with_retry(_op)

        assert result == "ok"
        assert calls["count"] == 2

    @pytest.mark.asyncio
    async def test_password_flow_falls_back_when_hub_info_unavailable_after_login(
        self, hass, mock_aiohttp_session
    ):
        with patch("custom_components.sinum.config_flow.SinumClient") as MockClient:
            client = MagicMock()
            client.login = AsyncMock(return_value=None)
            client.get_hub_info = AsyncMock(side_effect=SinumConnectionError("busy"))
            MockClient.return_value = client

            from custom_components.sinum.config_flow import SinumConfigFlow

            flow = SinumConfigFlow()
            flow.hass = hass
            flow.context = {}
            flow._host = "10.0.0.1"

            result = await flow.async_step_password(
                {"username": "admin", "password": "secret", "scan_interval": 30}
            )

        assert result["type"] == "create_entry"
        assert result["title"] == "Sinum (10.0.0.1)"
