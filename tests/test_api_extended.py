"""Extended tests for SinumClient API methods and auth flows."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.sinum.api import (
    SinumAuthError,
    SinumClient,
    SinumConnectionError,
)


@asynccontextmanager
async def _fake_timeout(*args, **kwargs):
    yield


def make_response(status: int, data: object, content_length: int = 100) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    resp.content_length = content_length
    resp.json = AsyncMock(return_value=data)
    return resp


@pytest.fixture
def session() -> MagicMock:
    return MagicMock(spec=aiohttp.ClientSession)


class TestLoginEdgeCases:
    @pytest.mark.asyncio
    async def test_login_raises_when_no_credentials(self, session):
        client = SinumClient("192.168.1.1", session)
        with pytest.raises(SinumAuthError, match="No credentials"):
            await client.login()

    @pytest.mark.asyncio
    async def test_login_non_200_non_401_raises_connection_error(self, session):
        resp = make_response(503, {})
        session.post = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, username="user", password="pass")
        with (
            patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout),
            pytest.raises(SinumConnectionError, match="Login failed"),
        ):
            await client.login()


class TestRefreshJwt:
    @pytest.mark.asyncio
    async def test_refresh_returns_false_when_no_refresh_token(self, session):
        client = SinumClient("192.168.1.1", session, username="u", password="p")
        result = await client._refresh_jwt()
        assert result is False

    @pytest.mark.asyncio
    async def test_refresh_success(self, session):
        resp = make_response(200, {"data": {"session": "new-jwt", "refresh_token": "new-ref"}})
        session.post = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, username="u", password="p")
        client._refresh_token = "old-ref"
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client._refresh_jwt()
        assert result is True
        assert client._jwt == "new-jwt"
        assert client._refresh_token == "new-ref"

    @pytest.mark.asyncio
    async def test_refresh_returns_false_on_non_200(self, session):
        resp = make_response(401, {})
        session.post = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, username="u", password="p")
        client._refresh_token = "old-ref"
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client._refresh_jwt()
        assert result is False

    @pytest.mark.asyncio
    async def test_refresh_returns_false_on_connection_error(self, session):
        session.post = AsyncMock(side_effect=aiohttp.ClientError("unreachable"))
        client = SinumClient("192.168.1.1", session, username="u", password="p")
        client._refresh_token = "old-ref"
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client._refresh_jwt()
        assert result is False

    @pytest.mark.asyncio
    async def test_refresh_returns_false_when_no_session_in_response(self, session):
        resp = make_response(200, {"data": {"other": "data"}})
        session.post = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, username="u", password="p")
        client._refresh_token = "old-ref"
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client._refresh_jwt()
        assert result is False


class TestRequestEdgeCases:
    @pytest.mark.asyncio
    async def test_request_auto_login_when_no_token(self, session):
        """_request calls login() automatically when no token or JWT."""
        login_resp = make_response(200, {"data": {"session": "jwt", "refresh_token": "ref"}})
        data_resp = make_response(200, {"data": [{"id": 1}]})
        session.post = AsyncMock(return_value=login_resp)
        session.request = AsyncMock(return_value=data_resp)
        client = SinumClient("192.168.1.1", session, username="u", password="p")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_virtual_devices()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_request_raises_connection_error_on_client_error(self, session):
        session.request = AsyncMock(side_effect=aiohttp.ClientError("timeout"))
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with (
            patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout),
            pytest.raises(SinumConnectionError, match="Request failed"),
        ):
            await client.get_virtual_devices()

    @pytest.mark.asyncio
    async def test_request_401_with_api_token_raises_auth_error(self, session):
        resp = make_response(401, {})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="bad-token")
        with (
            patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout),
            pytest.raises(SinumAuthError, match="API token rejected"),
        ):
            await client.get_virtual_devices()

    @pytest.mark.asyncio
    async def test_request_401_triggers_refresh_then_retries(self, session):
        """On 401 with JWT, refresh succeeds and request is retried."""
        auth_resp = make_response(401, {})
        refresh_resp = make_response(
            200, {"data": {"session": "new-jwt", "refresh_token": "new-ref"}}
        )
        ok_resp = make_response(200, {"data": [{"id": 1}]})

        request_responses = [auth_resp, ok_resp]
        session.request = AsyncMock(side_effect=request_responses)
        session.post = AsyncMock(return_value=refresh_resp)

        client = SinumClient("192.168.1.1", session, username="u", password="p")
        client._jwt = "old-jwt"
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_virtual_devices()
        assert result == [{"id": 1}]

    @pytest.mark.asyncio
    async def test_request_304_returns_empty_dict(self, session):
        resp = make_response(304, {})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.patch_virtual_device(1, {"state": True})
        assert result == {}

    @pytest.mark.asyncio
    async def test_request_204_returns_empty_dict(self, session):
        resp = make_response(204, {}, content_length=0)
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.run_scene(5)
        assert result is None  # run_scene returns None


class TestApiMethods:
    @pytest.mark.asyncio
    async def test_get_hub_info(self, session):
        resp = make_response(200, {"data": {"version": "1.24.0"}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_hub_info()
        assert result["version"] == "1.24.0"

    @pytest.mark.asyncio
    async def test_get_rooms(self, session):
        resp = make_response(200, {"data": [{"id": 1, "name": "Living room"}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_rooms()
        assert len(result) == 1
        assert result[0]["name"] == "Living room"

    @pytest.mark.asyncio
    async def test_get_rooms_returns_empty_list_when_not_list(self, session):
        resp = make_response(200, {"data": None})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_rooms()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_floors(self, session):
        resp = make_response(200, {"data": [{"id": 1, "name": "Ground Floor"}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_floors()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_virtual_devices(self, session):
        resp = make_response(200, {"data": [{"id": 1, "type": "thermostat"}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_virtual_devices()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_virtual_devices_accepts_items_wrapper(self, session):
        resp = make_response(200, {"data": {"items": [{"id": 1, "type": "thermostat"}]}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_virtual_devices()
        assert result == [{"id": 1, "type": "thermostat"}]

    @pytest.mark.asyncio
    async def test_get_virtual_devices_accepts_id_map(self, session):
        resp = make_response(
            200,
            {"data": {"10": {"id": 10, "type": "thermostat"}, "metadata": {"ignored": True}}},
        )
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_virtual_devices()
        assert result == [{"id": 10, "type": "thermostat"}]

    @pytest.mark.asyncio
    async def test_get_virtual_device(self, session):
        resp = make_response(200, {"data": {"id": 5, "type": "thermostat", "state": True}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_virtual_device(5)
        assert result["id"] == 5

    @pytest.mark.asyncio
    async def test_patch_virtual_device(self, session):
        resp = make_response(200, {"data": {"id": 5, "state": True}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.patch_virtual_device(5, {"state": True})
        assert result["state"] is True
        _, kwargs = session.request.await_args
        assert kwargs["json"] == {"state": True}

    @pytest.mark.asyncio
    async def test_get_wtp_devices(self, session):
        resp = make_response(200, {"data": [{"id": 1, "type": "relay"}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_wtp_devices()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_wtp_devices_accepts_bus_wrapper(self, session):
        resp = make_response(200, {"data": {"wtp": [{"id": 4, "type": "relay"}]}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_wtp_devices()
        assert result == [{"id": 4, "type": "relay"}]

    @pytest.mark.asyncio
    async def test_get_wtp_device(self, session):
        resp = make_response(200, {"data": {"id": 3, "type": "relay"}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_wtp_device(3)
        assert result["id"] == 3

    @pytest.mark.asyncio
    async def test_patch_wtp_device(self, session):
        resp = make_response(200, {"data": {"id": 3, "state": False}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.patch_wtp_device(3, {"state": False})
        assert result["state"] is False

    @pytest.mark.asyncio
    async def test_get_sbus_devices(self, session):
        resp = make_response(200, {"data": [{"id": 10, "type": "relay"}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_sbus_devices()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_sbus_device(self, session):
        resp = make_response(200, {"data": {"id": 10, "type": "valve_pump"}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_sbus_device(10)
        assert result["id"] == 10

    @pytest.mark.asyncio
    async def test_patch_sbus_device(self, session):
        resp = make_response(200, {"data": {"id": 10, "state": True}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.patch_sbus_device(10, {"state": True})
        assert result["state"] is True

    @pytest.mark.asyncio
    async def test_get_scenes(self, session):
        resp = make_response(200, {"data": [{"id": 1, "name": "Evening"}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_scenes()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_scene_lua_uses_documented_endpoint(self, session):
        resp = make_response(200, {"data": {"code": "return true"}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_scene_lua(7)
        assert result["code"] == "return true"
        assert session.request.await_args.args[1].endswith("/api/v1/scenes/7/lua")

    @pytest.mark.asyncio
    async def test_get_automations(self, session):
        resp = make_response(200, {"data": [{"id": 2, "name": "Night", "enabled": True}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_automations()
        assert result[0]["name"] == "Night"
        assert session.request.await_args.args[1].endswith("/api/v1/automations")

    @pytest.mark.asyncio
    async def test_get_automation_schema_uses_documented_endpoint(self, session):
        resp = make_response(200, {"data": {"fields": []}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_automation_schema(9)
        assert result == {"fields": []}
        assert session.request.await_args.args[1].endswith("/api/v1/automations/9/schema")

    @pytest.mark.asyncio
    async def test_get_variables(self, session):
        resp = make_response(200, {"data": [{"id": 1, "name": "Var1", "value": 42}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_variables()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_set_variable(self, session):
        resp = make_response(200, {"data": {"id": 1, "value": 100}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.set_variable(1, 100)
        assert result["value"] == 100

    @pytest.mark.asyncio
    async def test_get_schedules(self, session):
        resp = make_response(200, {"data": [{"id": 1, "name": "Morning"}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_schedules()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_patch_schedule_uses_documented_endpoint(self, session):
        resp = make_response(200, {"data": {"id": 1, "name": "Morning"}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.patch_schedule(1, {"name": "Morning"})
        assert result["name"] == "Morning"
        assert session.request.await_args.args[:2] == (
            "PATCH",
            "http://192.168.1.1/api/v1/schedules/1",
        )
        assert session.request.await_args.kwargs["json"] == {"name": "Morning"}

    @pytest.mark.asyncio
    async def test_get_alarm_devices(self, session):
        resp = make_response(200, {"data": [{"id": 1, "type": "alarm"}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_alarm_devices()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_alarm_device(self, session):
        resp = make_response(200, {"data": {"id": 5, "type": "alarm"}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_alarm_device(5)
        assert result["id"] == 5

    @pytest.mark.asyncio
    async def test_patch_alarm_device(self, session):
        resp = make_response(200, {"data": {"id": 5, "armed": True}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.patch_alarm_device(5, {"armed": True})
        assert result["armed"] is True

    @pytest.mark.asyncio
    async def test_send_notification(self, session):
        resp = make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.send_notification("Title", "Body")
        _, kwargs = session.request.await_args
        assert kwargs["json"] == {"title": "Title", "message": "Body"}

    @pytest.mark.asyncio
    async def test_get_weather(self, session):
        resp = make_response(200, {"data": {"temperature": 220, "humidity": 60}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_weather()
        assert result["temperature"] == 220

    @pytest.mark.asyncio
    async def test_get_energy(self, session):
        resp = make_response(200, {"data": {"total_kwh": 150.5}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_energy()
        assert result["total_kwh"] == 150.5

    @pytest.mark.asyncio
    async def test_get_energy_center_flow_monitor_uses_documented_endpoint(self, session):
        resp = make_response(200, {"data": {"power": 123}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_energy_center_flow_monitor()
        assert result["power"] == 123
        assert session.request.await_args.args[1].endswith("/api/v1/energy-center/flow-monitor")

    @pytest.mark.asyncio
    async def test_get_energy_center_summary_allows_partial_availability(self, session):
        client = SinumClient("192.168.1.1", session, api_token="tok")
        client.get_energy_center_associations = AsyncMock(return_value={"items": []})
        client.get_energy_center_flow_monitor = AsyncMock(
            side_effect=SinumConnectionError("missing")
        )
        client.get_energy_center_prices = AsyncMock(return_value={"tariff": "flat"})
        client.get_energy_center_prices_settings = AsyncMock(
            side_effect=SinumConnectionError("missing")
        )
        client.get_energy_center_prices_sources = AsyncMock(return_value=[])
        client.get_energy_center_storage = AsyncMock(side_effect=SinumConnectionError("missing"))
        client.get_energy_center_consumption = AsyncMock(return_value={"value": 10})
        client.get_energy_center_production = AsyncMock(return_value={"value": 3})

        summary = await client.get_energy_center_summary()

        assert summary["available_endpoints"] == [
            "associations",
            "prices",
            "prices_sources",
            "consumption",
            "production",
        ]
        assert "flow_monitor" in summary["missing_endpoints"]

    @pytest.mark.asyncio
    async def test_get_energy_center_summary_raises_when_all_missing(self, session):
        client = SinumClient("192.168.1.1", session, api_token="tok")
        missing = AsyncMock(side_effect=SinumConnectionError("missing"))
        client.get_energy_center_associations = missing
        client.get_energy_center_flow_monitor = missing
        client.get_energy_center_prices = missing
        client.get_energy_center_prices_settings = missing
        client.get_energy_center_prices_sources = missing
        client.get_energy_center_storage = missing
        client.get_energy_center_consumption = missing
        client.get_energy_center_production = missing

        with pytest.raises(SinumConnectionError, match="Energy Center"):
            await client.get_energy_center_summary()

    @pytest.mark.asyncio
    async def test_get_lua_hub_info(self, session):
        resp = make_response(200, {"data": {"wifi_signal": -60, "ssid": "HomeNetwork"}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_lua_hub_info()
        assert result["ssid"] == "HomeNetwork"

    @pytest.mark.asyncio
    async def test_test_connection_calls_get_hub_info(self, session):
        resp = make_response(200, {"data": {"version": "1.0"}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.test_connection()
        session.request.assert_awaited_once()


class TestApiGaps:
    """Fill remaining api.py coverage gaps."""

    @pytest.mark.asyncio
    async def test_request_422_json_parse_error_uses_status_fallback(self, session):
        """422 response where json() raises → details falls back to 'status 422'."""
        resp = MagicMock()
        resp.status = 422
        resp.json = AsyncMock(side_effect=Exception("bad json"))
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with (
            patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout),
            pytest.raises(SinumConnectionError, match="Validation error"),
        ):
            await client._request("PATCH", "/api/v1/devices/virtual/1", json={"state": "on"})

    @pytest.mark.asyncio
    async def test_get_parent_devices_non_dict_result_returns_empty(self, session):
        """get_parent_devices: non-dict API result → empty list (line 243)."""
        resp = make_response(200, {"data": "not_a_dict"})  # non-dict data → empty list
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_parent_devices()
        assert result == []

    @pytest.mark.asyncio
    async def test_patch_alarm_device(self, session):
        """patch_alarm_device sends PATCH and returns parsed response (line 327)."""
        resp = make_response(200, {"data": {"id": 1, "state": "armed"}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.patch_alarm_device(1, {"command": "arm_away"})
        assert result["id"] == 1

    @pytest.mark.asyncio
    async def test_command_alarm_device(self, session):
        """command_alarm_device sends POST (lines 329-337)."""
        resp = make_response(204, {}, content_length=0)
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.command_alarm_device(1, "arm_away", {})
        session.request.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_lora_devices(self, session):
        """get_lora_devices returns list on success (line 340)."""
        resp = make_response(
            200, {"data": [{"id": 1, "class": "lora", "type": "temperature_sensor"}]}
        )
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_lora_devices()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_lora_device(self, session):
        """get_lora_device fetches single device (line 343)."""
        resp = make_response(200, {"data": {"id": 5, "class": "lora"}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_lora_device(5)
        assert result["id"] == 5

    @pytest.mark.asyncio
    async def test_patch_lora_device(self, session):
        """patch_lora_device sends PATCH (line 346)."""
        resp = make_response(200, {"data": {"id": 5, "state": True}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.patch_lora_device(5, {"state": True})
        assert result["id"] == 5
