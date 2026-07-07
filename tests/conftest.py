"""Shared pytest fixtures for Sinapse tests."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, create_autospec

import pytest

from custom_components.sinum.api import SinumClient
from custom_components.sinum.const import CONF_API_TOKEN, DOMAIN

# turbojpeg is an optional C extension used by the HA camera platform for JPEG
# re-encoding. It is not available in the CI/test environment; provide a stub so
# camera-related tests can import homeassistant.components.camera without error.
if "turbojpeg" not in sys.modules:
    _tj_stub = types.ModuleType("turbojpeg")

    class _TurboJPEGStub:
        def __init__(self, *a: object, **kw: object) -> None:
            pass

    _tj_stub.TurboJPEG = _TurboJPEGStub  # type: ignore[attr-defined]
    sys.modules["turbojpeg"] = _tj_stub

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "sinum_devices.json"


@pytest.fixture(name="fixtures")
def fixture_data() -> dict[str, Any]:
    return json.loads(FIXTURES_PATH.read_text())


@pytest.fixture(name="mock_client")
def fixture_mock_client(fixtures: dict[str, Any]) -> MagicMock:
    # Autospec'd against SinumClient so every real method (including ones no
    # single test configures explicitly) is a proper AsyncMock/MagicMock
    # matching its real signature, rather than silently returning a bare
    # MagicMock that blows up with "object can't be awaited".
    client = create_autospec(SinumClient, instance=True)
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
    client.get_automations = AsyncMock(return_value=[])
    client.get_alarm_devices = AsyncMock(return_value=fixtures["alarm_devices"])
    client.login = AsyncMock(return_value=None)
    client.test_connection = AsyncMock(return_value=None)
    # Explicit return_value (rather than relying on the autospec default) for
    # every async method the sensor platform's optional-sensor factories
    # await during setup — under this environment's asyncio eager-task
    # scheduling, an unconfigured autospec'd AsyncMock can resolve to a
    # still-pending coroutine instead of its return value, and these call
    # sites only catch SinumConnectionError/SinumNotSupportedError, so
    # anything else crashes the whole sensor platform setup.
    client.get_energy_center_summary = AsyncMock(return_value={})
    client.get_energy_center_flow_monitor = AsyncMock(return_value={})
    client.get_energy_center_consumption = AsyncMock(return_value={})
    client.get_energy_center_production = AsyncMock(return_value={})
    client.get_energy_center_storage = AsyncMock(return_value={})
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


@pytest.fixture(name="mock_config_entry")
def fixture_mock_config_entry(hass: Any) -> Any:
    """Return a mock config entry."""

    def add_to_hass_impl(hass_instance: Any) -> None:
        """Add entry to hass config_entries."""
        hass_instance.config_entries._entries[entry.entry_id] = entry

    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.domain = DOMAIN
    entry.data = {"host": "192.168.1.100", "api_token": "test_token"}
    entry.options = {}
    entry.add_to_hass = lambda h: add_to_hass_impl(h)
    entry.async_on_unload = MagicMock(return_value=lambda: None)
    return entry


@pytest.fixture(name="mock_coordinator")
def fixture_mock_coordinator(mock_client: MagicMock) -> MagicMock:
    """Return a mock coordinator."""
    coordinator = MagicMock()
    coordinator.data = {
        "devices": [],
        "rooms": [],
        "floors": [],
        "scenes": [],
        "variables": [],
        "weather": {},
        "energy": {},
        "schedules": [],
        "alarm_devices": [],
    }
    coordinator.client = mock_client
    coordinator.hass = MagicMock()
    coordinator.last_update_success = True
    coordinator.get_motion_event = MagicMock(return_value=None)
    coordinator.dispatch_motion_detected = MagicMock()
    return coordinator
