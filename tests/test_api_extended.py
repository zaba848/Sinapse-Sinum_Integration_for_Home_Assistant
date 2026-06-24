"""Extended tests for SinumClient API methods and auth flows."""

from __future__ import annotations

import json as _json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.sinum.api import (
    SinumAuthError,
    SinumClient,
    SinumConnectionError,
    _list_result,
)


@asynccontextmanager
async def _fake_timeout(*args, **kwargs):
    yield


def make_response(status: int, data: object = None, content_length: int = 100) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    _data = data if data is not None else {}
    resp.read = AsyncMock(return_value=_json.dumps(_data).encode())
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

    @pytest.mark.asyncio
    async def test_refresh_keeps_existing_refresh_token_when_missing_in_response(self, session):
        """Regression: some firmware returns only new JWT without refresh token."""
        resp = make_response(200, {"data": {"session": "new-jwt"}})
        session.post = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, username="u", password="p")
        client._refresh_token = "old-ref"
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client._refresh_jwt()
        assert result is True
        assert client._jwt == "new-jwt"
        assert client._refresh_token == "old-ref"


class TestFirmwareResponseContracts:
    def test_list_result_accepts_nested_devices_wrapper(self):
        """Firmware variant: payload groups lists by bus inside 'devices'."""
        payload = {
            "devices": {
                "wtp": [{"id": 1, "type": "temperature_sensor"}],
                "sbus": [{"id": 2, "type": "relay"}],
                "meta": {"ignored": True},
            }
        }
        assert _list_result(payload) == [
            {"id": 1, "type": "temperature_sensor"},
            {"id": 2, "type": "relay"},
        ]

    def test_list_result_accepts_results_wrapper_with_mixed_values(self):
        """Firmware variant: endpoint returns mixed map under 'results'."""
        payload = {
            "results": {
                "10": {"id": 10, "type": "thermostat"},
                "status": "ok",
                "nested": [{"id": 11, "type": "button"}],
            }
        }
        assert _list_result(payload) == [
            {"id": 10, "type": "thermostat"},
            {"id": 11, "type": "button"},
        ]


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
        """422 response where body is not JSON → details falls back to 'status 422'."""
        resp = MagicMock()
        resp.status = 422
        resp.read = AsyncMock(return_value=b"not valid json{{{{")
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


class TestReadJsonErrorHandling:
    """Tests for _read_json helper: empty body, non-JSON, and body-read failure."""

    @pytest.mark.asyncio
    async def test_empty_body_returns_empty_dict(self, session):
        """204 or empty body → returns {} without raising."""
        resp = MagicMock()
        resp.status = 200
        resp.read = AsyncMock(return_value=b"")
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_hub_info()
        assert result == {}

    @pytest.mark.asyncio
    async def test_non_json_body_raises_connection_error(self, session):
        """HTML or non-JSON response → SinumConnectionError with body excerpt."""
        resp = MagicMock()
        resp.status = 200
        resp.read = AsyncMock(return_value=b"<html>Service Unavailable</html>")
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with (
            patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout),
            pytest.raises(SinumConnectionError, match="Non-JSON response"),
        ):
            await client.get_hub_info()

    @pytest.mark.asyncio
    async def test_body_read_failure_raises_connection_error(self, session):
        """If body read itself raises ClientError → SinumConnectionError."""
        resp = MagicMock()
        resp.status = 200
        resp.read = AsyncMock(side_effect=aiohttp.ClientPayloadError("truncated"))
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with (
            patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout),
            pytest.raises(SinumConnectionError, match="Failed to read response"),
        ):
            await client.get_hub_info()

    @pytest.mark.asyncio
    async def test_valid_json_without_data_envelope_returned_as_is(self, session):
        """JSON without 'data' envelope → returned directly (not wrapped)."""
        resp = MagicMock()
        resp.status = 200
        resp.read = AsyncMock(return_value=_json.dumps({"name": "hub"}).encode())
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_hub_info()
        assert result == {"name": "hub"}

    @pytest.mark.asyncio
    async def test_refresh_jwt_returns_false_on_bad_json(self, session):
        """If token-refresh endpoint returns non-JSON, _refresh_jwt returns False instead of raising."""
        resp_refresh = MagicMock()
        resp_refresh.status = 200
        resp_refresh.read = AsyncMock(return_value=b"not-json")
        session.post = AsyncMock(return_value=resp_refresh)
        client = SinumClient("192.168.1.1", session, username="u", password="p")
        client._refresh_token = "old-token"
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client._refresh_jwt()
        assert result is False


