"""Protocol contract tests — verify exact HTTP URLs and payloads for each bus type.

These tests are different from coverage tests: they assert *what* gets sent over the
wire for every device command, ensuring the integration correctly talks to the Sinum API.

Bus types covered:
  - Virtual (relay, wicket, dimmer, blind, gate)
  - WTP (relay, dimmer, blind, climate fan-coil)
  - SBUS (relay, blind, fan-coil, valve-pump, PWM, analog output)
  - LoRa (relay)
  - Alarm (arm/disarm commands with PIN)
  - MQTT bridge (state topic routing, event firing)
"""

from __future__ import annotations

import json as _json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.sinum.api import SinumClient, SinumConnectionError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE = "http://10.0.1.1"


@asynccontextmanager
async def _fake_timeout(*args, **kwargs):
    yield


def _make_response(status: int = 200, data: object = None, content_length: int = 100):
    resp = MagicMock()
    resp.status = status
    _data = data if data is not None else {}
    resp.read = AsyncMock(return_value=_json.dumps(_data).encode())
    return resp


def _make_client(session) -> SinumClient:
    client = SinumClient("10.0.1.1", session, api_token="test-token")
    return client


# ---------------------------------------------------------------------------
# Virtual bus — exact URL / payload contracts
# ---------------------------------------------------------------------------


