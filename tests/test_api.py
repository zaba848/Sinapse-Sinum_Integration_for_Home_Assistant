"""Tests for SinumClient."""

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
    SinumNotSupportedError,
)


@pytest.fixture
def session() -> MagicMock:
    return MagicMock(spec=aiohttp.ClientSession)


def make_response(status: int, data: object = None) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    _data = data if data is not None else {}
    resp.read = AsyncMock(return_value=_json.dumps(_data).encode())
    return resp


@asynccontextmanager
async def _fake_timeout(*args, **kwargs):
    yield


class TestDecodeEncodeTemperature:
    def test_decode(self):
        assert SinumClient.decode_temperature(220) == 22.0
        assert SinumClient.decode_temperature(185) == 18.5

    def test_encode(self):
        assert SinumClient.encode_temperature(22.0) == 220
        assert SinumClient.encode_temperature(18.5) == 185
        assert SinumClient.encode_temperature(21.15) == 212  # rounds


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_success(self, session):
        resp = make_response(200, {"data": {"session": "test-jwt-token", "refresh_token": "ref"}})
        session.post = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, username="user", password="pass")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.login()
        assert client._jwt == "test-jwt-token"
        assert client._refresh_token == "ref"

    @pytest.mark.asyncio
    async def test_login_noop_for_token(self, session):
        client = SinumClient("192.168.1.1", session, api_token="static-token")
        await client.login()  # should be no-op, session never called
        session.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, session):
        resp = make_response(401, {})
        session.post = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, username="user", password="wrong")
        with (
            patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout),
            pytest.raises(SinumAuthError),
        ):
            await client.login()

    @pytest.mark.asyncio
    async def test_login_connection_error(self, session):
        session.post = AsyncMock(side_effect=aiohttp.ClientError("unreachable"))
        client = SinumClient("192.168.1.1", session, username="user", password="pass")
        with (
            patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout),
            pytest.raises(SinumConnectionError),
        ):
            await client.login()


class TestTokenAuth:
    def test_token_header_has_bearer_prefix(self, session):
        client = SinumClient("192.168.1.1", session, api_token="my-secret-token")
        headers = client._headers()
        assert headers["Authorization"] == "Bearer my-secret-token"

    def test_jwt_header_has_bearer_prefix(self, session):
        client = SinumClient("192.168.1.1", session, username="u", password="p")
        client._jwt = "jwt-token"
        headers = client._headers()
        assert headers["Authorization"] == "Bearer jwt-token"

    def test_base_url_with_http(self, session):
        client = SinumClient("http://192.168.1.1", session, api_token="tok")
        assert client.base_url == "http://192.168.1.1"

    def test_base_url_without_scheme(self, session):
        client = SinumClient("192.168.1.1", session, api_token="tok")
        assert client.base_url == "http://192.168.1.1"

    def test_websocket_url_with_access_token_for_api_token(self, session):
        client = SinumClient("192.168.1.1", session, api_token="tok")
        url = client.websocket_url_with_access_token("/api/v1/ws")
        assert url == "ws://192.168.1.1/api/v1/ws?access_token=tok"

    def test_websocket_url_with_access_token_for_jwt(self, session):
        client = SinumClient("192.168.1.1", session, username="u", password="p")
        client._jwt = "jwt-token"
        url = client.websocket_url_with_access_token("/api/v1/ws")
        assert url == "ws://192.168.1.1/api/v1/ws?access_token=jwt-token"

    def test_websocket_url_without_token_leaves_query_unchanged(self, session):
        client = SinumClient("192.168.1.1", session, username="u", password="p")
        url = client.websocket_url_with_access_token("/api/v1/ws?foo=bar")
        assert url == "ws://192.168.1.1/api/v1/ws?foo=bar"

    def test_unwrap_data_returns_empty_dict_for_non_dict_body(self, session):
        client = SinumClient("192.168.1.1", session, api_token="tok")
        assert client._unwrap_data("not-a-dict") == {}


