"""Live API write validation tests for Sinum integration.

These tests intentionally change real hub state. They are skipped unless
SINUM_WRITE_TESTS=1 and live credentials are provided.

Run with:
    SINUM_WRITE_TESTS=1 SINUM_HOST=<host> SINUM_PASSWORD=<pw> \
      pytest -v tests/test_api_endpoint_write.py
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import aiohttp
import pytest

from custom_components.sinum.api import SinumClient


def _bool_state(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(value.get("on", value.get("state", False)))
    return bool(value)


@pytest.mark.asyncio
class TestApiEndpointWrite:
    """API write endpoint validation tests."""

    SINUM_HOST = os.getenv("SINUM_HOST")
    SINUM_USERNAME = os.getenv("SINUM_USERNAME", "admin")
    SINUM_PASSWORD = os.getenv("SINUM_PASSWORD")
    WRITE_TESTS_ENABLED = os.getenv("SINUM_WRITE_TESTS") == "1"

    @pytest.fixture
    async def client(self):
        if not self.WRITE_TESTS_ENABLED:
            pytest.skip("Write tests disabled (set SINUM_WRITE_TESTS=1)")
        if not self.SINUM_HOST or not self.SINUM_PASSWORD:
            pytest.skip("Write tests require SINUM_HOST and SINUM_PASSWORD env vars")

        async with aiohttp.ClientSession() as session:
            client = SinumClient(
                self.SINUM_HOST,
                session,
                username=self.SINUM_USERNAME,
                password=self.SINUM_PASSWORD,
            )
            try:
                await client.login()
            except Exception as exc:
                pytest.skip(f"Failed to authenticate with {self.SINUM_HOST}: {exc}")
            yield client

    async def test_a_lora_relay_patch_scope(self, client: SinumClient) -> None:
        """A. LoRa relay PATCH scope."""
        try:
            devices = await client.get_lora_devices()
        except Exception:
            pytest.skip("Could not fetch LoRa devices")

        relays = [device for device in devices if device.get("type") == "relay"]
        if not relays:
            pytest.skip("No LoRa relay devices found")

        for relay in relays[:2]:
            device_id = int(relay["id"])
            initial_state = _bool_state(relay.get("state"))
            target_state = not initial_state

            await client.patch_lora_device(device_id, {"state": target_state})
            updated = await client.get_lora_device(device_id)
            assert _bool_state(updated.get("state")) is target_state

            await client.patch_lora_device(device_id, {"state": initial_state})

    async def test_b_sbus_dimmer_idempotency(self, client: SinumClient) -> None:
        """B. SBUS dimmer idempotency."""
        try:
            sbus_devices = await client.get_sbus_devices()
        except Exception:
            pytest.skip("Could not fetch SBUS devices")

        dimmers = [device for device in sbus_devices if device.get("type") == "dimmer"]
        if not dimmers:
            pytest.skip("No SBUS dimmer devices found")

        device = dimmers[0]
        device_id = int(device["id"])
        original_level = int(device.get("target_level", 50))
        test_level = 60 if original_level != 60 else 65

        await client.patch_sbus_device(device_id, {"target_level": test_level})
        await client.patch_sbus_device(device_id, {"target_level": test_level})
        updated = await client.get_sbus_device(device_id)
        assert updated.get("target_level") == test_level

        await client.patch_sbus_device(device_id, {"target_level": original_level})

    async def test_c_heat_pump_mode_matrix(self, client: SinumClient) -> None:
        """C. Heat pump manager mode matrix."""
        try:
            virtual_devices = await client.get_virtual_devices()
        except Exception:
            pytest.skip("Could not fetch virtual devices")

        heat_pumps = [
            device for device in virtual_devices if device.get("type") == "heat_pump_manager"
        ]
        if not heat_pumps:
            pytest.skip("No heat_pump_manager devices found")

        device = heat_pumps[0]
        device_id = int(device["id"])
        original_mode = device.get("work_mode", "cooling")
        original_enabled = device.get("enabled", True)

        for mode in ("heating", "cooling", "automatic"):
            await client.patch_virtual_device(device_id, {"work_mode": mode, "enabled": True})
            await asyncio.sleep(0.3)
            updated = await client.get_virtual_device(device_id)
            assert updated.get("work_mode") == mode

        await client.patch_virtual_device(
            device_id, {"work_mode": original_mode, "enabled": original_enabled}
        )

    async def test_d_schedule_state_transitions(self, client: SinumClient) -> None:
        """D. Schedule setpoint transition."""
        try:
            schedules = await client.get_schedules()
        except Exception:
            pytest.skip("Could not fetch schedules")

        if not schedules:
            pytest.skip("No schedules found")

        schedule = schedules[0]
        schedule_id = int(schedule["id"])
        detail = await client.get_schedule(schedule_id)
        fallback = detail.get("fallback")
        original_temp = fallback.get("target_temperature") if isinstance(fallback, dict) else None
        if original_temp is None:
            pytest.skip("Schedule has no fallback.target_temperature")

        test_temp = original_temp + 10
        await client.patch_schedule(schedule_id, {"fallback": {"target_temperature": test_temp}})
        updated = await client.get_schedule(schedule_id)
        assert (updated.get("fallback") or {}).get("target_temperature") == test_temp

        await client.patch_schedule(
            schedule_id, {"fallback": {"target_temperature": original_temp}}
        )

    async def test_e_alarm_arm_disarm_idempotency(self, client: SinumClient) -> None:
        """E. Alarm arm/disarm idempotency, gated by explicit PIN env."""
        pin = os.getenv("SINUM_ALARM_TEST_PIN")
        if not pin:
            pytest.skip("Alarm write test requires SINUM_ALARM_TEST_PIN")

        try:
            zones = await client.get_alarm_devices()
        except Exception:
            pytest.skip("Could not fetch alarm zones")

        disarmed = [zone for zone in zones if not zone.get("armed")]
        if not disarmed:
            pytest.skip("No disarmed alarm zone available for safe arm/disarm test")

        zone = disarmed[0]
        zone_id = int(zone["id"])

        await client.command_alarm_device(zone_id, "arm", {"arm": pin})
        await asyncio.sleep(0.5)
        await client.command_alarm_device(zone_id, "arm", {"arm": pin})
        updated = await client.get_alarm_device(zone_id)
        assert updated.get("armed") is True

        await client.command_alarm_device(zone_id, "disarm", {"disarm": pin})
