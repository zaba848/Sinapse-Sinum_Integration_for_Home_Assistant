"""Tests for __init__.py setup/unload and helper functions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.sinum.const import (
    ATTR_ENTRY_ID,
    ATTR_MQTT_CLIENT_ID,
    ATTR_MQTT_DRY_RUN,
    ATTR_MQTT_SCENE_ID,
    ATTR_NOTIFICATION_MESSAGE,
    ATTR_NOTIFICATION_TITLE,
    ATTR_PAYLOAD,
    ATTR_RUN_SCENE_ID,
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
    SERVICE_RUN_SCENE,
    SERVICE_SEND_NOTIFICATION,
    SERVICE_UPDATE_SCHEDULE,
    SERVICE_UPLOAD_MQTT_BRIDGE,
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
            entry.options = {}

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
        entry.options = {}

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
    async def test_setup_entry_registers_ha_runtime_contract(self, hass):
        """async_setup_entry wires Home Assistant runtime state after first refresh."""
        from custom_components.sinum import (
            DATA_COORDINATORS,
            DATA_NOTIFICATION_CLIENTS,
            PLATFORMS,
            async_setup_entry,
        )

        entry = MagicMock()
        entry.entry_id = "runtime_entry"
        entry.title = "Sinum"
        entry.data = {
            "host": "sinum-hub.local",
            CONF_AUTH_MODE: AUTH_MODE_TOKEN,
            CONF_API_TOKEN: "tok",
            "scan_interval": DEFAULT_SCAN_INTERVAL,
        }
        entry.options = {}
        entry.add_update_listener = MagicMock(return_value="update-listener")
        entry.async_on_unload = MagicMock()

        with (
            patch("custom_components.sinum.async_get_clientsession", return_value=MagicMock()),
            patch("custom_components.sinum.SinumClient") as MockClient,
            patch("custom_components.sinum.SinumCoordinator") as MockCoordinator,
            patch(
                "custom_components.sinum._start_realtime_bridge", new_callable=AsyncMock
            ) as mock_start_bridge,
            patch.object(
                hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock
            ) as mock_forward,
        ):
            client = MagicMock()
            client.login = AsyncMock()
            MockClient.return_value = client

            coordinator = MagicMock()
            coordinator.async_config_entry_first_refresh = AsyncMock()
            coordinator.async_add_listener = MagicMock(return_value="stale-cleanup-listener")
            coordinator.hub_info = {}
            coordinator.removed_ids = {}
            coordinator.mqtt_bridge = None
            MockCoordinator.return_value = coordinator

            result = await async_setup_entry(hass, entry)

        assert result is True
        assert entry.runtime_data is coordinator
        mock_forward.assert_awaited_once_with(entry, PLATFORMS)
        mock_start_bridge.assert_awaited_once_with(
            hass,
            entry,
            coordinator,
            {**entry.data, **entry.options},
        )
        assert hass.data[DOMAIN][DATA_COORDINATORS]["runtime_entry"] is coordinator
        assert hass.data[DOMAIN][DATA_NOTIFICATION_CLIENTS]["runtime_entry"] is client
        assert hass.services.has_service(DOMAIN, SERVICE_SEND_NOTIFICATION)
        assert hass.services.has_service(DOMAIN, SERVICE_UPDATE_SCHEDULE)
        assert hass.services.has_service(DOMAIN, SERVICE_UPLOAD_MQTT_BRIDGE)
        assert hass.services.has_service(DOMAIN, SERVICE_RUN_SCENE)
        entry.async_on_unload.assert_any_call("update-listener")
        entry.async_on_unload.assert_any_call("stale-cleanup-listener")

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
        from custom_components.sinum import async_setup_entry
        from custom_components.sinum.lifecycle import _MQTT_BRIDGES

        entry = MagicMock()
        entry.entry_id = "mqtt_entry"
        entry.data = {
            "host": "10.0.0.1",
            CONF_AUTH_MODE: AUTH_MODE_TOKEN,
            CONF_API_TOKEN: "tok",
            CONF_MQTT_ENABLED: True,
            "scan_interval": DEFAULT_SCAN_INTERVAL,
            CONF_WS_ENABLED: False,
        }
        entry.options = {CONF_MQTT_TOPIC_PREFIX: "sinum/hub-a"}

        with (
            patch("custom_components.sinum.async_get_clientsession", return_value=MagicMock()),
            patch("custom_components.sinum.SinumClient") as MockClient,
            patch("custom_components.sinum.SinumCoordinator") as MockCoordinator,
            patch("custom_components.sinum.lifecycle.SinumMqttBridge") as MockBridge,
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
        from custom_components.sinum import async_setup_entry
        from custom_components.sinum.lifecycle import _MQTT_BRIDGES

        entry = MagicMock()
        entry.entry_id = "no_mqtt_entry"
        entry.data = {
            "host": "10.0.0.1",
            CONF_AUTH_MODE: AUTH_MODE_TOKEN,
            CONF_API_TOKEN: "tok",
            CONF_MQTT_ENABLED: False,
            "scan_interval": DEFAULT_SCAN_INTERVAL,
            CONF_WS_ENABLED: False,
        }
        entry.options = {}

        with (
            patch("custom_components.sinum.async_get_clientsession", return_value=MagicMock()),
            patch("custom_components.sinum.SinumClient") as MockClient,
            patch("custom_components.sinum.SinumCoordinator") as MockCoordinator,
            patch("custom_components.sinum.lifecycle.SinumMqttBridge") as MockBridge,
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
        from custom_components.sinum import async_setup_entry
        from custom_components.sinum.lifecycle import _WS_BRIDGES

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
            patch("custom_components.sinum.lifecycle.SinumWebSocketBridge") as MockWsBridge,
            patch("custom_components.sinum.lifecycle.SinumMqttBridge") as MockMqttBridge,
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
        assert coordinator.ws_bridge is ws_bridge
        _WS_BRIDGES.pop("ws_entry", None)

    @pytest.mark.asyncio
    async def test_setup_entry_ws_bridge_start_failure_falls_back_to_mqtt(self, hass):
        """When WS bridge async_start returns False, setup succeeds via MQTT fallback."""
        from custom_components.sinum import async_setup_entry
        from custom_components.sinum.lifecycle import _WS_BRIDGES

        entry = MagicMock()
        entry.entry_id = "ws_fail_entry"
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
            patch("custom_components.sinum.lifecycle.SinumWebSocketBridge") as MockWsBridge,
            patch("custom_components.sinum.lifecycle.SinumMqttBridge"),
            patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock),
        ):
            client = MagicMock()
            client.login = AsyncMock()
            MockClient.return_value = client

            coordinator = MagicMock()
            coordinator.async_config_entry_first_refresh = AsyncMock()
            coordinator.client = client
            coordinator.mqtt_bridge = None
            MockCoordinator.return_value = coordinator

            ws_bridge = MagicMock()
            ws_bridge.async_start = AsyncMock(return_value=False)
            MockWsBridge.return_value = ws_bridge

            result = await async_setup_entry(hass, entry)

        assert result is True
        assert "ws_fail_entry" not in _WS_BRIDGES


class TestAsyncUnloadEntry:
    @pytest.mark.asyncio
    async def test_unload_entry_stops_mqtt_bridge(self, hass):
        from custom_components.sinum import async_unload_entry
        from custom_components.sinum.lifecycle import _MQTT_BRIDGES

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
    async def test_unload_entry_stops_ws_bridge(self, hass):
        from custom_components.sinum import async_unload_entry
        from custom_components.sinum.lifecycle import _WS_BRIDGES

        ws_bridge = MagicMock()
        ws_bridge.async_stop = AsyncMock()
        _WS_BRIDGES["ws_unload_test"] = ws_bridge

        entry = MagicMock()
        entry.entry_id = "ws_unload_test"

        with (
            patch.object(hass.config_entries, "async_unload_platforms", return_value=True),
            patch.object(hass.config_entries, "async_entries", return_value=[entry]),
        ):
            result = await async_unload_entry(hass, entry)

        assert result is True
        ws_bridge.async_stop.assert_awaited_once()
        assert "ws_unload_test" not in _WS_BRIDGES

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
            patch("custom_components.sinum.lifecycle.SinumMqttBridge"),
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
            "host": "10.0.0.1",
            "auth_mode": "token",
            "api_token": "tok-a",
            "scan_interval": 30,
        }
        entry_b = MagicMock()
        entry_b.entry_id = "hub_b"
        entry_b.title = "Sinum (Hub B)"
        entry_b.options = {}
        entry_b.data = {
            "host": "10.0.0.2",
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
            "host": "10.0.0.1",
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
            "host": "10.0.0.1",
            "auth_mode": "token",
            "api_token": "tok-a",
            "scan_interval": 30,
        }
        entry_b = MagicMock()
        entry_b.entry_id = "hub_b"
        entry_b.title = "Sinum (Hub B)"
        entry_b.options = {}
        entry_b.data = {
            "host": "10.0.0.2",
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


class TestRunSceneServiceRouting:
    """Tests for handle_run_scene service handler."""

    def _setup_entry(self) -> tuple:
        mock_client = MagicMock()
        mock_client.login = AsyncMock()
        mock_client.run_scene = AsyncMock(return_value=None)

        coordinator = MagicMock()
        coordinator.async_config_entry_first_refresh = AsyncMock()
        coordinator.client = mock_client

        entry = MagicMock()
        entry.entry_id = "hub_a"
        entry.options = {}
        entry.data = {
            "host": "10.0.0.1",
            "auth_mode": "token",
            "api_token": "tok",
            "scan_interval": 30,
        }
        return coordinator, mock_client, entry

    @pytest.mark.asyncio
    async def test_run_scene_calls_client(self, hass):
        from custom_components.sinum import async_setup_entry

        coordinator, mock_client, entry = self._setup_entry()

        with (
            patch("custom_components.sinum.SinumCoordinator", return_value=coordinator),
            patch("custom_components.sinum.SinumClient", return_value=mock_client),
            patch("custom_components.sinum.async_get_clientsession", return_value=MagicMock()),
            patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock),
        ):
            await async_setup_entry(hass, entry)

        await hass.services.async_call(
            DOMAIN,
            SERVICE_RUN_SCENE,
            {ATTR_RUN_SCENE_ID: 5},
            blocking=True,
        )

        mock_client.run_scene.assert_awaited_once_with(5)

    @pytest.mark.asyncio
    async def test_run_scene_accepts_string_id(self, hass):
        from custom_components.sinum import async_setup_entry

        coordinator, mock_client, entry = self._setup_entry()

        with (
            patch("custom_components.sinum.SinumCoordinator", return_value=coordinator),
            patch("custom_components.sinum.SinumClient", return_value=mock_client),
            patch("custom_components.sinum.async_get_clientsession", return_value=MagicMock()),
            patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock),
        ):
            await async_setup_entry(hass, entry)

        await hass.services.async_call(
            DOMAIN,
            SERVICE_RUN_SCENE,
            {ATTR_RUN_SCENE_ID: "3"},
            blocking=True,
        )

        mock_client.run_scene.assert_awaited_once_with(3)


class TestUploadMqttBridgeService:
    """Tests for handle_upload_mqtt_bridge service handler."""

    def _setup_entry(self):
        mock_client = MagicMock()
        mock_client.login = AsyncMock()
        mock_client.patch_scene_lua = AsyncMock(return_value=None)

        coordinator = MagicMock()
        coordinator.async_config_entry_first_refresh = AsyncMock()
        coordinator.client = mock_client
        coordinator.config_entry = MagicMock()
        coordinator.config_entry.options = {}
        coordinator.config_entry.data = {}

        entry = MagicMock()
        entry.entry_id = "hub_a"
        entry.options = {}
        entry.data = {
            "host": "10.0.0.1",
            "auth_mode": "token",
            "api_token": "tok",
            "scan_interval": 30,
        }
        return coordinator, mock_client, entry

    @pytest.mark.asyncio
    async def test_dry_run_does_not_call_patch(self, hass):
        from custom_components.sinum import async_setup_entry

        coordinator, mock_client, entry = self._setup_entry()

        with (
            patch("custom_components.sinum.SinumCoordinator", return_value=coordinator),
            patch("custom_components.sinum.SinumClient", return_value=mock_client),
            patch("custom_components.sinum.async_get_clientsession", return_value=MagicMock()),
            patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock),
        ):
            await async_setup_entry(hass, entry)

        await hass.services.async_call(
            DOMAIN,
            SERVICE_UPLOAD_MQTT_BRIDGE,
            {ATTR_MQTT_SCENE_ID: 1, ATTR_MQTT_CLIENT_ID: 2, ATTR_MQTT_DRY_RUN: True},
            blocking=True,
        )

        mock_client.patch_scene_lua.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_dry_run_uploads_lua(self, hass):
        from custom_components.sinum import async_setup_entry

        coordinator, mock_client, entry = self._setup_entry()

        with (
            patch("custom_components.sinum.SinumCoordinator", return_value=coordinator),
            patch("custom_components.sinum.SinumClient", return_value=mock_client),
            patch("custom_components.sinum.async_get_clientsession", return_value=MagicMock()),
            patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock),
        ):
            await async_setup_entry(hass, entry)

        await hass.services.async_call(
            DOMAIN,
            SERVICE_UPLOAD_MQTT_BRIDGE,
            {ATTR_MQTT_SCENE_ID: 1, ATTR_MQTT_CLIENT_ID: 2, ATTR_MQTT_DRY_RUN: False},
            blocking=True,
        )

        mock_client.patch_scene_lua.assert_awaited_once()
        scene_id_arg = mock_client.patch_scene_lua.call_args[0][0]
        assert scene_id_arg == 1


class TestNotificationServiceErrors:
    """Tests for error paths in handle_send_notification."""

    @pytest.mark.asyncio
    async def test_not_supported_raises_ha_error(self, hass):
        from custom_components.sinum import async_setup_entry
        from custom_components.sinum.api import SinumNotSupportedError

        mock_client = MagicMock()
        mock_client.login = AsyncMock()
        mock_client.send_notification = AsyncMock(
            side_effect=SinumNotSupportedError("not supported")
        )

        coordinator = MagicMock()
        coordinator.async_config_entry_first_refresh = AsyncMock()
        coordinator.client = mock_client

        entry = MagicMock()
        entry.entry_id = "hub_a"
        entry.options = {}
        entry.data = {
            "host": "10.0.0.1",
            "auth_mode": "token",
            "api_token": "tok",
            "scan_interval": 30,
        }

        with (
            patch("custom_components.sinum.SinumCoordinator", return_value=coordinator),
            patch("custom_components.sinum.SinumClient", return_value=mock_client),
            patch("custom_components.sinum.async_get_clientsession", return_value=MagicMock()),
            patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock),
        ):
            await async_setup_entry(hass, entry)

        with pytest.raises(HomeAssistantError, match="does not support push notifications"):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_SEND_NOTIFICATION,
                {ATTR_NOTIFICATION_TITLE: "T", ATTR_NOTIFICATION_MESSAGE: "M"},
                blocking=True,
            )


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


class TestStaleEntityCleanup:
    """Tests for stale device cleanup helpers."""

    def test_stale_uid_prefixes_empty_when_no_removed_ids(self):
        from custom_components.sinum.lifecycle import _stale_uid_prefixes

        result = _stale_uid_prefixes("entry1", {"wtp": frozenset(), "sbus": frozenset()})
        assert result == set()

    def test_stale_uid_prefixes_builds_correct_prefixes(self):
        from custom_components.sinum.lifecycle import _stale_uid_prefixes

        result = _stale_uid_prefixes("abc", {"wtp": frozenset({10, 20}), "sbus": frozenset({5})})
        assert "abc_wtp_10" in result
        assert "abc_wtp_20" in result
        assert "abc_sbus_5" in result
        assert len(result) == 3

    def test_is_stale_entity_matches_exact_uid(self):
        from custom_components.sinum.lifecycle import _is_stale_entity

        entity = MagicMock()
        entity.unique_id = "abc_wtp_10"
        assert _is_stale_entity(entity, {"abc_wtp_10"}) is True

    def test_is_stale_entity_matches_prefixed_uid(self):
        from custom_components.sinum.lifecycle import _is_stale_entity

        entity = MagicMock()
        entity.unique_id = "abc_wtp_10_temperature"
        assert _is_stale_entity(entity, {"abc_wtp_10"}) is True

    def test_is_stale_entity_does_not_match_partial_prefix(self):
        from custom_components.sinum.lifecycle import _is_stale_entity

        entity = MagicMock()
        entity.unique_id = "abc_wtp_100_temperature"
        assert _is_stale_entity(entity, {"abc_wtp_10"}) is False

    def test_is_stale_entity_no_match_for_different_bus(self):
        from custom_components.sinum.lifecycle import _is_stale_entity

        entity = MagicMock()
        entity.unique_id = "abc_sbus_10_state"
        assert _is_stale_entity(entity, {"abc_wtp_10"}) is False

    def test_is_stale_entity_returns_false_when_no_prefixes(self):
        from custom_components.sinum.lifecycle import _is_stale_entity

        entity = MagicMock()
        entity.unique_id = "abc_wtp_10"
        assert _is_stale_entity(entity, set()) is False

    @pytest.mark.asyncio
    async def test_cleanup_stale_entities_noop_when_no_removed(self, hass):
        from custom_components.sinum.lifecycle import (
            cleanup_stale_entities as _cleanup_stale_entities,
        )

        with patch("custom_components.sinum.lifecycle.er") as mock_er:
            await _cleanup_stale_entities(hass, "entry1", {"wtp": frozenset(), "sbus": frozenset()})
            mock_er.async_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_stale_entities_removes_matching_entities(self, hass):
        from custom_components.sinum.lifecycle import (
            cleanup_stale_entities as _cleanup_stale_entities,
        )

        stale_entity = MagicMock()
        stale_entity.unique_id = "e1_wtp_42_temperature"
        stale_entity.entity_id = "sensor.stale_device_temp"

        live_entity = MagicMock()
        live_entity.unique_id = "e1_wtp_99_temperature"
        live_entity.entity_id = "sensor.live_device_temp"

        mock_reg = MagicMock()
        mock_reg.entities.get_entries_for_config_entry_id.return_value = [stale_entity, live_entity]

        with patch("custom_components.sinum.lifecycle.er") as mock_er:
            mock_er.async_get.return_value = mock_reg
            await _cleanup_stale_entities(hass, "e1", {"wtp": frozenset({42})})

        mock_reg.async_remove.assert_called_once_with("sensor.stale_device_temp")

    @pytest.mark.asyncio
    async def test_cleanup_stale_entities_removes_exact_uid_match(self, hass):
        from custom_components.sinum.lifecycle import (
            cleanup_stale_entities as _cleanup_stale_entities,
        )

        entity = MagicMock()
        entity.unique_id = "e1_sbus_7"
        entity.entity_id = "switch.stale"

        mock_reg = MagicMock()
        mock_reg.entities.get_entries_for_config_entry_id.return_value = [entity]

        with (
            patch("custom_components.sinum.lifecycle.er") as mock_er,
            patch("custom_components.sinum.lifecycle.dr") as mock_dr,
        ):
            mock_er.async_get.return_value = mock_reg
            mock_dr.async_get.return_value = MagicMock(
                async_get_device=MagicMock(return_value=None)
            )
            await _cleanup_stale_entities(hass, "e1", {"sbus": frozenset({7})})

        mock_reg.async_remove.assert_called_once_with("switch.stale")

    @pytest.mark.asyncio
    async def test_stale_cleanup_callback_fires_when_removed_ids_present(self, hass):
        """_handle_stale_cleanup schedules cleanup task when removed_ids are non-empty."""
        from custom_components.sinum import async_setup_entry

        mock_client = MagicMock()
        mock_client.login = AsyncMock()

        coordinator = MagicMock()
        coordinator.async_config_entry_first_refresh = AsyncMock()
        coordinator.client = mock_client
        coordinator.last_update_success = True
        coordinator.removed_ids = {"wtp": frozenset([10])}

        entry = MagicMock()
        entry.entry_id = "stale_test"
        entry.options = {}
        entry.data = {
            "host": "10.0.0.1",
            "auth_mode": "token",
            "api_token": "tok",
            "scan_interval": 30,
        }

        with (
            patch("custom_components.sinum.SinumCoordinator", return_value=coordinator),
            patch("custom_components.sinum.SinumClient", return_value=mock_client),
            patch("custom_components.sinum.async_get_clientsession", return_value=MagicMock()),
            patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock),
        ):
            await async_setup_entry(hass, entry)

        # Capture and invoke the stale cleanup listener
        cleanup_callback = coordinator.async_add_listener.call_args[0][0]
        hass.async_create_task = MagicMock()
        cleanup_callback()

        hass.async_create_task.assert_called_once()


class TestRunSceneService:
    @pytest.mark.asyncio
    async def test_run_scene_triggers_hub_scene(self, hass):
        from custom_components.sinum import async_setup_entry

        mock_client = MagicMock()
        mock_client.login = AsyncMock()
        mock_client.run_scene = AsyncMock()

        coordinator = MagicMock()
        coordinator.async_config_entry_first_refresh = AsyncMock()
        coordinator.client = mock_client
        coordinator.hub_info = {"name": "Hub A"}
        coordinator.mqtt_bridge = None
        coordinator.data = {}

        entry = MagicMock()
        entry.entry_id = "hub_a"
        entry.title = "Sinum (Hub A)"
        entry.options = {}
        entry.data = {"host": "10.0.0.1", "auth_mode": "token", "api_token": "tok"}

        with (
            patch("custom_components.sinum.SinumCoordinator", return_value=coordinator),
            patch("custom_components.sinum.SinumClient", return_value=mock_client),
            patch("custom_components.sinum.async_get_clientsession", return_value=MagicMock()),
            patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock),
        ):
            await async_setup_entry(hass, entry)

        await hass.services.async_call(
            DOMAIN,
            SERVICE_RUN_SCENE,
            {ATTR_RUN_SCENE_ID: 7},
            blocking=True,
        )

        mock_client.run_scene.assert_awaited_once_with(7)

    @pytest.mark.asyncio
    async def test_run_scene_with_explicit_entry_id(self, hass):
        from custom_components.sinum import async_setup_entry

        mock_client = MagicMock()
        mock_client.login = AsyncMock()
        mock_client.run_scene = AsyncMock()

        coordinator = MagicMock()
        coordinator.async_config_entry_first_refresh = AsyncMock()
        coordinator.client = mock_client
        coordinator.hub_info = {"name": "Hub B"}
        coordinator.mqtt_bridge = None
        coordinator.data = {}

        entry = MagicMock()
        entry.entry_id = "hub_b"
        entry.title = "Sinum (Hub B)"
        entry.options = {}
        entry.data = {"host": "10.0.0.3", "auth_mode": "token", "api_token": "tok2"}

        with (
            patch("custom_components.sinum.SinumCoordinator", return_value=coordinator),
            patch("custom_components.sinum.SinumClient", return_value=mock_client),
            patch("custom_components.sinum.async_get_clientsession", return_value=MagicMock()),
            patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock),
        ):
            await async_setup_entry(hass, entry)

        await hass.services.async_call(
            DOMAIN,
            SERVICE_RUN_SCENE,
            {ATTR_RUN_SCENE_ID: 3, ATTR_ENTRY_ID: "hub_b"},
            blocking=True,
        )

        mock_client.run_scene.assert_awaited_once_with(3)


class TestMultiHubServiceRouting:
    """Multi-hub services must require entry_id and route to the correct hub."""

    def _two_hub_setup(self):
        client_a = MagicMock()
        client_a.login = AsyncMock()
        client_a.run_scene = AsyncMock(return_value=None)
        client_a.patch_scene_lua = AsyncMock(return_value=None)
        client_b = MagicMock()
        client_b.login = AsyncMock()
        client_b.run_scene = AsyncMock(return_value=None)
        client_b.patch_scene_lua = AsyncMock(return_value=None)

        coordinator_a = MagicMock()
        coordinator_a.async_config_entry_first_refresh = AsyncMock()
        coordinator_a.client = client_a
        coordinator_a.hub_info = {"name": "Hub A"}
        coordinator_a.mqtt_bridge = None
        coordinator_a.config_entry = MagicMock()
        coordinator_a.config_entry.options = {}
        coordinator_a.config_entry.data = {}
        coordinator_b = MagicMock()
        coordinator_b.async_config_entry_first_refresh = AsyncMock()
        coordinator_b.client = client_b
        coordinator_b.hub_info = {"name": "Hub B"}
        coordinator_b.mqtt_bridge = None
        coordinator_b.config_entry = MagicMock()
        coordinator_b.config_entry.options = {}
        coordinator_b.config_entry.data = {}

        entry_a = MagicMock()
        entry_a.entry_id = "hub_a"
        entry_a.title = "Sinum (Hub A)"
        entry_a.options = {}
        entry_a.data = {
            "host": "10.0.0.1",
            "auth_mode": "token",
            "api_token": "tok-a",
            "scan_interval": 30,
        }
        entry_b = MagicMock()
        entry_b.entry_id = "hub_b"
        entry_b.title = "Sinum (Hub B)"
        entry_b.options = {}
        entry_b.data = {
            "host": "10.0.0.2",
            "auth_mode": "token",
            "api_token": "tok-b",
            "scan_interval": 30,
        }
        return client_a, client_b, coordinator_a, coordinator_b, entry_a, entry_b

    @pytest.mark.asyncio
    async def test_run_scene_two_hubs_requires_entry_id(self, hass):
        from custom_components.sinum import async_setup_entry

        client_a, client_b, coordinator_a, coordinator_b, entry_a, entry_b = self._two_hub_setup()

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
                SERVICE_RUN_SCENE,
                {ATTR_RUN_SCENE_ID: 5},
                blocking=True,
            )

    @pytest.mark.asyncio
    async def test_upload_mqtt_bridge_two_hubs_routes_entry_id(self, hass):
        from custom_components.sinum import async_setup_entry

        client_a, client_b, coordinator_a, coordinator_b, entry_a, entry_b = self._two_hub_setup()

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

        await hass.services.async_call(
            DOMAIN,
            SERVICE_UPLOAD_MQTT_BRIDGE,
            {
                ATTR_ENTRY_ID: "hub_b",
                ATTR_MQTT_SCENE_ID: 1,
                ATTR_MQTT_CLIENT_ID: 2,
                ATTR_MQTT_DRY_RUN: False,
            },
            blocking=True,
        )

        client_a.patch_scene_lua.assert_not_awaited()
        client_b.patch_scene_lua.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unload_one_of_two_hubs_keeps_domain_services(self, hass):
        from custom_components.sinum import async_setup_entry, async_unload_entry

        client_a, client_b, coordinator_a, coordinator_b, entry_a, entry_b = self._two_hub_setup()

        with (
            patch("custom_components.sinum.SinumCoordinator") as mock_coordinator,
            patch("custom_components.sinum.SinumClient") as mock_client_cls,
            patch("custom_components.sinum.async_get_clientsession", return_value=MagicMock()),
            patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock),
            patch.object(
                hass.config_entries, "async_unload_platforms", new_callable=AsyncMock
            ) as unload,
        ):
            mock_client_cls.side_effect = [client_a, client_b]
            mock_coordinator.side_effect = [coordinator_a, coordinator_b]
            unload.return_value = True
            await async_setup_entry(hass, entry_a)
            await async_setup_entry(hass, entry_b)

        assert hass.services.has_service(DOMAIN, SERVICE_RUN_SCENE)
        await async_unload_entry(hass, entry_a)
        assert hass.services.has_service(DOMAIN, SERVICE_RUN_SCENE)


class TestServicesModuleImports:
    """Service helpers live in services.py but remain importable from the package."""

    def test_services_module_exports_handlers(self):
        from custom_components.sinum import services

        assert services.register_services is not None
        assert services.select_coordinator is not None
        assert services.merge_schedule is not None

    def test_init_reexports_service_schemas(self):
        from custom_components.sinum import NOTIFY_SCHEMA, RUN_SCENE_SCHEMA

        assert NOTIFY_SCHEMA is not None
        assert RUN_SCENE_SCHEMA is not None


class TestStaleDeviceRegistryCleanup:
    """Tests for device registry cleanup helpers."""

    def test_stale_identifiers_builds_correct_set(self):
        from custom_components.sinum.lifecycle import _stale_identifiers

        result = _stale_identifiers("abc", {"wtp": frozenset({10}), "sbus": frozenset({5})})
        assert ("sinum", "abc_wtp_10") in result
        assert ("sinum", "abc_sbus_5") in result
        assert len(result) == 2

    def test_stale_identifiers_empty_when_no_removed(self):
        from custom_components.sinum.lifecycle import _stale_identifiers

        result = _stale_identifiers("abc", {"wtp": frozenset(), "sbus": frozenset()})
        assert result == set()

    def test_remove_stale_devices_removes_found_device(self):
        from custom_components.sinum.lifecycle import _remove_stale_devices

        mock_device = MagicMock()
        mock_device.id = "dev-uuid-123"
        mock_device.name = "Old Relay"

        mock_reg = MagicMock()
        mock_reg.async_get_device.return_value = mock_device

        hass = MagicMock()
        with patch("custom_components.sinum.lifecycle.dr") as mock_dr:
            mock_dr.async_get.return_value = mock_reg
            _remove_stale_devices(hass, "e1", {("sinum", "e1_wtp_10")})

        mock_reg.async_remove_device.assert_called_once_with("dev-uuid-123")

    def test_remove_stale_devices_noop_when_device_not_found(self):
        from custom_components.sinum.lifecycle import _remove_stale_devices

        mock_reg = MagicMock()
        mock_reg.async_get_device.return_value = None

        hass = MagicMock()
        with patch("custom_components.sinum.lifecycle.dr") as mock_dr:
            mock_dr.async_get.return_value = mock_reg
            _remove_stale_devices(hass, "e1", {("sinum", "e1_wtp_10")})

        mock_reg.async_remove_device.assert_not_called()
