"""Integration tests: verify the 408-retry fix actually works end-to-end.

These tests use the REAL SinumClient (no client mock) with a mocked HTTP
session. They prove that when the hub returns 408 on the first try but 200
on the second, the command SUCCEEDS and state is correctly updated.

Testing errors is not a substitute for testing that the fix works.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.exceptions import HomeAssistantError

from custom_components.sinum.api import SinumClient


# ---------------------------------------------------------------------------
# HTTP-level helpers (mirror test_api.py pattern)
# ---------------------------------------------------------------------------

def _resp(status: int, data: object) -> MagicMock:
    r = MagicMock()
    r.status = status
    r.content_length = 100
    r.json = AsyncMock(return_value=data)
    return r


@asynccontextmanager
async def _fake_timeout(*args, **kwargs):
    yield


def _patches():
    """Context manager: disable asyncio.timeout and sleep for fast tests."""
    return (
        patch("custom_components.sinum.api.asyncio.timeout", _fake_timeout),
        patch("custom_components.sinum.api.asyncio.sleep", AsyncMock()),
    )


# ---------------------------------------------------------------------------
# Full-stack entity helpers
#
# Build a real SinumClient backed by a mocked aiohttp session, then wire it
# into an entity. This tests the whole path: entity → api._request → retry.
# ---------------------------------------------------------------------------

def _make_client(responses: list) -> tuple[SinumClient, MagicMock]:
    session = MagicMock(spec=aiohttp.ClientSession)
    session.request = AsyncMock(side_effect=responses)
    client = SinumClient("10.0.62.167", session, api_token="test-token")
    return client, session


def _coordinator_with_client(client: SinumClient, virtual=None, wtp=None, sbus=None):
    c = MagicMock()
    c.client = client
    c.virtual_devices = virtual or {}
    c.wtp_devices = wtp or {}
    c.sbus_devices = sbus or {}
    c.lora_devices = {}
    c.variables = []
    return c


def _wire(entity):
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    return entity


# ===========================================================================
# SinumThermostat — the exact entity from the bug report
# ===========================================================================

class TestThermostatRetryIntegration:
    """Verify set_hvac_mode works end-to-end when hub returns 408 → 200."""

    def _make(self, device, responses):
        from custom_components.sinum.climate import SinumThermostat
        client, session = _make_client(responses)
        c = _coordinator_with_client(client, virtual={device["id"]: device})
        entity = _wire(SinumThermostat(c, device["id"], "e"))
        return entity, c, session

    @pytest.mark.asyncio
    async def test_set_hvac_mode_succeeds_after_408_retry(self):
        """Reproduce the bug: 408 on first PATCH → retry → 200 → success, no exception."""
        device = {"id": 9, "type": "thermostat", "mode": "heating",
                  "target_temperature": 220, "temperature": 215}
        first = _resp(408, {})
        second = _resp(200, {"data": {"id": 9, "mode": "off"}})
        entity, c, session = self._make(device, [first, second])

        with _patches()[0], _patches()[1]:
            # Must NOT raise — this was the bug
            await entity.async_set_hvac_mode(HVACMode.OFF)

        # Hub was called twice: first attempt + retry
        assert session.request.call_count == 2
        # State updated in coordinator
        assert c.virtual_devices[9]["mode"] == "off"

    @pytest.mark.asyncio
    async def test_set_hvac_mode_updates_state_after_retry(self):
        """After 408→200 retry, coordinator data is merged with hub response."""
        device = {"id": 9, "type": "thermostat", "mode": "heating",
                  "target_temperature": 220, "temperature": 215, "state": True}
        first = _resp(408, {})
        second = _resp(200, {"data": {"id": 9, "mode": "cooling", "state": False}})
        entity, c, session = self._make(device, [first, second])

        with _patches()[0], _patches()[1]:
            await entity.async_set_hvac_mode(HVACMode.COOL)

        assert c.virtual_devices[9]["mode"] == "cooling"
        assert c.virtual_devices[9]["state"] is False

    @pytest.mark.asyncio
    async def test_set_hvac_mode_raises_only_when_both_attempts_fail(self):
        """If both the first attempt and retry return 408, HomeAssistantError is raised."""
        device = {"id": 9, "type": "thermostat", "mode": "heating",
                  "target_temperature": 220, "temperature": 215}
        entity, c, session = self._make(device, [_resp(408, {}), _resp(408, {})])

        with _patches()[0], _patches()[1], pytest.raises(HomeAssistantError):
            await entity.async_set_hvac_mode(HVACMode.OFF)

        assert session.request.call_count == 2

    @pytest.mark.asyncio
    async def test_set_hvac_mode_succeeds_on_first_try_no_retry(self):
        """Normal case: hub returns 200 directly, only one request made."""
        device = {"id": 9, "type": "thermostat", "mode": "heating",
                  "target_temperature": 220, "temperature": 215}
        entity, c, session = self._make(device, [_resp(200, {"data": {"id": 9, "mode": "off"}})])

        with _patches()[0], _patches()[1]:
            await entity.async_set_hvac_mode(HVACMode.OFF)

        assert session.request.call_count == 1
        assert c.virtual_devices[9]["mode"] == "off"

    @pytest.mark.asyncio
    async def test_set_temperature_succeeds_after_408_retry(self):
        """set_temperature also retries on 408 (uses same api._request path)."""
        device = {"id": 9, "type": "thermostat", "mode": "heating",
                  "target_temperature": 220, "temperature": 215,
                  "target_temperature_minimum": 50, "target_temperature_maximum": 300}
        first = _resp(408, {})
        second = _resp(200, {"data": {"id": 9, "target_temperature": 230}})
        entity, c, session = self._make(device, [first, second])

        with _patches()[0], _patches()[1]:
            await entity.async_set_temperature(temperature=23.0)

        assert session.request.call_count == 2
        assert c.virtual_devices[9]["target_temperature"] == 230

    @pytest.mark.asyncio
    async def test_retry_sleeps_one_second_before_second_attempt(self):
        """Retry must pause 1 second to let bus recover (timing contract)."""
        device = {"id": 9, "type": "thermostat", "mode": "heating",
                  "target_temperature": 220, "temperature": 215}
        first = _resp(408, {})
        second = _resp(200, {"data": {"id": 9, "mode": "off"}})
        entity, c, _ = self._make(device, [first, second])
        mock_sleep = AsyncMock()

        with _patches()[0], patch("custom_components.sinum.api.asyncio.sleep", mock_sleep):
            await entity.async_set_hvac_mode(HVACMode.OFF)

        mock_sleep.assert_awaited_once_with(1)


# ===========================================================================
# _BusClimateMixin — FanCoil (SBUS)
# ===========================================================================

class TestFanCoilRetryIntegration:

    def _make_sbus(self, device, responses):
        from custom_components.sinum.climate import SinumFanCoilClimate
        client, session = _make_client(responses)
        c = _coordinator_with_client(client, sbus={device["id"]: device})
        entity = _wire(SinumFanCoilClimate(c, device["id"], "e", "sbus"))
        return entity, c, session

    @pytest.mark.asyncio
    async def test_set_hvac_mode_succeeds_after_408_retry(self):
        device = {"id": 5, "type": "fan_coil", "work_mode": "heating",
                  "target_temperature": 220}
        first = _resp(408, {})
        second = _resp(200, {"data": {"id": 5, "work_mode": "cooling"}})
        entity, c, session = self._make_sbus(device, [first, second])

        with _patches()[0], _patches()[1]:
            await entity.async_set_hvac_mode(HVACMode.COOL)

        assert session.request.call_count == 2
        assert c.sbus_devices[5]["work_mode"] == "cooling"

    @pytest.mark.asyncio
    async def test_set_fan_mode_succeeds_after_408_retry(self):
        device = {"id": 5, "type": "fan_coil", "work_mode": "heating",
                  "target_temperature": 220}
        first = _resp(408, {})
        second = _resp(200, {"data": {"id": 5, "fan": {"manual_fan_gear": "second"}}})
        entity, c, session = self._make_sbus(device, [first, second])

        with _patches()[0], _patches()[1]:
            await entity.async_set_fan_mode("2")

        assert session.request.call_count == 2


# ===========================================================================
# SinumTemperatureRegulatorClimate
# ===========================================================================

class TestTemperatureRegulatorRetryIntegration:

    def _make(self, device, responses, bus="sbus"):
        from custom_components.sinum.climate import SinumTemperatureRegulatorClimate
        client, session = _make_client(responses)
        store = {device["id"]: device}
        c = _coordinator_with_client(
            client,
            sbus=store if bus == "sbus" else {},
            wtp=store if bus == "wtp" else {},
        )
        entity = _wire(SinumTemperatureRegulatorClimate(c, device["id"], "e", bus))
        return entity, c, session

    @pytest.mark.asyncio
    async def test_set_hvac_mode_succeeds_after_408_retry(self):
        device = {"id": 6, "type": "temperature_regulator", "system_mode": "heating",
                  "target_temperature": 220, "mode_mutable": True}
        first = _resp(408, {})
        second = _resp(200, {"data": {"id": 6, "system_mode": "off"}})
        entity, c, session = self._make(device, [first, second])

        with _patches()[0], _patches()[1]:
            await entity.async_set_hvac_mode(HVACMode.OFF)

        assert session.request.call_count == 2
        assert c.sbus_devices[6]["system_mode"] == "off"

    @pytest.mark.asyncio
    async def test_turn_on_succeeds_after_408_retry(self):
        device = {"id": 6, "type": "temperature_regulator", "system_mode": "off",
                  "target_temperature": 220, "mode_mutable": True}
        first = _resp(408, {})
        second = _resp(200, {"data": {"id": 6, "system_mode": "heating"}})
        entity, c, session = self._make(device, [first, second])

        with _patches()[0], _patches()[1]:
            await entity.async_turn_on()

        assert session.request.call_count == 2
        assert c.sbus_devices[6]["system_mode"] == "heating"

    @pytest.mark.asyncio
    async def test_turn_off_succeeds_after_408_retry(self):
        device = {"id": 6, "type": "temperature_regulator", "system_mode": "heating",
                  "target_temperature": 220, "mode_mutable": True}
        first = _resp(408, {})
        second = _resp(200, {"data": {"id": 6, "system_mode": "off"}})
        entity, c, session = self._make(device, [first, second])

        with _patches()[0], _patches()[1]:
            await entity.async_turn_off()

        assert session.request.call_count == 2


# ===========================================================================
# Switch — virtual relay
# ===========================================================================

class TestSwitchRetryIntegration:

    def _make_relay(self, device, responses):
        from custom_components.sinum.switch import SinumRelaySwitch
        client, session = _make_client(responses)
        c = _coordinator_with_client(client, virtual={device["id"]: device})
        entity = _wire(SinumRelaySwitch(c, device["id"], "e"))
        return entity, c, session

    def _make_bus_relay(self, device, responses, bus="wtp"):
        from custom_components.sinum.switch import SinumBusRelaySwitch
        client, session = _make_client(responses)
        store = {device["id"]: device}
        c = _coordinator_with_client(
            client,
            wtp=store if bus == "wtp" else {},
            sbus=store if bus == "sbus" else {},
        )
        entity = _wire(SinumBusRelaySwitch(c, device["id"], "e", bus))
        return entity, c, session

    @pytest.mark.asyncio
    async def test_relay_turn_on_succeeds_after_408_retry(self):
        device = {"id": 2, "type": "relay_integrator", "state": False}
        first = _resp(408, {})
        second = _resp(200, {"data": {"id": 2, "state": True}})
        entity, c, session = self._make_relay(device, [first, second])

        with _patches()[0], _patches()[1]:
            await entity.async_turn_on()

        assert session.request.call_count == 2
        assert c.virtual_devices[2]["state"] is True

    @pytest.mark.asyncio
    async def test_relay_turn_off_succeeds_after_408_retry(self):
        device = {"id": 2, "type": "relay_integrator", "state": True}
        first = _resp(408, {})
        second = _resp(200, {"data": {"id": 2, "state": False}})
        entity, c, session = self._make_relay(device, [first, second])

        with _patches()[0], _patches()[1]:
            await entity.async_turn_off()

        assert session.request.call_count == 2
        assert c.virtual_devices[2]["state"] is False

    @pytest.mark.asyncio
    async def test_wtp_relay_turn_on_succeeds_after_408_retry(self):
        device = {"id": 8, "type": "relay", "state": False}
        first = _resp(408, {})
        second = _resp(200, {"data": {"id": 8, "state": True}})
        entity, c, session = self._make_bus_relay(device, [first, second], "wtp")

        with _patches()[0], _patches()[1]:
            await entity.async_turn_on()

        assert session.request.call_count == 2
        assert c.wtp_devices[8]["state"] is True

    @pytest.mark.asyncio
    async def test_sbus_relay_turn_on_succeeds_after_408_retry(self):
        device = {"id": 8, "type": "relay", "state": False}
        first = _resp(408, {})
        second = _resp(200, {"data": {"id": 8, "state": True}})
        entity, c, session = self._make_bus_relay(device, [first, second], "sbus")

        with _patches()[0], _patches()[1]:
            await entity.async_turn_on()

        assert session.request.call_count == 2
        assert c.sbus_devices[8]["state"] is True


# ===========================================================================
# Cover — virtual blind
# ===========================================================================

class TestCoverRetryIntegration:

    def _make_blind(self, device, responses):
        from custom_components.sinum.cover import SinumBlindCover
        client, session = _make_client(responses)
        c = _coordinator_with_client(client, virtual={device["id"]: device})
        entity = _wire(SinumBlindCover(c, device["id"], "e"))
        return entity, c, session

    @pytest.mark.asyncio
    async def test_open_cover_succeeds_after_408_retry(self):
        device = {"id": 14, "type": "blind_controller_integrator", "state": "closed",
                  "last_set_target_opening": 0}
        first = _resp(408, {})
        second = _resp(200, {"data": {"id": 14, "last_set_target_opening": 100}})
        entity, c, session = self._make_blind(device, [first, second])

        with _patches()[0], _patches()[1]:
            await entity.async_open_cover()

        assert session.request.call_count == 2
        assert c.virtual_devices[14]["last_set_target_opening"] == 100

    @pytest.mark.asyncio
    async def test_set_position_succeeds_after_408_retry(self):
        device = {"id": 14, "type": "blind_controller_integrator", "state": "open",
                  "last_set_target_opening": 100}
        first = _resp(408, {})
        second = _resp(200, {"data": {"id": 14, "last_set_target_opening": 50}})
        entity, c, session = self._make_blind(device, [first, second])

        with _patches()[0], _patches()[1]:
            await entity.async_set_cover_position(position=50)

        assert session.request.call_count == 2
        assert c.virtual_devices[14]["last_set_target_opening"] == 50


# ===========================================================================
# Light — bus dimmer
# ===========================================================================

class TestLightRetryIntegration:

    def _make_dimmer(self, device, responses, bus="wtp"):
        from custom_components.sinum.light import SinumBusDimmerLight
        client, session = _make_client(responses)
        store = {device["id"]: device}
        c = _coordinator_with_client(
            client,
            wtp=store if bus == "wtp" else {},
            sbus=store if bus == "sbus" else {},
        )
        entity = _wire(SinumBusDimmerLight(c, device["id"], "e", bus))
        return entity, c, session

    @pytest.mark.asyncio
    async def test_turn_on_succeeds_after_408_retry(self):
        device = {"id": 12, "type": "dimmer", "state": False, "target_level": 0}
        first = _resp(408, {})
        second = _resp(200, {"data": {"id": 12, "state": True, "target_level": 100}})
        entity, c, session = self._make_dimmer(device, [first, second], "wtp")

        with _patches()[0], _patches()[1]:
            await entity.async_turn_on()

        assert session.request.call_count == 2
        assert c.wtp_devices[12]["state"] is True

    @pytest.mark.asyncio
    async def test_turn_off_succeeds_after_408_retry(self):
        device = {"id": 12, "type": "dimmer", "state": True, "target_level": 80}
        first = _resp(408, {})
        second = _resp(200, {"data": {"id": 12, "state": False, "target_level": 0}})
        entity, c, session = self._make_dimmer(device, [first, second], "wtp")

        with _patches()[0], _patches()[1]:
            await entity.async_turn_off()

        assert session.request.call_count == 2
        assert c.wtp_devices[12]["state"] is False


# ===========================================================================
# GET requests also retry on 408 — prevents entities going unavailable
# on transient bus-busy conditions during coordinator polling
# ===========================================================================

class TestGetRetry:

    @pytest.mark.asyncio
    async def test_get_virtual_devices_retries_on_408_and_succeeds(self):
        """Coordinator poll retries on 408 so entities stay available on transient bus busy."""
        first = _resp(408, {})
        second = _resp(200, {"data": [{"id": 1, "type": "thermostat", "mode": "heating"}]})
        client, session = _make_client([first, second])

        with _patches()[0], _patches()[1]:
            result = await client.get_virtual_devices()

        assert session.request.call_count == 2
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_virtual_devices_raises_only_when_both_408(self):
        """Only if both the poll and retry return 408 do entities go unavailable."""
        from custom_components.sinum.api import SinumConnectionError
        client, session = _make_client([_resp(408, {}), _resp(408, {})])

        with _patches()[0], _patches()[1], pytest.raises(SinumConnectionError):
            await client.get_virtual_devices()

        assert session.request.call_count == 2

    @pytest.mark.asyncio
    async def test_get_sbus_devices_retries_on_408_and_succeeds(self):
        first = _resp(408, {})
        second = _resp(200, {"data": [{"id": 5, "type": "fan_coil"}]})
        client, session = _make_client([first, second])

        with _patches()[0], _patches()[1]:
            result = await client.get_sbus_devices()

        assert session.request.call_count == 2
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_wtp_devices_retries_on_408_and_succeeds(self):
        first = _resp(408, {})
        second = _resp(200, {"data": [{"id": 3, "type": "relay"}]})
        client, session = _make_client([first, second])

        with _patches()[0], _patches()[1]:
            result = await client.get_wtp_devices()

        assert session.request.call_count == 2
        assert len(result) == 1
