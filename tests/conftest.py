"""Shared pytest fixtures for Sinapse tests."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "sinum_devices.json"


@pytest.fixture(name="fixtures")
def fixture_data() -> dict[str, Any]:
    return json.loads(FIXTURES_PATH.read_text())


@pytest.fixture(name="mock_client")
def fixture_mock_client(fixtures: dict[str, Any]) -> MagicMock:
    client = MagicMock()
    client.get_rooms = AsyncMock(return_value=fixtures["rooms"])
    client.get_hub_info = AsyncMock(return_value={"version": "1.24.0-alpha.1", "uptime": 123})
    client.get_lua_hub_info = AsyncMock(return_value={})
    client.get_floors = AsyncMock(return_value=[])
    client.get_parent_devices = AsyncMock(return_value=[])
    client.get_virtual_devices = AsyncMock(
        return_value=[
            dict(fixtures["virtual_thermostat"]),
            dict(fixtures["virtual_light"]),
            dict(fixtures["virtual_relay"]),
            dict(fixtures["virtual_blind"]),
        ]
    )
    client.get_wtp_devices = AsyncMock(
        return_value=[
            dict(fixtures["wtp_temp"]),
            dict(fixtures["wtp_motion"]),
        ]
    )
    client.get_sbus_devices = AsyncMock(return_value=[])
    client.get_lora_devices = AsyncMock(return_value=[])
    client.get_virtual_device = AsyncMock(side_effect=_virtual_device_side_effect(fixtures))
    client.get_wtp_device = AsyncMock(side_effect=_wtp_device_side_effect(fixtures))
    client.get_sbus_device = AsyncMock(return_value={})
    client.get_lora_device = AsyncMock(return_value={})
    client.patch_virtual_device = AsyncMock(return_value={})
    client.get_scenes = AsyncMock(return_value=fixtures["scenes"])
    client.run_scene = AsyncMock(return_value=None)
    client.get_variables = AsyncMock(return_value=fixtures["variables"])
    client.set_variable = AsyncMock(return_value={"id": 1, "value": 50})
    client.get_weather = AsyncMock(return_value=fixtures["weather"])
    client.get_energy = AsyncMock(return_value=fixtures["energy"])
    client.get_schedules = AsyncMock(return_value=fixtures["schedules"])
    client.get_alarm_devices = AsyncMock(return_value=fixtures["alarm_devices"])
    client.login = AsyncMock(return_value=None)
    client.test_connection = AsyncMock(return_value=None)
    client.decode_temperature = lambda raw: raw / 10
    client.encode_temperature = lambda c: round(c * 10)
    return client


def _virtual_device_side_effect(fixtures: dict[str, Any]):
    mapping = {
        10: fixtures["virtual_thermostat"],
        11: fixtures["virtual_light"],
        12: fixtures["virtual_relay"],
        13: fixtures["virtual_blind"],
    }

    async def _side_effect(device_id: int) -> dict[str, Any]:
        return dict(mapping[device_id])

    return _side_effect


def _wtp_device_side_effect(fixtures: dict[str, Any]):
    mapping = {
        20: fixtures["wtp_temp"],
        21: fixtures["wtp_motion"],
    }

    async def _side_effect(device_id: int) -> dict[str, Any]:
        return dict(mapping[device_id])

    return _side_effect