class TestLoginStaticToken:
    """Line 111: login() returns immediately when api_token is set."""

    @pytest.mark.asyncio
    async def test_login_noop_with_static_token(self, session):
        client = SinumClient("192.168.1.1", session, api_token="static-tok")
        # login() should not call session.post at all
        session.post = AsyncMock()
        await client.login()
        session.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_read_json_body_raises_connection_error_on_client_error(self, session):
        """Line 70: resp.read() raises ClientPayloadError → SinumConnectionError."""
        resp = MagicMock()
        resp.status = 200
        resp.read = AsyncMock(side_effect=aiohttp.ClientPayloadError("truncated payload"))
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with (
            patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout),
            pytest.raises(SinumConnectionError, match="Failed to read response"),
        ):
            await client.get_hub_info()

    @pytest.mark.asyncio
    async def test_raise_for_422_falls_back_to_status_when_body_unreadable(self, session):
        """Lines 288-289: _raise_for_422 uses status fallback when _read_json raises."""
        bad_resp = MagicMock()
        bad_resp.status = 422
        bad_resp.read = AsyncMock(return_value=b"not-json")
        session.request = AsyncMock(return_value=bad_resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with (
            patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout),
            pytest.raises(SinumConnectionError, match="Validation error"),
        ):
            await client.get_hub_info()


