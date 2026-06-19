"""Tests for SinumClient."""
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


@pytest.fixture
def session() -> MagicMock:
    return MagicMock(spec=aiohttp.ClientSession)


def make_response(status: int, data: object) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    resp.content_length = 100
    resp.json = AsyncMock(return_value=data)
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
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            with pytest.raises(SinumAuthError):
                await client.login()

    @pytest.mark.asyncio
    async def test_login_connection_error(self, session):
        session.post = AsyncMock(side_effect=aiohttp.ClientError("unreachable"))
        client = SinumClient("192.168.1.1", session, username="user", password="pass")
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            with pytest.raises(SinumConnectionError):
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


class TestApiRequests:
    @pytest.mark.asyncio
    async def test_get_energy_raises_on_404(self, session):
        resp = make_response(404, {})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            with pytest.raises(SinumConnectionError, match="API error 404"):
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
    async def test_408_raises_connection_error(self, session):
        """Hub-side bus timeout (HTTP 408) raises SinumConnectionError for retry."""
        resp = make_response(408, {"error": {"message": {"text": "Request timeout exceeded", "id": 7334}}})
        session.request = AsyncMock(return_value=resp)
        client = SinumClient("192.168.1.1", session, api_token="tok")

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            with pytest.raises(SinumConnectionError, match="Hub internal timeout"):
                await client.get_wtp_devices()
