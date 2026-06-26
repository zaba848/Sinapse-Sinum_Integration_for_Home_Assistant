"""Tests for __init__.py setup/unload and helper functions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.sinum.const import (
    ATTR_ENTRY_ID,
    ATTR_NOTIFICATION_MESSAGE,
    ATTR_NOTIFICATION_TITLE,
    ATTR_PAYLOAD,
    ATTR_SCHEDULE_ID,
    AUTH_MODE_PASSWORD,
    AUTH_MODE_TOKEN,
    CONF_API_TOKEN,
    CONF_AUTH_MODE,
    CONF_MQTT_ENABLED,
    CONF_MQTT_TOPIC_PREFIX,
    CONF_WS_ENABLED,
    CONF_WS_PATH,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SERVICE_SEND_NOTIFICATION,
    SERVICE_UPDATE_SCHEDULE,
)


class TestBuildClient:
    def test_token_mode_creates_client_with_api_token(self):
        with patch("custom_components.sinum.async_get_clientsession", return_value=MagicMock()):
            from custom_components.sinum import _build_client

            hass = MagicMock()
            hass.helpers = MagicMock()
            entry = MagicMock()
            entry.data = {
                "host": "10.0.0.1",
                CONF_AUTH_MODE: AUTH_MODE_TOKEN,
                CONF_API_TOKEN: "my-token",
            }

            with patch("custom_components.sinum.async_get_clientsession") as mock_session:
                mock_session.return_value = MagicMock()
                client = _build_client(hass, entry)
            assert client._api_token == "my-token"

    def test_password_mode_creates_client_with_credentials(self):
        from custom_components.sinum import _build_client

        hass = MagicMock()
        entry = MagicMock()
        entry.data = {
            "host": "10.0.0.1",
            CONF_AUTH_MODE: AUTH_MODE_PASSWORD,
            "username": "admin",
            "password": "secret",
        }

        with patch("custom_components.sinum.async_get_clientsession") as mock_session:
            mock_session.return_value = MagicMock()
            client = _build_client(hass, entry)
        assert client._username == "admin"
        assert client._password == "secret"
        assert client._api_token is None


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_setup_entry_token_mode(self, hass):
        """async_setup_entry completes successfully in token auth mode."""
        from custom_components.sinum import async_setup_entry

        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.data = {
            "host": "10.0.0.1",
            CONF_AUTH_MODE: AUTH_MODE_TOKEN,
            CONF_API_TOKEN: "my-token",
            "scan_interval": DEFAULT_SCAN_INTERVAL,
        }
        entry.options = {}

        with (
            patch("custom_components.sinum.async_get_clientsession", return_value=MagicMock()),
            patch("custom_components.sinum.SinumClient") as MockClient,
            patch("custom_components.sinum.SinumCoordinator") as MockCoordinator,
            patch.object(
                hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock
            ) as mock_fwd,
        ):
            client = MagicMock()
            client.login = AsyncMock()
            MockClient.return_value = client

            coordinator = MagicMock()
            coordinator.async_config_entry_first_refresh = AsyncMock()
            coordinator.mqtt_bridge = None
            MockCoordinator.return_value = coordinator

            mock_fwd.return_value = None

            result = await async_setup_entry(hass, entry)
        assert result is True

    @pytest.mark.asyncio
    async def test_setup_entry_updates_title_from_hub_name(self, hass):
        """async_setup_entry syncs stale config entry title with hub name."""
        from custom_components.sinum import async_setup_entry

        entry = MagicMock()
        entry.entry_id = "title_entry"
        entry.title = "Sinum (10.0.0.1)"
        entry.data = {
            "host": "10.0.0.1",
            CONF_AUTH_MODE: AUTH_MODE_TOKEN,
            CONF_API_TOKEN: "tok",
            "scan_interval": DEFAULT_SCAN_INTERVAL,
        }
        entry.options = {}

        with (
            patch("custom_components.sinum.async_get_clientsession", return_value=MagicMock()),
            patch("custom_components.sinum.SinumClient") as MockClient,
            patch("custom_components.sinum.SinumCoordinator") as MockCoordinator,
            patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock),
            patch.object(hass.config_entries, "async_get_entry", return_value=entry),
            patch.object(hass.config_entries, "async_update_entry") as mock_update_entry,
        ):
            client = MagicMock()
            client.login = AsyncMock()
            MockClient.return_value = client

            coordinator = MagicMock()
            coordinator.async_config_entry_first_refresh = AsyncMock()
            coordinator.hub_info = {"name": "Living Hub"}
            coordinator.mqtt_bridge = None
            MockCoordinator.return_value = coordinator

            await async_setup_entry(hass, entry)

        mock_update_entry.assert_called_once_with(entry, title="Sinum (Living Hub)")

    @pytest.mark.asyncio
    async def test_setup_entry_mqtt_bridge_started_when_enabled(self, hass):
        from custom_components.sinum import _MQTT_BRIDGES, async_setup_entry

        entry = MagicMock()
        entry.entry_id = "mqtt_entry"
        entry.data = {
            "host": "10.0.0.1",
            CONF_AUTH_MODE: AUTH_MODE_TOKEN,
            CONF_API_TOKEN: "tok",
            CONF_MQTT_ENABLED: True,
            "scan_interval": DEFAULT_SCAN_INTERVAL,
        }
        entry.options = {CONF_MQTT_TOPIC_PREFIX: "sinum/hub-a"}

        with (
            patch("custom_components.sinum.async_get_clientsession", return_value=MagicMock()),
            patch("custom_components.sinum.SinumClient") as MockClient,
            patch("custom_components.sinum.SinumCoordinator") as MockCoordinator,
            patch("custom_components.sinum.SinumMqttBridge") as MockBridge,
            patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock),
        ):
            client = MagicMock()
            client.login = AsyncMock()
            MockClient.return_value = client

            coordinator = MagicMock()
            coordinator.async_config_entry_first_refresh = AsyncMock()
            coordinator.mqtt_bridge = None
            MockCoordinator.return_value = coordinator

            bridge = MagicMock()
            bridge.async_start = AsyncMock(return_value=True)
            bridge.async_stop = AsyncMock()
            MockBridge.return_value = bridge

            await async_setup_entry(hass, entry)

        assert "mqtt_entry" in _MQTT_BRIDGES
        MockBridge.assert_called_once_with(hass, coordinator, topic_prefix="sinum/hub-a")
        _MQTT_BRIDGES.pop("mqtt_entry", None)  # cleanup

    @pytest.mark.asyncio
    async def test_setup_entry_mqtt_bridge_not_started_when_disabled(self, hass):
        from custom_components.sinum import _MQTT_BRIDGES, async_setup_entry

        entry = MagicMock()
        entry.entry_id = "no_mqtt_entry"
        entry.data = {
            "host": "10.0.0.1",
            CONF_AUTH_MODE: AUTH_MODE_TOKEN,
            CONF_API_TOKEN: "tok",
            CONF_MQTT_ENABLED: False,
            "scan_interval": DEFAULT_SCAN_INTERVAL,
        }
        entry.options = {}

        with (
            patch("custom_components.sinum.async_get_clientsession", return_value=MagicMock()),
            patch("custom_components.sinum.SinumClient") as MockClient,
            patch("custom_components.sinum.SinumCoordinator") as MockCoordinator,
            patch("custom_components.sinum.SinumMqttBridge") as MockBridge,
            patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock),
        ):
            client = MagicMock()
            client.login = AsyncMock()
            MockClient.return_value = client

            coordinator = MagicMock()
            coordinator.async_config_entry_first_refresh = AsyncMock()
            coordinator.mqtt_bridge = None
            MockCoordinator.return_value = coordinator

            bridge = MagicMock()
            bridge.async_start = AsyncMock(return_value=True)
            MockBridge.return_value = bridge

            await async_setup_entry(hass, entry)

        assert "no_mqtt_entry" not in _MQTT_BRIDGES
        MockBridge.assert_not_called()

    @pytest.mark.asyncio
    async def test_setup_entry_ws_bridge_started_when_enabled(self, hass):
        from custom_components.sinum import _WS_BRIDGES, async_setup_entry

        entry = MagicMock()
        entry.entry_id = "ws_entry"
        entry.data = {
            "host": "10.0.0.1",
            CONF_AUTH_MODE: AUTH_MODE_TOKEN,
            CONF_API_TOKEN: "tok",
            CONF_WS_ENABLED: True,
            "scan_interval": DEFAULT_SCAN_INTERVAL,
        }
        entry.options = {CONF_WS_PATH: "/api/v1/ws"}

        with (
            patch("custom_components.sinum.async_get_clientsession", return_value=MagicMock()),
            patch("custom_components.sinum.SinumClient") as MockClient,
            patch("custom_components.sinum.SinumCoordinator") as MockCoordinator,
            patch("custom_components.sinum.SinumWebSocketBridge") as MockWsBridge,
            patch("custom_components.sinum.SinumMqttBridge") as MockMqttBridge,
            patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock),
        ):
            client = MagicMock()
            client.login = AsyncMock()
            MockClient.return_value = client

            coordinator = MagicMock()
            coordinator.async_config_entry_first_refresh = AsyncMock()
            coordinator.client = client
            coordinator.update_interval = None
            coordinator.mqtt_bridge = None
            MockCoordinator.return_value = coordinator

            ws_bridge = MagicMock()
            ws_bridge.async_start = AsyncMock(return_value=True)
            MockWsBridge.return_value = ws_bridge

            await async_setup_entry(hass, entry)

        assert "ws_entry" in _WS_BRIDGES
        MockWsBridge.assert_called_once_with(
            hass,
            client,
            coordinator,
            ws_path="/api/v1/ws",
        )
        MockMqttBridge.assert_not_called()
        _WS_BRIDGES.pop("ws_entry", None)


class TestAsyncUnloadEntry:
    @pytest.mark.asyncio
    async def test_unload_entry_stops_mqtt_bridge(self, hass):
        from custom_components.sinum import _MQTT_BRIDGES, async_unload_entry

        bridge = MagicMock()
        bridge.async_stop = AsyncMock()
        _MQTT_BRIDGES["unload_test"] = bridge

        entry = MagicMock()
        entry.entry_id = "unload_test"

        with (
            patch.object(hass.config_entries, "async_unload_platforms", return_value=True),
            patch.object(hass.config_entries, "async_entries", return_value=[entry]),
        ):
            result = await async_unload_entry(hass, entry)

        assert result is True
        bridge.async_stop.assert_awaited_once()
        assert "unload_test" not in _MQTT_BRIDGES

    @pytest.mark.asyncio
    async def test_unload_entry_without_bridge(self, hass):
        from custom_components.sinum import async_unload_entry

        entry = MagicMock()
        entry.entry_id = "no_bridge_entry"

        with (
            patch.object(hass.config_entries, "async_unload_platforms", return_value=True),
            patch.object(hass.config_entries, "async_entries", return_value=[]),
        ):
            result = await async_unload_entry(hass, entry)

        assert result is True


class TestAsyncUpdateListener:
    @pytest.mark.asyncio
    async def test_update_listener_reloads_entry(self, hass):
        from custom_components.sinum import _async_update_listener

        entry = MagicMock()
        entry.entry_id = "reload_entry"

        with patch.object(
            hass.config_entries, "async_reload", new_callable=AsyncMock
        ) as mock_reload:
            await _async_update_listener(hass, entry)
        mock_reload.assert_awaited_once_with("reload_entry")


class TestSendNotificationService:
    @pytest.mark.asyncio
    async def test_send_notification_service_called(self, hass):
        """Service handle_send_notification calls client.send_notification."""
        from custom_components.sinum import async_setup_entry
        from custom_components.sinum.const import (
            ATTR_NOTIFICATION_MESSAGE,
            ATTR_NOTIFICATION_TITLE,
            DOMAIN,
            SERVICE_SEND_NOTIFICATION,
        )

        mock_client = MagicMock()
        mock_client.send_notification = AsyncMock(return_value=None)
        mock_client.login = AsyncMock()

        coord = MagicMock()
        coord.async_config_entry_first_refresh = AsyncMock()
        coord.client = mock_client

        entry = MagicMock()
        entry.entry_id = "svc_test"
        entry.options = {}
        entry.data = {
            "host": "10.0.0.1",
            "auth_mode": "token",
            "api_token": "tok",
            "scan_interval": 30,
        }

        with (
            patch("custom_components.sinum.SinumCoordinator", return_value=coord),
            patch("custom_components.sinum.SinumClient", return_value=mock_client),
            patch("custom_components.sinum.async_get_clientsession", return_value=MagicMock()),
            patch("custom_components.sinum.SinumMqttBridge"),
            patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock),
        ):
            await async_setup_entry(hass, entry)

        # Call the registered service and verify it invokes client.send_notification
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND_NOTIFICATION,
            {ATTR_NOTIFICATION_TITLE: "Test", ATTR_NOTIFICATION_MESSAGE: "Hello"},
            blocking=True,
        )
        mock_client.send_notification.assert_awaited_once_with(title="Test", message="Hello")

    @pytest.mark.asyncio
    async def test_send_notification_service_registered_once_for_two_entries(self, hass):
        """Two loaded hubs share one service and receive the same notification call."""
        from custom_components.sinum import async_setup_entry

        client_a = MagicMock()
        client_a.send_notification = AsyncMock(return_value=None)
        client_a.login = AsyncMock()
        client_b = MagicMock()
        client_b.send_notification = AsyncMock(return_value=None)
        client_b.login = AsyncMock()

        coordinator_a = MagicMock()
        coordinator_a.async_config_entry_first_refresh = AsyncMock()
        coordinator_a.hub_info = {"name": "Hub A"}
        coordinator_a.mqtt_bridge = None
        coordinator_b = MagicMock()
        coordinator_b.async_config_entry_first_refresh = AsyncMock()
        coordinator_b.hub_info = {"name": "Hub B"}
        coordinator_b.mqtt_bridge = None

        entry_a = MagicMock()
        entry_a.entry_id = "hub_a"
        entry_a.title = "Sinum (Hub A)"
        entry_a.options = {}
        entry_a.data = {
            "host": "10.0.61.132",
            "auth_mode": "token",
            "api_token": "tok-a",
            "scan_interval": 30,
        }
        entry_b = MagicMock()
        entry_b.entry_id = "hub_b"
        entry_b.title = "Sinum (Hub B)"
        entry_b.options = {}
        entry_b.data = {
            "host": "10.0.62.167",
            "auth_mode": "token",
            "api_token": "tok-b",
            "scan_interval": 30,
        }

        with (
            patch("custom_components.sinum.SinumCoordinator") as mock_coordinator,
            patch("custom_components.sinum.SinumClient") as mock_client_cls,
            patch("custom_components.sinum.async_get_clientsession", return_value=MagicMock()),
            patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock),
        ):
            mock_client_cls.side_effect = [client_a, client_b]
            mock_coordinator.side_effect = [coordinator_a, coordinator_b]

            await async_setup_entry(hass, entry_a)
            service_after_first_setup = hass.services.async_services()[DOMAIN][
                SERVICE_SEND_NOTIFICATION
            ]
            await async_setup_entry(hass, entry_b)

        assert hass.services.has_service(DOMAIN, SERVICE_SEND_NOTIFICATION)
        assert (
            hass.services.async_services()[DOMAIN][SERVICE_SEND_NOTIFICATION]
            is service_after_first_setup
        )

        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND_NOTIFICATION,
            {ATTR_NOTIFICATION_TITLE: "Test", ATTR_NOTIFICATION_MESSAGE: "Hello"},
            blocking=True,
        )

        client_a.send_notification.assert_awaited_once_with(title="Test", message="Hello")
        client_b.send_notification.assert_awaited_once_with(title="Test", message="Hello")


class TestUpdateScheduleService:
    @pytest.mark.asyncio
    async def test_update_schedule_single_hub_without_entry_id(self, hass):
        from custom_components.sinum import async_setup_entry

        mock_client = MagicMock()
        mock_client.login = AsyncMock()
        mock_client.patch_schedule = AsyncMock(return_value={"id": 1, "name": "Morning"})

        coordinator = MagicMock()
        coordinator.async_config_entry_first_refresh = AsyncMock()
        coordinator.client = mock_client
        coordinator.hub_info = {"name": "Hub A"}
        coordinator.mqtt_bridge = None
        coordinator.schedules = [{"id": 1, "name": "Old"}]
        coordinator.data = {"schedules": coordinator.schedules}
        coordinator.async_set_updated_data = MagicMock()

        entry = MagicMock()
        entry.entry_id = "hub_a"
        entry.title = "Sinum (Hub A)"
        entry.options = {}
        entry.data = {
            "host": "10.0.61.132",
            "auth_mode": "token",
            "api_token": "tok-a",
            "scan_interval": 30,
        }

        with (
            patch("custom_components.sinum.SinumCoordinator", return_value=coordinator),
            patch("custom_components.sinum.SinumClient", return_value=mock_client),
            patch("custom_components.sinum.async_get_clientsession", return_value=MagicMock()),
            patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock),
        ):
            await async_setup_entry(hass, entry)

        await hass.services.async_call(
            DOMAIN,
            SERVICE_UPDATE_SCHEDULE,
            {ATTR_SCHEDULE_ID: 1, ATTR_PAYLOAD: {"name": "Morning"}},
            blocking=True,
        )

        mock_client.patch_schedule.assert_awaited_once_with(1, {"name": "Morning"})
        assert coordinator.schedules[0]["name"] == "Morning"
        coordinator.async_set_updated_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_schedule_two_hubs_requires_and_routes_entry_id(self, hass):
        from homeassistant.exceptions import HomeAssistantError

        from custom_components.sinum import async_setup_entry

        client_a = MagicMock()
        client_a.login = AsyncMock()
        client_a.patch_schedule = AsyncMock(return_value={})
        client_b = MagicMock()
        client_b.login = AsyncMock()
        client_b.patch_schedule = AsyncMock(return_value={"id": 7, "name": "Evening"})

        coordinator_a = MagicMock()
        coordinator_a.async_config_entry_first_refresh = AsyncMock()
        coordinator_a.client = client_a
        coordinator_a.hub_info = {"name": "Hub A"}
        coordinator_a.mqtt_bridge = None
        coordinator_a.schedules = [{"id": 7, "name": "A"}]
        coordinator_a.data = {}
        coordinator_a.async_set_updated_data = MagicMock()
        coordinator_b = MagicMock()
        coordinator_b.async_config_entry_first_refresh = AsyncMock()
        coordinator_b.client = client_b
        coordinator_b.hub_info = {"name": "Hub B"}
        coordinator_b.mqtt_bridge = None
        coordinator_b.schedules = [{"id": 7, "name": "Old"}]
        coordinator_b.data = {}
        coordinator_b.async_set_updated_data = MagicMock()

        entry_a = MagicMock()
        entry_a.entry_id = "hub_a"
        entry_a.title = "Sinum (Hub A)"
        entry_a.options = {}
        entry_a.data = {
            "host": "10.0.61.132",
            "auth_mode": "token",
            "api_token": "tok-a",
            "scan_interval": 30,
        }
        entry_b = MagicMock()
        entry_b.entry_id = "hub_b"
        entry_b.title = "Sinum (Hub B)"
        entry_b.options = {}
        entry_b.data = {
            "host": "10.0.62.167",
            "auth_mode": "token",
            "api_token": "tok-b",
            "scan_interval": 30,
        }

        with (
            patch("custom_components.sinum.SinumCoordinator") as mock_coordinator,
            patch("custom_components.sinum.SinumClient") as mock_client_cls,
            patch("custom_components.sinum.async_get_clientsession", return_value=MagicMock()),
            patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock),
        ):
            mock_client_cls.side_effect = [client_a, client_b]
            mock_coordinator.side_effect = [coordinator_a, coordinator_b]
            await async_setup_entry(hass, entry_a)
            await async_setup_entry(hass, entry_b)

        with pytest.raises(HomeAssistantError, match="entry_id is required"):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_UPDATE_SCHEDULE,
                {ATTR_SCHEDULE_ID: 7, ATTR_PAYLOAD: {"name": "Skipped"}},
                blocking=True,
            )

        await hass.services.async_call(
            DOMAIN,
            SERVICE_UPDATE_SCHEDULE,
            {
                ATTR_ENTRY_ID: "hub_b",
                ATTR_SCHEDULE_ID: 7,
                ATTR_PAYLOAD: {"name": "Evening"},
            },
            blocking=True,
        )

        client_a.patch_schedule.assert_not_awaited()
        client_b.patch_schedule.assert_awaited_once_with(7, {"name": "Evening"})
        assert coordinator_b.schedules[0]["name"] == "Evening"


class TestInitHelpers:
    def test_select_coordinator_returns_only_loaded_hub(self, hass):
        from custom_components.sinum import _coordinators, _select_coordinator

        coordinator = MagicMock()
        _coordinators(hass)["entry_a"] = coordinator

        assert _select_coordinator(hass, None) is coordinator

    def test_select_coordinator_raises_for_missing_entry(self, hass):
        from custom_components.sinum import _select_coordinator

        with pytest.raises(HomeAssistantError, match="not loaded"):
            _select_coordinator(hass, "missing")

    def test_select_coordinator_raises_when_no_hubs_loaded(self, hass):
        from custom_components.sinum import _select_coordinator

        with pytest.raises(HomeAssistantError, match="No Sinum hubs are loaded"):
            _select_coordinator(hass, None)

    def test_merge_schedule_ignores_empty_payload(self):
        from custom_components.sinum import _merge_schedule

        coordinator = MagicMock()
        coordinator.schedules = [{"id": 1, "name": "Morning"}]

        _merge_schedule(coordinator, 1, {})

        assert coordinator.schedules == [{"id": 1, "name": "Morning"}]

    def test_merge_schedule_appends_missing_schedule(self):
        from custom_components.sinum import _merge_schedule

        coordinator = MagicMock()
        coordinator.schedules = [{"id": 1, "name": "Morning"}]

        _merge_schedule(coordinator, 2, {"name": "Evening"})

        assert coordinator.schedules[-1] == {"id": 2, "name": "Evening"}

    def test_sync_entry_title_noop_when_hub_name_missing(self, hass):
        from custom_components.sinum import _sync_entry_title

        entry = MagicMock()
        entry.entry_id = "entry_a"
        entry.title = "Sinum (10.0.0.1)"
        coordinator = MagicMock()
        coordinator.hub_info = {}

        with patch.object(hass.config_entries, "async_update_entry") as mock_update:
            _sync_entry_title(hass, entry, coordinator)

        mock_update.assert_not_called()

    def test_remove_domain_services_noop_when_other_coordinators_exist(self, hass):
        from custom_components.sinum import (
            _coordinators,
            _remove_domain_services_if_no_coordinators,
        )

        _coordinators(hass)["entry_a"] = MagicMock()
        hass.services = MagicMock()

        _remove_domain_services_if_no_coordinators(hass)

        hass.services.async_remove.assert_not_called()

    @pytest.mark.asyncio
    async def test_unload_entry_removes_services_for_last_hub(self):
        from custom_components.sinum import (
            DATA_COORDINATORS,
            DATA_NOTIFICATION_CLIENTS,
            SERVICE_SEND_NOTIFICATION,
            SERVICE_UPDATE_SCHEDULE,
            async_unload_entry,
        )

        hass = MagicMock()
        hass.data = {DOMAIN: {}}
        hass.services = MagicMock()
        hass.services.has_service.return_value = True
        hass.services.async_remove = MagicMock()
        hass.config_entries = MagicMock()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        entry = MagicMock()
        entry.entry_id = "last_entry"
        hass.data.setdefault(DOMAIN, {})[DATA_COORDINATORS] = {"last_entry": MagicMock()}
        hass.data.setdefault(DOMAIN, {})[DATA_NOTIFICATION_CLIENTS] = {"last_entry": MagicMock()}

        result = await async_unload_entry(hass, entry)

        assert result is True
        hass.services.async_remove.assert_any_call(DOMAIN, SERVICE_SEND_NOTIFICATION)
        hass.services.async_remove.assert_any_call(DOMAIN, SERVICE_UPDATE_SCHEDULE)

    @pytest.mark.asyncio
    async def test_unload_entry_returns_false_when_platform_unload_fails(self, hass):
        from custom_components.sinum import async_unload_entry

        entry = MagicMock()
        entry.entry_id = "entry_fail"

        with patch.object(hass.config_entries, "async_unload_platforms", return_value=False):
            result = await async_unload_entry(hass, entry)

        assert result is False