class TestSceneApiMethods:
    """Lines 392-444: scene management endpoint coverage."""

    @pytest.mark.asyncio
    async def test_get_scene_returns_empty_dict_for_non_dict_result(self, session):
        """get_scene → fallback {} when result is not a dict."""
        resp = make_response(200, [{"id": 1}])  # list, not dict
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_scene(1)
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_scene_lua_returns_empty_dict_for_non_dict_result(self, session):
        resp = make_response(200, [])  # list
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_scene_lua(5)
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_scene_lua_extensions(self, session):
        resp = make_response(200, {"data": [{"id": 1, "lua": "-- ext"}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_scene_lua_extensions(5)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_scene_schema_returns_empty_dict_for_non_dict_result(self, session):
        resp = make_response(200, [])
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_scene_schema(3)
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_scene_logs(self, session):
        resp = make_response(200, {"data": [{"ts": "2026-01-01", "msg": "ok"}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_scene_logs(3)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_create_scene_returns_id(self, session):
        resp = make_response(200, {"data": {"id": 42, "name": "test"}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            scene_id = await client.create_scene("test", "-- lua")
        assert scene_id == 42

    @pytest.mark.asyncio
    async def test_create_scene_raises_on_missing_id(self, session):
        resp = make_response(200, {"data": {"name": "test"}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with (
            patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout),
            pytest.raises(SinumConnectionError, match="Scene creation failed"),
        ):
            await client.create_scene("test", "-- lua")

    @pytest.mark.asyncio
    async def test_patch_scene_lua(self, session):
        resp = make_response(200, {})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_scene_lua(7, "return true")
        session.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_scene(self, session):
        resp = make_response(204)
        resp.read = AsyncMock(return_value=b"")
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.delete_scene(7)
        session.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_scene_by_name_returns_none_when_missing(self, session):
        resp = make_response(200, {"data": [{"id": 1, "name": "other"}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.find_scene_by_name("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_find_scene_by_name_returns_id_when_found(self, session):
        resp = make_response(200, {"data": [{"id": 9, "name": "my-scene"}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.find_scene_by_name("my-scene")
        assert result == 9

    @pytest.mark.asyncio
    async def test_get_or_create_scene_creates_when_not_found(self, session):
        """get_or_create_scene calls create_scene when find returns None."""
        resp_list = make_response(200, {"data": []})
        resp_create = make_response(200, {"data": {"id": 11, "name": "new-scene"}})
        session.request = AsyncMock(side_effect=[resp_list, resp_create])
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            scene_id = await client.get_or_create_scene("new-scene")
        assert scene_id == 11

    @pytest.mark.asyncio
    async def test_get_or_create_scene_returns_existing(self, session):
        resp = make_response(200, {"data": [{"id": 5, "name": "existing"}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            scene_id = await client.get_or_create_scene("existing")
        assert scene_id == 5


class TestAutomationApiMethods:
    """Lines 453-491: automation + alarm command endpoint coverage."""

    @pytest.mark.asyncio
    async def test_get_automation_returns_empty_dict_for_non_dict(self, session):
        resp = make_response(200, [])
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_automation(1)
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_automation_lua_returns_empty_dict_for_non_dict(self, session):
        resp = make_response(200, [])
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_automation_lua(1)
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_automation_lua_extensions(self, session):
        resp = make_response(200, {"data": [{"id": 1}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_automation_lua_extensions(1)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_automation_logs(self, session):
        resp = make_response(200, {"data": [{"ts": "2026-01-01"}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_automation_logs(2)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_command_alarm_device(self, session):
        resp = make_response(200, {})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.command_alarm_device(3, "arm", {"mode": "full"})
        session.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_lora_devices(self, session):
        resp = make_response(200, {"data": [{"id": 1, "type": "opening_sensor"}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_lora_devices()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_lora_device(self, session):
        resp = make_response(200, {"data": {"id": 1}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_lora_device(1)
        assert result == {"id": 1}

    @pytest.mark.asyncio
    async def test_patch_lora_device(self, session):
        resp = make_response(200, {"data": {"id": 1, "state": "open"}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.patch_lora_device(1, {"state": "open"})
        assert result == {"id": 1, "state": "open"}


class TestEnergyCenterEndpoints:
    """Lines 547-576: individual energy center getter coverage."""

    @pytest.fixture
    def client_ok(self, session):
        """Client with api_token, session returns a generic 200 with dict result."""
        resp = make_response(200, {"data": {"value": 42}})
        session.request = AsyncMock(return_value=resp)
        return SinumClient("192.168.1.1", session, api_token="tok")

    @pytest.mark.asyncio
    async def test_get_energy_center_associations(self, session, client_ok):
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client_ok.get_energy_center_associations()
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_energy_center_prices(self, session, client_ok):
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client_ok.get_energy_center_prices()
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_energy_center_prices_settings(self, session, client_ok):
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client_ok.get_energy_center_prices_settings()
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_energy_center_prices_sources(self, session, client_ok):
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client_ok.get_energy_center_prices_sources()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_energy_center_storage(self, session, client_ok):
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client_ok.get_energy_center_storage()
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_energy_center_consumption(self, session, client_ok):
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client_ok.get_energy_center_consumption()
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_energy_center_production(self, session, client_ok):
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client_ok.get_energy_center_production()
        assert isinstance(result, dict)


class TestHelperFunctions:
    """Lines 70, 111, 490-491: helper and _list_result edge-case coverage."""

    def test_dict_list_returns_empty_for_non_list_input(self):
        """Line 70: _dict_list(non-list) → []."""
        from custom_components.sinum.api import _dict_list

        assert _dict_list("not-a-list") == []
        assert _dict_list(None) == []
        assert _dict_list(42) == []

    def test_list_result_single_id_dict_wrapped_in_list(self):
        """Line 111: _list_result({'id': 1, ...}) → [{'id': 1, ...}]."""
        from custom_components.sinum.api import _list_result

        device = {"id": 1, "type": "flood_sensor"}
        result = _list_result(device)
        assert result == [device]

    @pytest.mark.asyncio
    async def test_get_schedule_returns_empty_dict_for_non_dict_result(self, session):
        """Lines 490-491: get_schedule fallback {} when result is not a dict."""
        resp = make_response(200, [{"id": 5}])  # list, not dict
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_schedule(5)
        assert result == {}

    @pytest.mark.asyncio
    async def test_patch_schedule_returns_empty_dict_for_non_dict_result(self, session):
        """Lines 490-491: patch_schedule fallback {} when result is not a dict."""
        resp = make_response(200, [])
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.patch_schedule(5, {"active": True})
        assert result == {}
