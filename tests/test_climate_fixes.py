"""Tests for climate temperature fix: dynamic min/max, HomeAssistantError, 422 handling."""

from __future__ import annotations

import json as _json
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.sinum.api import SinumConnectionError
from custom_components.sinum.climate import SinumTemperatureRegulatorClimate, SinumThermostat
from custom_components.sinum.const import TEMP_MAX, TEMP_MIN


def _make_coordinator(virtual=None, wtp=None, sbus=None):
    c = MagicMock()
    c.virtual_devices = virtual or {}
    c.wtp_devices = wtp or {}
    c.sbus_devices = sbus or {}
    c.client = MagicMock()
    c.client.encode_temperature = lambda t: round(t * 10)
    c.client.decode_temperature = lambda r: r / 10
    c.client.patch_virtual_device = AsyncMock(return_value={})
    c.client.patch_wtp_device = AsyncMock(return_value={})
    c.client.patch_sbus_device = AsyncMock(return_value={})
    return c


def _wire(entity):
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    return entity


class TestSinumThermostatDynamicMinMax:
    def _make(self, device: dict):
        c = _make_coordinator(virtual={1: device})
        entity = _wire(SinumThermostat(c, 1, "e"))
        return entity, c

    def test_min_max_from_device_when_valid_range(self):
        """min/max read from API when max > min."""
        entity, _ = self._make(
            {"id": 1, "target_temperature_minimum": 50, "target_temperature_maximum": 250}
        )
        assert entity.min_temp == 5.0
        assert entity.max_temp == 25.0

    def test_min_max_fallback_when_min_equals_max(self):
        """When schedule-locked (min == max), use the actual values to prevent 'exceeds range' errors."""
        entity, _ = self._make(
            {"id": 1, "target_temperature_minimum": 50, "target_temperature_maximum": 50}
        )
        assert entity.min_temp == 5.0
        assert entity.max_temp == 5.0

    def test_min_max_fallback_when_missing(self):
        """Fallback when keys absent."""
        entity, _ = self._make({"id": 1})
        assert entity.min_temp == TEMP_MIN
        assert entity.max_temp == TEMP_MAX

    @pytest.mark.asyncio
    async def test_set_temperature_clamps_to_max(self):
        """Temperature above max is clamped to max before sending."""
        entity, c = self._make(
            {"id": 1, "target_temperature_minimum": 50, "target_temperature_maximum": 250}
        )
        # Try to set 30°C but max is 25°C
        await entity.async_set_temperature(temperature=30.0)
        raw = c.client.patch_virtual_device.await_args.args[1]["target_temperature"]
        assert raw == 250  # clamped to 25.0°C

    @pytest.mark.asyncio
    async def test_set_temperature_clamps_to_min(self):
        """Temperature below min is clamped to min before sending."""
        entity, c = self._make(
            {"id": 1, "target_temperature_minimum": 150, "target_temperature_maximum": 250}
        )
        await entity.async_set_temperature(temperature=10.0)
        raw = c.client.patch_virtual_device.await_args.args[1]["target_temperature"]
        assert raw == 150  # clamped to 15.0°C

    @pytest.mark.asyncio
    async def test_set_temperature_raises_ha_error_on_api_failure(self):
        """SinumConnectionError is converted to HomeAssistantError."""
        entity, c = self._make({"id": 1})
        c.client.patch_virtual_device = AsyncMock(
            side_effect=SinumConnectionError("Validation error")
        )
        with pytest.raises(HomeAssistantError, match="Cannot set temperature"):
            await entity.async_set_temperature(temperature=20.0)

    @pytest.mark.asyncio
    async def test_set_temperature_normal_within_range(self):
        """Normal temperature within range is sent correctly."""
        entity, c = self._make(
            {"id": 1, "target_temperature_minimum": 50, "target_temperature_maximum": 300}
        )
        c.client.patch_virtual_device = AsyncMock(return_value={"target_temperature": 210})
        await entity.async_set_temperature(temperature=21.0)
        raw = c.client.patch_virtual_device.await_args.args[1]["target_temperature"]
        assert raw == 210