class TestApiRequests:
    @pytest.mark.asyncio
    async def test_get_energy_raises_on_404(self, session):
        resp = make_response(404, {})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")

        with (
            patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout),
            pytest.raises(SinumNotSupportedError, match="Endpoint not found"),
        ):
            await client.get_energy()

    @pytest.mark.asyncio
    async def test_run_scene_sends_trigger_payload(self, session):
        resp = make_response(204, {})
        resp.content_length = 0
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.run_scene(2)

        args = session.request.await_args.args
        kwargs = session.request.await_args.kwargs
        assert args[0] == "POST"
        assert args[1] == "http://192.168.1.1/api/v1/scenes/2/activate"
        assert kwargs.get("json") is None

    @pytest.mark.asyncio
    async def test_get_parent_devices_flattens_class_collections(self, session):
        resp = make_response(
            200,
            {
                "data": {
                    "wtp": [{"id": 1, "class": "wtp"}],
                    "sbus": [{"id": 2, "class": "sbus"}],
                    "metadata": {"ignored": True},
                }
            },
        )
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            devices = await client.get_parent_devices()

        assert devices == [{"id": 1, "class": "wtp"}, {"id": 2, "class": "sbus"}]

    @pytest.mark.asyncio
    async def test_get_parent_devices_accepts_list_response(self, session):
        resp = make_response(
            200,
            {"data": [{"id": 1, "class": "wtp_parent_device", "devices": []}]},
        )
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            devices = await client.get_parent_devices()

        assert devices == [{"id": 1, "class": "wtp_parent_device", "devices": []}]

    @pytest.mark.asyncio
    async def test_408_on_get_retries_once_and_raises_if_both_fail(self, session):
        """GET 408 retries once; if both attempts return 408, SinumConnectionError is raised."""
        resp = make_response(
            408, {"error": {"message": {"text": "Request timeout exceeded", "id": 7334}}}
        )
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")

        with (
            patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout),
            patch("custom_components.sinum.api.asyncio.sleep", AsyncMock()),
            pytest.raises(SinumConnectionError, match="Hub internal timeout"),
        ):
            await client.get_wtp_devices()

        assert session.request.call_count == 2

    @pytest.mark.asyncio
    async def test_408_on_patch_retries_once_and_succeeds(self, session):
        """PATCH 408 triggers one retry; if retry returns 200 the call succeeds."""
        first = make_response(408, {})
        second = make_response(200, {"data": {"id": 9, "mode": "heating"}})
        session.request = AsyncMock(side_effect=[first, second])
        client = SinumClient("192.168.1.1", session, api_token="tok")

        with (
            patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout),
            patch("custom_components.sinum.api.asyncio.sleep", AsyncMock()),
        ):
            result = await client.patch_virtual_device(9, {"mode": "heating"})

        assert result == {"id": 9, "mode": "heating"}
        assert session.request.call_count == 2

    @pytest.mark.asyncio
    async def test_408_on_patch_retry_also_408_raises_connection_error(self, session):
        """PATCH 408 is retried once; if retry is also 408, SinumConnectionError is raised."""
        resp = make_response(408, {})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")

        with (
            patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout),
            patch("custom_components.sinum.api.asyncio.sleep", AsyncMock()),
            pytest.raises(SinumConnectionError, match="Hub internal timeout"),
        ):
            await client.patch_virtual_device(9, {"mode": "heating"})

        assert session.request.call_count == 2

    @pytest.mark.asyncio
    async def test_408_on_patch_sleeps_before_retry(self, session):
        """PATCH 408 triggers asyncio.sleep(1) before retrying."""
        resp_408 = make_response(408, {})
        resp_ok = make_response(200, {"data": {"id": 9}})
        session.request = AsyncMock(side_effect=[resp_408, resp_ok])
        client = SinumClient("192.168.1.1", session, api_token="tok")
        mock_sleep = AsyncMock()

        with (
            patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout),
            patch("custom_components.sinum.api.asyncio.sleep", mock_sleep),
        ):
            await client.patch_virtual_device(9, {"mode": "off"})

        mock_sleep.assert_awaited_once_with(1)

    @pytest.mark.asyncio
    async def test_408_on_patch_sbus_also_retries(self, session):
        """SBUS PATCH also retries on 408."""
        first = make_response(408, {})
        second = make_response(200, {"data": {"id": 5, "state": True}})
        session.request = AsyncMock(side_effect=[first, second])
        client = SinumClient("192.168.1.1", session, api_token="tok")

        with (
            patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout),
            patch("custom_components.sinum.api.asyncio.sleep", AsyncMock()),
        ):
            result = await client.patch_sbus_device(5, {"state": True})

        assert result == {"id": 5, "state": True}
        assert session.request.call_count == 2


