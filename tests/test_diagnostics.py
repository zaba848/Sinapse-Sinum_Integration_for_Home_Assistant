"""Tests for diagnostics module."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.sinum.diagnostics import (
    _sanitize_device,
    async_get_config_entry_diagnostics,
)
from custom_components.sinum.const import CONF_API_TOKEN, CONF_PASSWORD


def _make_entry(data: dict, runtime_data=None) -> MagicMock:
    entry = MagicMock()
    entry.data = data
    entry.runtime_data = runtime_data or _make_coordinator()
    return entry


def _make_coordinator(
    virtual=None, wtp=None, sbus=None, parent_devices=None, floors=None
) -> MagicMock:
    coord = MagicMock()
    coord.virtual_devices = virtual or {}
    coord.wtp_devices = wtp or {}
    coord.sbus_devices = sbus or {}
    coord.parent_devices = parent_devices or []
    coord.floors = floors or {}
    coord.hub_info = {"version": "1.24.0"}
    coord.rooms = []
    coord.mqtt_bridge = None
    return coord


class TestSanitizeDevice:
    def test_removes_underscore_keys(self):
        device = {"id": 1, "name": "Test", "_room": "Living Room", "_area": "Floor/Room"}
        result = _sanitize_device(device)
        assert "_room" not in result
        assert "_area" not in result
        assert result["id"] == 1
        assert result["name"] == "Test"

    def test_keeps_non_underscore_keys(self):
        device = {"type": "thermostat", "temperature": 210, "state": True}
        result = _sanitize_device(device)
        assert result == {"type": "thermostat", "temperature": 210, "state": True}

    def test_empty_device(self):
        assert _sanitize_device({}) == {}


class TestDiagnosticsRedaction:
    @pytest.mark.asyncio
    async def test_api_token_redacted(self):
        entry = _make_entry({CONF_API_TOKEN: "secret-token-123", "host": "10.0.0.1"})
        result = await async_get_config_entry_diagnostics(MagicMock(), entry)
        assert result["entry"][CONF_API_TOKEN] == "**REDACTED**"
        assert result["entry"]["host"] == "10.0.0.1"

    @pytest.mark.asyncio
    async def test_password_redacted(self):
        entry = _make_entry({CONF_PASSWORD: "my-password", "host": "10.0.0.1"})
        result = await async_get_config_entry_diagnostics(MagicMock(), entry)
        assert result["entry"][CONF_PASSWORD] == "**REDACTED**"

    @pytest.mark.asyncio
    async def test_no_redaction_when_keys_absent(self):
        entry = _make_entry({"host": "10.0.0.1", "auth_mode": "token"})
        result = await async_get_config_entry_diagnostics(MagicMock(), entry)
        assert CONF_API_TOKEN not in result["entry"]
        assert CONF_PASSWORD not in result["entry"]

    @pytest.mark.asyncio
    async def test_all_device_stores_included(self):
        coord = _make_coordinator(
            virtual={10: {"id": 10, "type": "thermostat"}},
            wtp={20: {"id": 20, "type": "temperature_sensor"}},
            sbus={30: {"id": 30, "type": "relay"}},
        )
        entry = _make_entry({"host": "10.0.0.1"}, runtime_data=coord)
        result = await async_get_config_entry_diagnostics(MagicMock(), entry)

        assert "10" in result["virtual_devices"]
        assert "20" in result["wtp_devices"]
        assert "30" in result["sbus_devices"]
        assert result["virtual_count"] == 1
        assert result["wtp_count"] == 1
        assert result["sbus_count"] == 1

    @pytest.mark.asyncio
    async def test_mqtt_enabled_flag(self):
        coord = _make_coordinator()
        coord.mqtt_bridge = MagicMock()  # bridge present = MQTT enabled
        entry = _make_entry({"host": "10.0.0.1"}, runtime_data=coord)
        result = await async_get_config_entry_diagnostics(MagicMock(), entry)
        assert result["mqtt_enabled"] is True

    @pytest.mark.asyncio
    async def test_mqtt_disabled_when_no_bridge(self):
        coord = _make_coordinator()
        coord.mqtt_bridge = None
        entry = _make_entry({"host": "10.0.0.1"}, runtime_data=coord)
        result = await async_get_config_entry_diagnostics(MagicMock(), entry)
        assert result["mqtt_enabled"] is False

    @pytest.mark.asyncio
    async def test_parent_devices_sanitized(self):
        coord = _make_coordinator(
            parent_devices=[{"id": 1, "name": "Gateway", "_internal": "removed"}]
        )
        entry = _make_entry({"host": "10.0.0.1"}, runtime_data=coord)
        result = await async_get_config_entry_diagnostics(MagicMock(), entry)
        assert len(result["parent_devices"]) == 1
        assert "_internal" not in result["parent_devices"][0]

    @pytest.mark.asyncio
    async def test_floors_included(self):
        coord = _make_coordinator(floors={1: {"id": 1, "name": "Ground"}})
        entry = _make_entry({"host": "10.0.0.1"}, runtime_data=coord)
        result = await async_get_config_entry_diagnostics(MagicMock(), entry)
        assert "1" in result["floors"]