class TestVirtualBusContracts:
    """PATCH /api/v1/devices/virtual/{id} — verify method, URL, and JSON body."""

    @pytest.mark.asyncio
    async def test_virtual_relay_turn_on(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {"id": 5, "state": True}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.patch_virtual_device(5, {"state": True})

        call_args = session.request.await_args
        assert call_args.args[0] == "PATCH"
        assert call_args.args[1] == f"{BASE}/api/v1/devices/virtual/5"
        assert call_args.kwargs["json"] == {"state": True}
        assert result == {"id": 5, "state": True}

    @pytest.mark.asyncio
    async def test_virtual_relay_turn_off(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {"id": 5, "state": False}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_virtual_device(5, {"state": False})

        call_args = session.request.await_args
        assert call_args.kwargs["json"] == {"state": False}

    @pytest.mark.asyncio
    async def test_virtual_wicket_unlock(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {"id": 7, "state": "unlocked"}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_virtual_device(7, {"command": "unlock"})

        assert session.request.await_args.kwargs["json"] == {"command": "unlock"}

    @pytest.mark.asyncio
    async def test_virtual_wicket_lock(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {"id": 7}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_virtual_device(7, {"command": "lock"})

        assert session.request.await_args.kwargs["json"] == {"command": "lock"}

    @pytest.mark.asyncio
    async def test_virtual_dimmer_on_with_brightness(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {"id": 10, "state": "on", "brightness": 75}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_virtual_device(10, {"state": "on", "brightness": 75})

        assert session.request.await_args.kwargs["json"] == {"state": "on", "brightness": 75}
        assert session.request.await_args.args[1] == f"{BASE}/api/v1/devices/virtual/10"

    @pytest.mark.asyncio
    async def test_virtual_dimmer_off(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {"id": 10}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_virtual_device(10, {"state": "off"})

        assert session.request.await_args.kwargs["json"] == {"state": "off"}

    @pytest.mark.asyncio
    async def test_virtual_blind_open_100_percent(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {"id": 13}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_virtual_device(13, {"command": "open", "opening_percentage": 100})

        assert session.request.await_args.kwargs["json"] == {
            "command": "open",
            "opening_percentage": 100,
        }

    @pytest.mark.asyncio
    async def test_virtual_blind_close_0_percent(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_virtual_device(13, {"command": "open", "opening_percentage": 0})

        assert session.request.await_args.kwargs["json"] == {
            "command": "open",
            "opening_percentage": 0,
        }

    @pytest.mark.asyncio
    async def test_virtual_blind_stop(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_virtual_device(13, {"command": "stop"})

        assert session.request.await_args.kwargs["json"] == {"command": "stop"}

    @pytest.mark.asyncio
    async def test_virtual_blind_set_position(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_virtual_device(13, {"command": "open", "opening_percentage": 60})

        assert session.request.await_args.kwargs["json"] == {
            "command": "open",
            "opening_percentage": 60,
        }

    @pytest.mark.asyncio
    async def test_virtual_blind_tilt(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_virtual_device(13, {"command": "tilt", "tilt_percentage": 30})

        assert session.request.await_args.kwargs["json"] == {
            "command": "tilt",
            "tilt_percentage": 30,
        }

    @pytest.mark.asyncio
    async def test_virtual_gate_full_open(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_virtual_device(14, {"command": "full_open"})

        assert session.request.await_args.kwargs["json"] == {"command": "full_open"}
        assert session.request.await_args.args[1] == f"{BASE}/api/v1/devices/virtual/14"

    @pytest.mark.asyncio
    async def test_virtual_gate_close(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_virtual_device(14, {"command": "close"})

        assert session.request.await_args.kwargs["json"] == {"command": "close"}

    @pytest.mark.asyncio
    async def test_virtual_climate_set_temperature(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {"target_temperature": 215}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        raw = client.encode_temperature(21.5)  # should be 215
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_virtual_device(20, {"target_temperature": raw})

        assert session.request.await_args.kwargs["json"] == {"target_temperature": 215}

    @pytest.mark.asyncio
    async def test_virtual_climate_set_hvac_mode_heat(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_virtual_device(20, {"mode": "heating"})

        assert session.request.await_args.kwargs["json"] == {"mode": "heating"}

    @pytest.mark.asyncio
    async def test_virtual_light_with_rgb_color(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_virtual_device(
                15, {"state": "on", "led_color": "#ff8000", "brightness": 80}
            )

        payload = session.request.await_args.kwargs["json"]
        assert payload["state"] == "on"
        assert payload["led_color"] == "#ff8000"
        assert payload["brightness"] == 80


# ---------------------------------------------------------------------------
# WTP bus — exact URL / payload contracts
# ---------------------------------------------------------------------------


class TestWtpBusContracts:
    """PATCH /api/v1/devices/wtp/{id} — verify method, URL, and JSON body."""

    @pytest.mark.asyncio
    async def test_wtp_relay_turn_on(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {"id": 100, "state": True}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_wtp_device(100, {"state": True})

        call_args = session.request.await_args
        assert call_args.args[0] == "PATCH"
        assert call_args.args[1] == f"{BASE}/api/v1/devices/wtp/100"
        assert call_args.kwargs["json"] == {"state": True}

    @pytest.mark.asyncio
    async def test_wtp_relay_turn_off(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_wtp_device(100, {"state": False})

        assert session.request.await_args.kwargs["json"] == {"state": False}

    @pytest.mark.asyncio
    async def test_wtp_dimmer_on_with_level(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_wtp_device(101, {"state": True, "target_level": 60})

        assert session.request.await_args.kwargs["json"] == {"state": True, "target_level": 60}
        assert session.request.await_args.args[1] == f"{BASE}/api/v1/devices/wtp/101"

    @pytest.mark.asyncio
    async def test_wtp_dimmer_off(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_wtp_device(101, {"state": False})

        assert session.request.await_args.kwargs["json"] == {"state": False}

    @pytest.mark.asyncio
    async def test_wtp_blind_open(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_wtp_device(102, {"command": "open", "opening_percentage": 100})

        assert session.request.await_args.kwargs["json"] == {
            "command": "open",
            "opening_percentage": 100,
        }

    @pytest.mark.asyncio
    async def test_wtp_blind_set_position(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_wtp_device(102, {"command": "open", "opening_percentage": 35})

        assert session.request.await_args.kwargs["json"] == {
            "command": "open",
            "opening_percentage": 35,
        }

    @pytest.mark.asyncio
    async def test_wtp_blind_stop(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_wtp_device(102, {"command": "stop"})

        assert session.request.await_args.kwargs["json"] == {"command": "stop"}

    @pytest.mark.asyncio
    async def test_wtp_fan_coil_set_temperature(self):
        """WTP fan coil climate: temperature is sent raw (×10) via patch_wtp_device."""
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        raw = client.encode_temperature(22.0)  # 220
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_wtp_device(103, {"target_temperature": raw})

        assert session.request.await_args.kwargs["json"] == {"target_temperature": 220}
        assert session.request.await_args.args[1] == f"{BASE}/api/v1/devices/wtp/103"

    @pytest.mark.asyncio
    async def test_wtp_fan_coil_set_mode_cooling(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_wtp_device(103, {"work_mode": "cooling"})

        assert session.request.await_args.kwargs["json"] == {"work_mode": "cooling"}

    @pytest.mark.asyncio
    async def test_wtp_rgb_light_on_with_color(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_wtp_device(
                104, {"state": True, "led_color": "#00ff00", "brightness": 50}
            )

        payload = session.request.await_args.kwargs["json"]
        assert payload["state"] is True
        assert payload["led_color"] == "#00ff00"
        assert payload["brightness"] == 50


# ---------------------------------------------------------------------------
# SBUS bus — exact URL / payload contracts
# ---------------------------------------------------------------------------


class TestSbusBusContracts:
    """PATCH /api/v1/devices/sbus/{id} — verify method, URL, and JSON body."""

    @pytest.mark.asyncio
    async def test_sbus_relay_turn_on(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {"id": 200, "state": True}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_sbus_device(200, {"state": True})

        call_args = session.request.await_args
        assert call_args.args[0] == "PATCH"
        assert call_args.args[1] == f"{BASE}/api/v1/devices/sbus/200"
        assert call_args.kwargs["json"] == {"state": True}

    @pytest.mark.asyncio
    async def test_sbus_relay_turn_off(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_sbus_device(200, {"state": False})

        assert session.request.await_args.kwargs["json"] == {"state": False}

    @pytest.mark.asyncio
    async def test_sbus_blind_open(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_sbus_device(201, {"command": "open", "opening_percentage": 100})

        assert session.request.await_args.kwargs["json"] == {
            "command": "open",
            "opening_percentage": 100,
        }
        assert session.request.await_args.args[1] == f"{BASE}/api/v1/devices/sbus/201"

    @pytest.mark.asyncio
    async def test_sbus_blind_close(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_sbus_device(201, {"command": "open", "opening_percentage": 0})

        assert session.request.await_args.kwargs["json"] == {
            "command": "open",
            "opening_percentage": 0,
        }

    @pytest.mark.asyncio
    async def test_sbus_blind_stop(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_sbus_device(201, {"command": "stop"})

        assert session.request.await_args.kwargs["json"] == {"command": "stop"}

    @pytest.mark.asyncio
    async def test_sbus_blind_set_position_45(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_sbus_device(201, {"command": "open", "opening_percentage": 45})

        assert session.request.await_args.kwargs["json"] == {
            "command": "open",
            "opening_percentage": 45,
        }

    @pytest.mark.asyncio
    async def test_sbus_blind_tilt(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_sbus_device(201, {"command": "tilt", "tilt_percentage": 50})

        assert session.request.await_args.kwargs["json"] == {
            "command": "tilt",
            "tilt_percentage": 50,
        }

    @pytest.mark.asyncio
    async def test_sbus_fan_coil_set_temperature(self):
        """SBUS fan coil: temperature sent raw (×10)."""
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        raw = client.encode_temperature(20.5)  # 205
        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_sbus_device(202, {"target_temperature": raw})

        assert session.request.await_args.kwargs["json"] == {"target_temperature": 205}
        assert session.request.await_args.args[1] == f"{BASE}/api/v1/devices/sbus/202"

    @pytest.mark.asyncio
    async def test_sbus_fan_coil_work_mode_heating(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_sbus_device(202, {"work_mode": "heating"})

        assert session.request.await_args.kwargs["json"] == {"work_mode": "heating"}

    @pytest.mark.asyncio
    async def test_sbus_fan_coil_fan_speed_medium(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_sbus_device(202, {"fan_speed": "medium"})

        assert session.request.await_args.kwargs["json"] == {"fan_speed": "medium"}

    @pytest.mark.asyncio
    async def test_sbus_valve_pump_on(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_sbus_device(203, {"state": True})

        assert session.request.await_args.kwargs["json"] == {"state": True}

    @pytest.mark.asyncio
    async def test_sbus_valve_pump_off(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_sbus_device(203, {"state": False})

        assert session.request.await_args.kwargs["json"] == {"state": False}

    @pytest.mark.asyncio
    async def test_sbus_analog_output_set_value(self):
        """Analog output: value sent as float in payload."""
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_sbus_device(204, {"value": 7.5})

        assert session.request.await_args.kwargs["json"] == {"value": 7.5}
        assert session.request.await_args.args[1] == f"{BASE}/api/v1/devices/sbus/204"

    @pytest.mark.asyncio
    async def test_sbus_pwm_set_duty_cycle(self):
        """PWM device: duty_cycle sent as int in payload."""
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_sbus_device(205, {"duty_cycle": 75})

        assert session.request.await_args.kwargs["json"] == {"duty_cycle": 75}

    @pytest.mark.asyncio
    async def test_sbus_common_valve_on(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_sbus_device(206, {"state": True})

        assert session.request.await_args.kwargs["json"] == {"state": True}

    @pytest.mark.asyncio
    async def test_sbus_dimmer_on_with_brightness(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_sbus_device(207, {"state": True, "brightness": 90})

        assert session.request.await_args.kwargs["json"] == {"state": True, "brightness": 90}


# ---------------------------------------------------------------------------
# LoRa bus — exact URL / payload contracts
# ---------------------------------------------------------------------------


class TestLoraBusContracts:
    """PATCH /api/v1/devices/lora/{id} — verify method, URL, and JSON body."""

    @pytest.mark.asyncio
    async def test_lora_relay_turn_on(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {"id": 300, "state": True}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_lora_device(300, {"state": True})

        call_args = session.request.await_args
        assert call_args.args[0] == "PATCH"
        assert call_args.args[1] == f"{BASE}/api/v1/devices/lora/300"
        assert call_args.kwargs["json"] == {"state": True}

    @pytest.mark.asyncio
    async def test_lora_relay_turn_off(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_lora_device(300, {"state": False})

        assert session.request.await_args.kwargs["json"] == {"state": False}

    @pytest.mark.asyncio
    async def test_lora_get_devices_returns_list(self):
        """GET /api/v1/devices/lora returns list of LoRa devices."""
        session = MagicMock(spec=aiohttp.ClientSession)
        lora_list = [
            {"id": 301, "type": "temperature_sensor", "temperature": 215},
            {"id": 302, "type": "relay", "state": False},
            {"id": 303, "type": "humidity_sensor", "humidity": 650},
        ]
        resp = _make_response(200, {"data": lora_list})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            devices = await client.get_lora_devices()

        call_args = session.request.await_args
        assert call_args.args[0] == "GET"
        assert call_args.args[1] == f"{BASE}/api/v1/devices/lora"
        assert len(devices) == 3
        assert devices[0]["type"] == "temperature_sensor"

    @pytest.mark.asyncio
    async def test_lora_get_single_device(self):
        """GET /api/v1/devices/lora/{id} returns single device dict."""
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(
            200, {"data": {"id": 301, "type": "opening_sensor", "state": "closed"}}
        )
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            device = await client.get_lora_device(301)

        assert session.request.await_args.args[1] == f"{BASE}/api/v1/devices/lora/301"
        assert device["type"] == "opening_sensor"

    @pytest.mark.asyncio
    async def test_lora_temperature_decode(self):
        """Temperature decode: raw 215 → 21.5°C (÷10)."""
        client = _make_client(MagicMock())
        assert client.decode_temperature(215) == 21.5
        assert client.decode_temperature(180) == 18.0
        assert client.decode_temperature(255) == 25.5

    @pytest.mark.asyncio
    async def test_lora_flood_sensor_state_reading(self):
        """LoRa flood sensor: state is read from 'state' key."""
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {"id": 304, "type": "flood_sensor", "state": True}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            device = await client.get_lora_device(304)

        assert device["state"] is True


# ---------------------------------------------------------------------------
# Alarm system — exact URL / payload contracts
# ---------------------------------------------------------------------------


class TestAlarmBusContracts:
    """POST /api/v1/devices/alarm-system/{id}/command/{cmd} — verify all arm/disarm flows."""

    @pytest.mark.asyncio
    async def test_alarm_arm_away_with_pin(self):
        """arm_away sends POST to .../command/arm with {"arm": pin}."""
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(204, {}, content_length=0)
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.command_alarm_device(1, "arm", {"arm": "1234"})

        call_args = session.request.await_args
        assert call_args.args[0] == "POST"
        assert call_args.args[1] == f"{BASE}/api/v1/devices/alarm-system/1/command/arm"
        assert call_args.kwargs["json"] == {"arm": "1234"}

    @pytest.mark.asyncio
    async def test_alarm_disarm_with_pin(self):
        """disarm sends POST to .../command/disarm with {"disarm": pin}."""
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(204, {}, content_length=0)
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.command_alarm_device(1, "disarm", {"disarm": "9999"})

        call_args = session.request.await_args
        assert call_args.args[0] == "POST"
        assert call_args.args[1] == f"{BASE}/api/v1/devices/alarm-system/1/command/disarm"
        assert call_args.kwargs["json"] == {"disarm": "9999"}

    @pytest.mark.asyncio
    async def test_alarm_arm_different_zone(self):
        """Alarm commands use the zone_id in the URL."""
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(204, {}, content_length=0)
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.command_alarm_device(42, "arm", {"arm": "0000"})

        assert (
            session.request.await_args.args[1]
            == f"{BASE}/api/v1/devices/alarm-system/42/command/arm"
        )

    @pytest.mark.asyncio
    async def test_alarm_get_devices_endpoint(self):
        """GET /api/v1/devices/alarm-system returns list."""
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(
            200, {"data": [{"id": 1, "type": "alarm_zone", "zone_status": "disarmed"}]}
        )
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            devices = await client.get_alarm_devices()

        assert session.request.await_args.args[0] == "GET"
        assert session.request.await_args.args[1] == f"{BASE}/api/v1/devices/alarm-system"
        assert len(devices) == 1
        assert devices[0]["zone_status"] == "disarmed"

    @pytest.mark.asyncio
    async def test_alarm_patch_device(self):
        """PATCH /api/v1/devices/alarm-system/{id} — e.g. update zone settings."""
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.patch_alarm_device(1, {"enter_time_delay": 30})

        call_args = session.request.await_args
        assert call_args.args[0] == "PATCH"
        assert call_args.args[1] == f"{BASE}/api/v1/devices/alarm-system/1"
        assert call_args.kwargs["json"] == {"enter_time_delay": 30}

    @pytest.mark.asyncio
    async def test_alarm_connection_error_raises(self):
        """Command failure raises SinumConnectionError (e.g. wrong PIN → 422)."""
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(422, {"error": {"errors": {"pin": {"text": "Invalid PIN"}}}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with (
            patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout),
            pytest.raises(SinumConnectionError, match="Validation error"),
        ):
            await client.command_alarm_device(1, "arm", {"arm": "wrong"})


# ---------------------------------------------------------------------------
# Variable (automation) API contracts
# ---------------------------------------------------------------------------


class TestVariableContracts:
    """PATCH /api/v1/variables/{id} — verify value payload."""

    @pytest.mark.asyncio
    async def test_set_variable_integer(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {"id": 10, "value": 42}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.set_variable(10, 42)

        call_args = session.request.await_args
        assert call_args.args[0] == "PATCH"
        assert call_args.args[1] == f"{BASE}/api/v1/variables/10"
        assert call_args.kwargs["json"] == {"value": 42}

    @pytest.mark.asyncio
    async def test_set_variable_float(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {"id": 11, "value": 3.14}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.set_variable(11, 3.14)

        assert session.request.await_args.kwargs["json"] == {"value": 3.14}

    @pytest.mark.asyncio
    async def test_set_variable_boolean(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(200, {"data": {"id": 12, "value": True}})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.set_variable(12, True)

        assert session.request.await_args.kwargs["json"] == {"value": True}


# ---------------------------------------------------------------------------
# Scene activation contracts
# ---------------------------------------------------------------------------


class TestSceneContracts:
    @pytest.mark.asyncio
    async def test_run_scene_posts_to_activate_endpoint(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(204, {}, content_length=0)
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.run_scene(7)

        call_args = session.request.await_args
        assert call_args.args[0] == "POST"
        assert call_args.args[1] == f"{BASE}/api/v1/scenes/7/activate"

    @pytest.mark.asyncio
    async def test_run_scene_uses_correct_id(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(204, {}, content_length=0)
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.run_scene(99)

        assert session.request.await_args.args[1] == f"{BASE}/api/v1/scenes/99/activate"


# ---------------------------------------------------------------------------
# Notification API contracts
# ---------------------------------------------------------------------------


class TestNotificationContracts:
    @pytest.mark.asyncio
    async def test_send_notification_payload(self):
        """Notification: POST /api/v1/notify with title+message."""
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(204, {}, content_length=0)
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            await client.send_notification("Alert", "Motion detected in kitchen")

        call_args = session.request.await_args
        assert call_args.args[0] == "POST"
        assert call_args.args[1] == f"{BASE}/api/v1/notify"
        payload = call_args.kwargs["json"]
        assert payload["title"] == "Alert"
        assert payload["message"] == "Motion detected in kitchen"


# ---------------------------------------------------------------------------
# Temperature encode/decode (protocol-critical for climate entities)
# ---------------------------------------------------------------------------


class TestTemperatureEncoding:
    """Sinum uses raw int = Celsius × 10. These are critical for climate correctness."""

    def test_encode_typical_values(self):
        client = _make_client(MagicMock())
        assert client.encode_temperature(21.0) == 210
        assert client.encode_temperature(22.5) == 225
        assert client.encode_temperature(15.0) == 150
        assert client.encode_temperature(30.0) == 300

    def test_decode_typical_values(self):
        client = _make_client(MagicMock())
        assert client.decode_temperature(210) == 21.0
        assert client.decode_temperature(225) == 22.5
        assert client.decode_temperature(150) == 15.0

    def test_encode_decode_roundtrip(self):
        """encode(decode(x)) == x for typical temperatures."""
        client = _make_client(MagicMock())
        for temp in (18.0, 19.5, 21.0, 22.5, 24.0, 25.5):
            raw = client.encode_temperature(temp)
            assert client.decode_temperature(raw) == temp

    def test_encode_rounds_to_nearest_tenth(self):
        """Fractional temperatures are rounded correctly (e.g. 21.15 → 212, not 211)."""
        client = _make_client(MagicMock())
        assert client.encode_temperature(21.15) == 212  # rounds up
        assert client.encode_temperature(21.14) == 211  # rounds down


# ---------------------------------------------------------------------------
# MQTT bridge — state routing and event handling
# ---------------------------------------------------------------------------


class TestMqttBridgeContracts:
    """Verify MQTT message routing: sinum/state/{id} updates coordinator stores."""

    def _make_coordinator(self):
        coord = MagicMock()
        coord.virtual_devices = {}
        coord.wtp_devices = {}
        coord.sbus_devices = {}
        coord.lora_devices = {}
        coord.async_set_updated_data = MagicMock()
        return coord

    def _make_msg(self, topic: str, payload: str):
        msg = MagicMock()
        msg.topic = topic
        msg.payload = payload
        return msg

    def test_virtual_state_update_stored_in_virtual_devices(self):
        from custom_components.sinum.mqtt import SinumMqttBridge

        coord = self._make_coordinator()
        coord.virtual_devices[5] = {"id": 5, "state": False}
        bridge = SinumMqttBridge(MagicMock(), coord)

        msg = self._make_msg("sinum/state/5", '{"id":5,"state":true,"source":"virtual"}')
        bridge._handle_state(msg)

        assert coord.virtual_devices[5]["state"] is True
        coord.async_set_updated_data.assert_called_once()

    def test_wtp_state_update_stored_in_wtp_devices(self):
        from custom_components.sinum.mqtt import SinumMqttBridge

        coord = self._make_coordinator()
        coord.wtp_devices[100] = {"id": 100, "state": False}
        bridge = SinumMqttBridge(MagicMock(), coord)

        msg = self._make_msg("sinum/state/100", '{"id":100,"state":true,"source":"wtp"}')
        bridge._handle_state(msg)

        assert coord.wtp_devices[100]["state"] is True

    def test_sbus_state_update_stored_in_sbus_devices(self):
        from custom_components.sinum.mqtt import SinumMqttBridge

        coord = self._make_coordinator()
        coord.sbus_devices[200] = {"id": 200, "current_opening": 0}
        bridge = SinumMqttBridge(MagicMock(), coord)

        msg = self._make_msg("sinum/state/200", '{"id":200,"current_opening":75,"source":"sbus"}')
        bridge._handle_state(msg)

        assert coord.sbus_devices[200]["current_opening"] == 75

    def test_new_device_added_to_store(self):
        """Device not yet in store gets added with _id set."""
        from custom_components.sinum.mqtt import SinumMqttBridge

        coord = self._make_coordinator()
        bridge = SinumMqttBridge(MagicMock(), coord)

        msg = self._make_msg("sinum/state/99", '{"state":true,"source":"virtual"}')
        bridge._handle_state(msg)

        assert 99 in coord.virtual_devices
        assert coord.virtual_devices[99]["_id"] == 99

    def test_invalid_topic_id_ignored(self):
        """Non-numeric device ID in topic is silently ignored."""
        from custom_components.sinum.mqtt import SinumMqttBridge

        coord = self._make_coordinator()
        bridge = SinumMqttBridge(MagicMock(), coord)

        msg = self._make_msg("sinum/state/invalid", '{"state":true,"source":"virtual"}')
        bridge._handle_state(msg)

        coord.async_set_updated_data.assert_not_called()

    def test_invalid_json_payload_ignored(self):
        """Malformed JSON payload is ignored without updating stores."""
        from custom_components.sinum.mqtt import SinumMqttBridge

        coord = self._make_coordinator()
        bridge = SinumMqttBridge(MagicMock(), coord)

        msg = self._make_msg("sinum/state/5", "not-json")
        bridge._handle_state(msg)

        coord.async_set_updated_data.assert_not_called()

    def test_unknown_source_ignored(self):
        """Source not in (virtual, wtp, sbus) is silently dropped."""
        from custom_components.sinum.mqtt import SinumMqttBridge

        coord = self._make_coordinator()
        bridge = SinumMqttBridge(MagicMock(), coord)

        msg = self._make_msg("sinum/state/5", '{"id":5,"state":true,"source":"modbus"}')
        bridge._handle_state(msg)

        coord.async_set_updated_data.assert_not_called()

    def test_event_fires_ha_event(self):
        """sinum/event/<type> fires hass.bus.async_fire with sinum_{type}."""
        from custom_components.sinum.mqtt import SinumMqttBridge

        hass = MagicMock()
        coord = self._make_coordinator()
        bridge = SinumMqttBridge(hass, coord)

        msg = self._make_msg("sinum/event/button_press", '{"device_id":10,"action":"press"}')
        bridge._handle_event(msg)

        hass.bus.async_fire.assert_called_once_with(
            "sinum_button_press",
            {"device_id": 10, "action": "press", "topic_prefix": "sinum"},
        )

    def test_event_invalid_json_fires_raw(self):
        """Event with non-JSON payload fires with {'raw': payload_str}."""
        from custom_components.sinum.mqtt import SinumMqttBridge

        hass = MagicMock()
        coord = self._make_coordinator()
        bridge = SinumMqttBridge(hass, coord)

        msg = self._make_msg("sinum/event/alarm", "not-json-here")
        bridge._handle_event(msg)

        hass.bus.async_fire.assert_called_once()
        fired_payload = hass.bus.async_fire.call_args.args[1]
        assert "raw" in fired_payload

    def test_mqtt_publish_command_sends_to_correct_topic(self):
        """async_publish_command → sinum/cmd/{device_id} with JSON payload."""
        from custom_components.sinum.mqtt import TOPIC_CMD

        # Verify the topic template is correct
        assert TOPIC_CMD == "sinum/cmd/{device_id}"
        assert TOPIC_CMD.format(device_id=42) == "sinum/cmd/42"

    def test_wtp_temperature_update_preserves_existing_fields(self):
        """MQTT update merges into existing device data (dict.update), not replace."""
        from custom_components.sinum.mqtt import SinumMqttBridge

        coord = self._make_coordinator()
        coord.wtp_devices[50] = {
            "id": 50,
            "type": "fan_coil",
            "room_temperature": 200,
            "target_temperature": 210,
        }
        bridge = SinumMqttBridge(MagicMock(), coord)

        msg = self._make_msg("sinum/state/50", '{"room_temperature":215,"source":"wtp"}')
        bridge._handle_state(msg)

        # Existing fields are preserved, only updated field changes
        assert coord.wtp_devices[50]["type"] == "fan_coil"
        assert coord.wtp_devices[50]["target_temperature"] == 210
        assert coord.wtp_devices[50]["room_temperature"] == 215


# ---------------------------------------------------------------------------
# Coordinator data flow — device parsing per bus
# ---------------------------------------------------------------------------


class TestCoordinatorDataFlow:
    """Verify coordinator correctly routes and stores per-bus API responses."""

    def _make_coordinator(self, client):
        from custom_components.sinum.coordinator import SinumCoordinator

        hass = MagicMock()
        hass.loop = MagicMock()
        # Required async method not in all test fixtures
        if not isinstance(client.get_lua_hub_info, AsyncMock):
            client.get_lua_hub_info = AsyncMock(return_value={})
        if not isinstance(client.get_automations, AsyncMock):
            client.get_automations = AsyncMock(return_value=[])
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            coord = SinumCoordinator(hass, client, scan_interval=30)
        return coord

    @pytest.mark.asyncio
    async def test_virtual_device_stored_by_id(self):
        """Virtual device list → stored in coordinator.virtual_devices keyed by id."""
        client = MagicMock()
        client.get_hub_info = AsyncMock(return_value={"name": "test-hub", "firmware": "1.0"})
        client.get_rooms = AsyncMock(return_value=[])
        client.get_floors = AsyncMock(return_value=[])
        client.get_parent_devices = AsyncMock(return_value=[])
        client.get_virtual_devices = AsyncMock(
            return_value=[
                {"id": 1, "type": "relay", "state": True, "name": "Kitchen light"},
                {"id": 2, "type": "blind_controller_integrator", "last_set_target_opening": 50},
            ]
        )
        client.get_wtp_devices = AsyncMock(return_value=[])
        client.get_sbus_devices = AsyncMock(return_value=[])
        client.get_alarm_devices = AsyncMock(return_value=[])
        client.get_lora_devices = AsyncMock(return_value=[])
        client.get_variables = AsyncMock(return_value=[])
        client.get_schedules = AsyncMock(return_value=[])

        coord = self._make_coordinator(client)
        with patch.object(coord, "async_set_updated_data"):
            await coord._async_update_data()

        assert 1 in coord.virtual_devices
        assert 2 in coord.virtual_devices
        assert coord.virtual_devices[1]["type"] == "relay"
        assert coord.virtual_devices[1]["state"] is True

    @pytest.mark.asyncio
    async def test_wtp_device_stored_by_id(self):
        """WTP device list → stored in coordinator.wtp_devices keyed by id."""
        client = MagicMock()
        client.get_hub_info = AsyncMock(return_value={"name": "test-hub"})
        client.get_rooms = AsyncMock(return_value=[])
        client.get_floors = AsyncMock(return_value=[])
        client.get_parent_devices = AsyncMock(return_value=[])
        client.get_virtual_devices = AsyncMock(return_value=[])
        client.get_wtp_devices = AsyncMock(
            return_value=[
                {"id": 100, "type": "relay", "state": False, "name": "WTP relay 1"},
                {"id": 101, "type": "fan_coil", "room_temperature": 210, "work_mode": "heating"},
            ]
        )
        client.get_sbus_devices = AsyncMock(return_value=[])
        client.get_alarm_devices = AsyncMock(return_value=[])
        client.get_lora_devices = AsyncMock(return_value=[])
        client.get_variables = AsyncMock(return_value=[])
        client.get_schedules = AsyncMock(return_value=[])

        coord = self._make_coordinator(client)
        with patch.object(coord, "async_set_updated_data"):
            await coord._async_update_data()

        assert 100 in coord.wtp_devices
        assert 101 in coord.wtp_devices
        assert coord.wtp_devices[101]["work_mode"] == "heating"

    @pytest.mark.asyncio
    async def test_sbus_device_stored_by_id(self):
        """SBUS device list → stored in coordinator.sbus_devices keyed by id."""
        client = MagicMock()
        client.get_hub_info = AsyncMock(return_value={"name": "test-hub"})
        client.get_rooms = AsyncMock(return_value=[])
        client.get_floors = AsyncMock(return_value=[])
        client.get_parent_devices = AsyncMock(return_value=[])
        client.get_virtual_devices = AsyncMock(return_value=[])
        client.get_wtp_devices = AsyncMock(return_value=[])
        client.get_sbus_devices = AsyncMock(
            return_value=[
                {"id": 200, "type": "blind_controller", "current_opening": 0},
                {"id": 201, "type": "fan_coil", "work_mode": "off"},
                {"id": 202, "type": "impulse_meter", "total_count": 1234},
            ]
        )
        client.get_alarm_devices = AsyncMock(return_value=[])
        client.get_lora_devices = AsyncMock(return_value=[])
        client.get_variables = AsyncMock(return_value=[])
        client.get_schedules = AsyncMock(return_value=[])

        coord = self._make_coordinator(client)
        with patch.object(coord, "async_set_updated_data"):
            await coord._async_update_data()

        assert 200 in coord.sbus_devices
        assert 201 in coord.sbus_devices
        assert 202 in coord.sbus_devices
        assert coord.sbus_devices[202]["total_count"] == 1234

    @pytest.mark.asyncio
    async def test_lora_device_stored_by_id(self):
        """LoRa device list → stored in coordinator.lora_devices keyed by id."""
        client = MagicMock()
        client.get_hub_info = AsyncMock(return_value={"name": "test-hub"})
        client.get_rooms = AsyncMock(return_value=[])
        client.get_floors = AsyncMock(return_value=[])
        client.get_parent_devices = AsyncMock(return_value=[])
        client.get_virtual_devices = AsyncMock(return_value=[])
        client.get_wtp_devices = AsyncMock(return_value=[])
        client.get_sbus_devices = AsyncMock(return_value=[])
        client.get_alarm_devices = AsyncMock(return_value=[])
        client.get_lora_devices = AsyncMock(
            return_value=[
                {"id": 300, "type": "temperature_sensor", "temperature": 215},
                {"id": 301, "type": "flood_sensor", "state": False},
                {"id": 302, "type": "humidity_sensor", "humidity": 650},
            ]
        )
        client.get_variables = AsyncMock(return_value=[])
        client.get_schedules = AsyncMock(return_value=[])

        coord = self._make_coordinator(client)
        with patch.object(coord, "async_set_updated_data"):
            await coord._async_update_data()

        assert 300 in coord.lora_devices
        assert 301 in coord.lora_devices
        assert 302 in coord.lora_devices
        assert coord.lora_devices[300]["temperature"] == 215

    @pytest.mark.asyncio
    async def test_alarm_device_stored_by_id(self):
        """Alarm device list → stored in coordinator.alarm_devices keyed by id."""
        client = MagicMock()
        client.get_hub_info = AsyncMock(return_value={"name": "test-hub"})
        client.get_rooms = AsyncMock(return_value=[])
        client.get_floors = AsyncMock(return_value=[])
        client.get_parent_devices = AsyncMock(return_value=[])
        client.get_virtual_devices = AsyncMock(return_value=[])
        client.get_wtp_devices = AsyncMock(return_value=[])
        client.get_sbus_devices = AsyncMock(return_value=[])
        client.get_alarm_devices = AsyncMock(
            return_value=[
                {"id": 1, "type": "alarm_zone", "zone_status": "disarmed"},
            ]
        )
        client.get_lora_devices = AsyncMock(return_value=[])
        client.get_variables = AsyncMock(return_value=[])
        client.get_schedules = AsyncMock(return_value=[])

        coord = self._make_coordinator(client)
        with patch.object(coord, "async_set_updated_data"):
            await coord._async_update_data()

        assert 1 in coord.alarm_zones
        assert coord.alarm_zones[1]["zone_status"] == "disarmed"


# ---------------------------------------------------------------------------
# 304 / empty-response handling (important for PATCH idempotency)
# ---------------------------------------------------------------------------


class TestHttpEdgeCasesPerBus:
    """304 Not Modified means no state change — each bus PATCH must handle it."""

    @pytest.mark.asyncio
    async def test_virtual_304_returns_empty_dict(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(304, {})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.patch_virtual_device(5, {"state": True})

        assert result == {}

    @pytest.mark.asyncio
    async def test_wtp_304_returns_empty_dict(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(304, {})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.patch_wtp_device(100, {"state": True})

        assert result == {}

    @pytest.mark.asyncio
    async def test_sbus_304_returns_empty_dict(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(304, {})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.patch_sbus_device(200, {"state": True})

        assert result == {}

    @pytest.mark.asyncio
    async def test_lora_304_returns_empty_dict(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(304, {})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout):
            result = await client.patch_lora_device(300, {"state": True})

        assert result == {}

    @pytest.mark.asyncio
    async def test_408_bus_timeout_raises_connection_error_with_bus_info(self):
        """HTTP 408 from hub means bus-side timeout — raised as SinumConnectionError."""
        session = MagicMock(spec=aiohttp.ClientSession)
        resp = _make_response(408, {})
        session.request = AsyncMock(return_value=resp)
        client = _make_client(session)

        with (
            patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout),
            pytest.raises(SinumConnectionError, match="Hub internal timeout"),
        ):
            await client.patch_sbus_device(200, {"state": True})