class TestSinumTempRegClimateMinMax:
    def _make(self, device: dict, bus="wtp"):
        store = {1: device}
        c = _make_coordinator(
            wtp=store if bus == "wtp" else {}, sbus=store if bus == "sbus" else {}
        )
        entity = _wire(SinumTemperatureRegulatorClimate(c, 1, "e", bus=bus))
        return entity, c

    def test_min_max_from_wtp_device(self):
        entity, _ = self._make(
            {"id": 1, "target_temperature_minimum": 50, "target_temperature_maximum": 350}
        )
        assert entity.min_temp == 5.0
        assert entity.max_temp == 35.0

    def test_min_max_fallback_when_locked(self):
        """When locked (min == max), use actual values to prevent 'exceeds range' errors."""
        entity, _ = self._make(
            {"id": 1, "target_temperature_minimum": 50, "target_temperature_maximum": 50}
        )
        assert entity.min_temp == 5.0
        assert entity.max_temp == 5.0

    @pytest.mark.asyncio
    async def test_set_temperature_clamps_and_sends(self):
        entity, c = self._make(
            {"id": 1, "target_temperature_minimum": 50, "target_temperature_maximum": 250}
        )
        await entity.async_set_temperature(temperature=30.0)
        raw = c.client.patch_wtp_device.await_args.args[1]["target_temperature"]
        assert raw == 250

    @pytest.mark.asyncio
    async def test_set_temperature_raises_ha_error(self):
        entity, c = self._make({"id": 1})
        c.client.patch_wtp_device = AsyncMock(side_effect=SinumConnectionError("err"))
        with pytest.raises(HomeAssistantError):
            await entity.async_set_temperature(temperature=20.0)


class TestApiValidationError:
    """Test that 422 responses produce meaningful error messages."""

    @pytest.mark.asyncio
    async def test_422_extracts_field_error(self):

        from custom_components.sinum.api import SinumClient

        session = MagicMock()
        resp = MagicMock()
        resp.status = 422
        _body = {
            "error": {
                "errors": {
                    "target_temperature": {"id": 7250, "text": "Parameter exceeds maximum range"}
                },
                "message": {"text": "Validation failed"},
            }
        }
        resp.read = AsyncMock(return_value=_json.dumps(_body).encode())

        async def fake_request(*args, **kwargs):
            return resp

        session.request = fake_request

        client = SinumClient("10.0.0.1", session, api_token="tok")
        with pytest.raises(SinumConnectionError, match="Parameter exceeds maximum range"):
            await client.patch_virtual_device(9, {"target_temperature": 210})


class TestNotifyEntity:
    @pytest.mark.asyncio
    async def test_send_message_calls_api(self):
        from custom_components.sinum.notify import SinumNotifyEntity

        c = MagicMock()
        c.hub_info = {"name": "My Hub"}
        c.client = MagicMock()
        c.client.send_notification = AsyncMock()

        entity = SinumNotifyEntity(c, "entry_id")
        entity.hass = MagicMock()

        await entity.async_send_message("Hello world", title="Test")
        c.client.send_notification.assert_awaited_once_with(title="Test", message="Hello world")

    @pytest.mark.asyncio
    async def test_send_message_uses_default_title(self):
        from custom_components.sinum.notify import SinumNotifyEntity

        c = MagicMock()
        c.hub_info = {}
        c.client = MagicMock()
        c.client.send_notification = AsyncMock()

        entity = SinumNotifyEntity(c, "entry_id")
        entity.hass = MagicMock()

        await entity.async_send_message("Message without title")
        c.client.send_notification.assert_awaited_once_with(
            title="Sinum", message="Message without title"
        )

    @pytest.mark.asyncio
    async def test_async_setup_entry_creates_entity(self):
        from custom_components.sinum.notify import SinumNotifyEntity, async_setup_entry

        coordinator = MagicMock()
        coordinator.hub_info = {}
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "test"

        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        assert len(added) == 1
        assert isinstance(added[0], SinumNotifyEntity)

    def test_unique_id(self):
        from custom_components.sinum.notify import SinumNotifyEntity

        c = MagicMock()
        c.hub_info = {}
        entity = SinumNotifyEntity(c, "myentry")
        assert entity.unique_id == "myentry_notify"

    def test_icon(self):
        from custom_components.sinum.notify import SinumNotifyEntity

        c = MagicMock()
        c.hub_info = {}
        entity = SinumNotifyEntity(c, "e")
        assert entity.icon == "mdi:bell-ring"
