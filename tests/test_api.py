"""Tests for SinumClient."""
from __future__ import annotations

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
    resp.json = AsyncMock(return_value=data)
    return resp


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
        resp = make_response(200, {"session": "test-jwt-token"})
        session.post = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=resp),
            __aexit__=AsyncMock(return_value=False),
        ))
        client = SinumClient("192.168.1.1", session, username="user", password="pass")
        # patch asyncio.timeout
        with patch("custom_components.sinum.api.asyncio.timeout"):
            await client.login()
        assert client._jwt == "test-jwt-token"

    @pytest.mark.asyncio
    async def test_login_noop_for_token(self, session):
        client = SinumClient("192.168.1.1", session, api_token="static-token")
        await client.login()  # should be no-op, session never called
        session.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, session):
        resp = make_response(401, {})
        session.post = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=resp),
            __aexit__=AsyncMock(return_value=False),
        ))
        client = SinumClient("192.168.1.1", session, username="user", password="wrong")
        with patch("custom_components.sinum.api.asyncio.timeout"):
            with pytest.raises(SinumAuthError):
                await client.login()

    @pytest.mark.asyncio
    async def test_login_connection_error(self, session):
        session.post = MagicMock(side_effect=aiohttp.ClientError("unreachable"))
        client = SinumClient("192.168.1.1", session, username="user", password="pass")
        with patch("custom_components.sinum.api.asyncio.timeout"):
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