class TestHubInfoEndpoints:
    @pytest.mark.asyncio
    async def test_get_hub_info_returns_data(self, session):
        resp = make_response(200, {"data": {"name": "MyHub", "version": "1.2.3"}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_hub_info()
        assert result["name"] == "MyHub"

    @pytest.mark.asyncio
    async def test_get_rooms_returns_list(self, session):
        resp = make_response(200, {"data": [{"id": 1, "name": "Living room"}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_rooms()
        assert result == [{"id": 1, "name": "Living room"}]

    @pytest.mark.asyncio
    async def test_get_floors_returns_list(self, session):
        resp = make_response(200, {"data": [{"id": 1, "name": "Ground floor"}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_floors()
        assert result == [{"id": 1, "name": "Ground floor"}]

    @pytest.mark.asyncio
    async def test_get_weather_returns_data(self, session):
        resp = make_response(200, {"data": {"temperature": 185, "humidity": 650}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_weather()
        assert result["temperature"] == 185

    @pytest.mark.asyncio
    async def test_get_lua_hub_info_returns_dict(self, session):
        resp = make_response(200, {"data": {"ip": "10.0.0.1", "mac": "aa:bb:cc"}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_lua_hub_info()
        assert result["ip"] == "10.0.0.1"


class TestLoraAlarmModbus:
    @pytest.mark.asyncio
    async def test_get_lora_devices_returns_list(self, session):
        resp = make_response(200, {"data": [{"id": 7, "class": "lora", "type": "opening_sensor"}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_lora_devices()
        assert result[0]["id"] == 7

    @pytest.mark.asyncio
    async def test_patch_lora_device_sends_patch(self, session):
        resp = make_response(200, {"data": {"id": 7, "state": True}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.patch_lora_device(7, {"state": True})
        assert result["state"] is True
        args = session.request.await_args.args
        assert args[0] == "PATCH"
        assert "lora" in args[1]

    @pytest.mark.asyncio
    async def test_get_alarm_devices_404_raises_not_supported(self, session):
        resp = make_response(404, {})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with (
            patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout),
            pytest.raises(SinumNotSupportedError),
        ):
            await client.get_alarm_devices()

    @pytest.mark.asyncio
    async def test_patch_alarm_device_sends_patch(self, session):
        resp = make_response(200, {"data": {"id": 1, "arm": True}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.patch_alarm_device(1, {"arm": True})
        assert result["arm"] is True

    @pytest.mark.asyncio
    async def test_get_modbus_devices_returns_list(self, session):
        resp = make_response(200, {"data": [{"id": 10, "class": "modbus"}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_modbus_devices()
        assert result[0]["class"] == "modbus"

    @pytest.mark.asyncio
    async def test_get_modbus_device_returns_single(self, session):
        resp = make_response(200, {"data": {"id": 10, "class": "modbus", "power": 1200}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_modbus_device(10)
        assert result["power"] == 1200


class TestVideoEndpoints:
    @pytest.mark.asyncio
    async def test_get_video_devices_returns_list(self, session):
        resp = make_response(200, {"data": [{"id": 3, "class": "video", "type": "camera"}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_video_devices()
        assert result[0]["type"] == "camera"

    @pytest.mark.asyncio
    async def test_get_video_device_returns_single(self, session):
        resp = make_response(200, {"data": {"id": 3, "class": "video", "snapshot": "/snap"}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_video_device(3)
        assert result["snapshot"] == "/snap"

    @pytest.mark.asyncio
    async def test_get_video_snapshot_returns_bytes(self, session):
        import base64
        jpeg = b"\xff\xd8\xff"
        resp = make_response(200, {"data": {"payload": base64.b64encode(jpeg).decode()}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_video_snapshot(3)
        assert result == jpeg

    @pytest.mark.asyncio
    async def test_get_video_snapshot_404_raises_not_supported(self, session):
        resp = make_response(404, {})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with (
            patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout),
            pytest.raises(SinumNotSupportedError),
        ):
            await client.get_video_snapshot(3)

    @pytest.mark.asyncio
    async def test_post_video_stream_offer_sends_correct_payload(self, session):
        resp = make_response(200, {})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.post_video_stream_offer(7, "v=0\r\n", "sess-abc")
        _, kwargs = session.request.call_args
        body = kwargs["json"]
        assert body["type"] == "offer"
        assert body["data"]["session_id"] == "sess-abc"
        assert body["data"]["description"]["sdp"] == "v=0\r\n"
        assert body["data"]["description"]["ice_servers"] == []

    @pytest.mark.asyncio
    async def test_post_video_candidate_sends_correct_payload(self, session):
        from unittest.mock import MagicMock
        resp = make_response(200, {})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        candidate = MagicMock()
        candidate.candidate = "candidate:1 1 UDP 2122252543 192.168.1.1 50000 typ host"
        candidate.sdp_m_line_index = 0
        candidate.sdp_mid = "0"
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.post_video_candidate(7, "sess-abc", candidate)
        _, kwargs = session.request.call_args
        body = kwargs["json"]
        assert body["type"] == "candidate"
        assert body["data"]["session_id"] == "sess-abc"
        assert body["data"]["candidate"]["candidate"] == candidate.candidate
        assert body["data"]["candidate"]["sdp_m_line_index"] == 0

    @pytest.mark.asyncio
    async def test_post_video_candidate_none_sdp_m_line_index_defaults_to_zero(self, session):
        from unittest.mock import MagicMock
        resp = make_response(200, {})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        candidate = MagicMock()
        candidate.candidate = "candidate:1 1 UDP 2122252543 192.168.1.2 50001 typ host"
        candidate.sdp_m_line_index = None
        candidate.sdp_mid = ""
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.post_video_candidate(7, "sess-abc", candidate)
        _, kwargs = session.request.call_args
        body = kwargs["json"]
        assert body["data"]["candidate"]["sdp_m_line_index"] == 0


class TestSceneScheduleEndpoints:
    @pytest.mark.asyncio
    async def test_get_scenes_returns_list(self, session):
        resp = make_response(200, {"data": [{"id": 1, "name": "Night", "type": "code"}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_scenes()
        assert result[0]["name"] == "Night"

    @pytest.mark.asyncio
    async def test_get_scene_returns_single(self, session):
        resp = make_response(200, {"data": {"id": 5, "name": "Day", "code": "return 1"}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_scene(5)
        assert result["name"] == "Day"

    @pytest.mark.asyncio
    async def test_patch_scene_lua_sends_patch(self, session):
        resp = make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_scene_lua(5, "return 42")
        args = session.request.await_args.args
        assert args[0] == "PATCH"
        assert "5" in args[1]

    @pytest.mark.asyncio
    async def test_get_or_create_scene_returns_existing(self, session):
        resp = make_response(200, {"data": [{"id": 8, "name": "_ha_test"}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            scene_id = await client.get_or_create_scene("_ha_test")
        assert scene_id == 8

    @pytest.mark.asyncio
    async def test_get_schedules_returns_list(self, session):
        resp = make_response(200, {"data": [{"id": 1, "name": "Heating"}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_schedules()
        assert result[0]["name"] == "Heating"

    @pytest.mark.asyncio
    async def test_get_schedule_returns_single(self, session):
        resp = make_response(200, {"data": {"id": 3, "name": "Summer"}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_schedule(3)
        assert result["name"] == "Summer"

    @pytest.mark.asyncio
    async def test_patch_schedule_sends_data(self, session):
        resp = make_response(200, {"data": {"id": 3, "name": "Updated"}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.patch_schedule(3, {"name": "Updated"})
        assert result["name"] == "Updated"
        assert session.request.await_args.args[0] == "PATCH"

    @pytest.mark.asyncio
    async def test_get_variables_returns_list(self, session):
        resp = make_response(200, {"data": [{"id": 1, "name": "setpoint", "value": 220}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_variables()
        assert result[0]["name"] == "setpoint"

    @pytest.mark.asyncio
    async def test_get_automations_returns_list(self, session):
        resp = make_response(200, {"data": [{"id": 2, "name": "night_mode"}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_automations()
        assert result[0]["name"] == "night_mode"


class TestWtpEndpoints:
    @pytest.mark.asyncio
    async def test_get_wtp_device_returns_single(self, session):
        resp = make_response(200, {"data": {"id": 4, "class": "wtp", "temperature": 215}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_wtp_device(4)
        assert result["temperature"] == 215

    @pytest.mark.asyncio
    async def test_patch_wtp_device_sends_patch(self, session):
        resp = make_response(200, {"data": {"id": 4, "target_temperature": 220}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.patch_wtp_device(4, {"target_temperature": 220})
        assert result["target_temperature"] == 220
        assert session.request.await_args.args[0] == "PATCH"

    @pytest.mark.asyncio
    async def test_get_sbus_device_returns_single(self, session):
        resp = make_response(200, {"data": {"id": 11, "class": "sbus", "humidity": 550}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_sbus_device(11)
        assert result["humidity"] == 550

    @pytest.mark.asyncio
    async def test_get_virtual_device_returns_single(self, session):
        resp = make_response(200, {"data": {"id": 2, "class": "virtual", "type": "thermostat"}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_virtual_device(2)
        assert result["type"] == "thermostat"

    @pytest.mark.asyncio
    async def test_get_virtual_devices_returns_list(self, session):
        resp = make_response(200, {"data": [{"id": 1, "class": "virtual", "type": "thermostat"}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_virtual_devices()
        assert result[0]["type"] == "thermostat"

    @pytest.mark.asyncio
    async def test_get_sbus_devices_returns_list(self, session):
        resp = make_response(200, {"data": [{"id": 5, "class": "sbus", "type": "relay"}]})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.get_sbus_devices()
        assert result[0]["class"] == "sbus"
