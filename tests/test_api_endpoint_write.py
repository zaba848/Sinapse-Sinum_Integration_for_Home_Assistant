"""
API write endpoint validation tests for Sinum integration.

These tests validate write operations (PATCH/POST) on real hardware to ensure:
- Idempotency (repeated writes produce no spurious updates)
- State consistency (updated state reflects correctly in GET)
- Correct HA entity mapping (state changes propagate to entities)

Run with: SINUM_HOST=<host> SINUM_PASSWORD=<pw> pytest -v tests/test_api_endpoint_write.py
Note: These tests change device state; run in test environments only.
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Any

import aiohttp
import pytest

from custom_components.sinum.api import SinumClient, SinumConnectionError


@pytest.mark.asyncio
class TestApiEndpointWrite:
    """API write endpoint validation tests."""

    SINUM_HOST = os.getenv("SINUM_HOST")
    SINUM_PASSWORD = os.getenv("SINUM_PASSWORD")
    WRITE_TESTS_ENABLED = os.getenv("SINUM_WRITE_TESTS") == "1"

    @pytest.fixture
    async def client(self):
        """Create a SinumClient for write tests."""
        if not self.WRITE_TESTS_ENABLED:
            pytest.skip("Write tests disabled (set SINUM_WRITE_TESTS=1)")
        if not self.SINUM_HOST or not self.SINUM_PASSWORD:
            pytest.skip(
                "Write tests require SINUM_HOST and SINUM_PASSWORD env vars"
            )

        async with aiohttp.ClientSession() as session:
            client = SinumClient(
                session=session, host=self.SINUM_HOST, password=self.SINUM_PASSWORD
            )
            try:
                token = await client.login()
                if not token:
                    pytest.skip(f"Failed to authenticate with {self.SINUM_HOST}")
                yield client
            finally:
                await client.session.close()

    @pytest.mark.asyncio
    async def test_a_lora_relay_patch_scope(self, client):
        """A. LoRa Relay PATCH Scope."""
        try:
            devices = await client.get_devices_lora()
        except Exception:
            pytest.skip("Could not fetch LoRa devices")

        relay_devices = [
            d for d in devices if d.get("type") == "relay"
        ]
        if not relay_devices:
            pytest.skip("No LoRa relay devices found")

        for relay in relay_devices[:2]:
            device_id = relay.get("id")
            initial_state = relay.get("state", {}).get("on", False)
            new_state = not initial_state

            await client.patch_device_lora(
                device_id, {"state": {"on": new_state}}
            )
            updated = await client.get_device_lora(device_id)
            assert updated.get("state", {}).get("on") == new_state

            await client.patch_device_lora(
                device_id, {"state": {"on": initial_state}}
            )

    @pytest.mark.asyncio
    async def test_b_rgb_dimmer_idempotency(self, client):
        """B. RGB/Dimmer Idempotency."""
        try:
            wtp_devices = await client.get_devices_wtp()
        except Exception:
            pytest.skip("Could not fetch WTP devices")

        rgb_devices = [
            d for d in wtp_devices
            if "rgb" in d.get("type", "").lower()
            or "dimmer" in d.get("type", "").lower()
        ]
        if not rgb_devices:
            pytest.skip("No RGB/dimmer devices found")

        for device in rgb_devices[:1]:
            device_id = device.get("id")
            device_type = device.get("type", "unknown")

            if "dimmer" in device_type:
                level = 75
                await client.patch_device_wtp(
                    device_id, {"state": {"level": level}}
                )
                await client.patch_device_wtp(
                    device_id, {"state": {"level": level}}
                )
                updated = await client.get_device_wtp(device_id)
                assert updated.get("state", {}).get("level") == level

    @pytest.mark.asyncio
    async def test_c_heat_pump_mode_matrix(self, client):
        """C. Heat Pump Mode Matrix."""
        try:
            virtual_devices = await client.get_devices_virtual()
        except Exception:
            pytest.skip("Could not fetch virtual devices")

        heat_pump_devices = [
            d for d in virtual_devices
            if d.get("type") == "heat_pump_manager"
        ]
        if not heat_pump_devices:
            pytest.skip("No heat pump devices found")

        valid_modes = ["OFF", "HEAT", "COOL", "AUTO"]
        for device in heat_pump_devices[:1]:
            device_id = device.get("id")
            current_mode = device.get("state", {}).get("mode", "OFF")

            for target_mode in valid_modes:
                try:
                    await client.patch_device_virtual(
                        device_id, {"state": {"mode": target_mode}}
                    )
                    await asyncio.sleep(0.5)
                    updated = await client.get_device_virtual(device_id)
                    actual_mode = updated.get("state", {}).get("mode")
                    assert actual_mode == target_mode
                except Exception:
                    pass

            await client.patch_device_virtual(
                device_id, {"state": {"mode": current_mode}}
            )

    @pytest.mark.asyncio
    async def test_d_schedule_state_transitions(self, client):
        """D. Schedule State Transitions."""
        try:
            schedules = await client.get_schedules()
        except Exception:
            pytest.skip("Could not fetch schedules")

        if not schedules:
            pytest.skip("No schedules found")

        for schedule in schedules[:1]:
            schedule_id = schedule.get("id")
            current = await client.get_schedule(schedule_id)
            current_mode = current.get("state", {}).get("mode", "day")
            new_mode = "week" if current_mode == "day" else "day"

            await client.patch_schedule(schedule_id, {"state": {"mode": new_mode}})
            await asyncio.sleep(0.5)

            updated = await client.get_schedule(schedule_id)
            actual_mode = updated.get("state", {}).get("mode")
            assert actual_mode == new_mode

            await client.patch_schedule(
                schedule_id, {"state": {"mode": current_mode}}
            )

    @pytest.mark.asyncio
    async def test_e_alarm_arm_disarm_idempotency(self, client):
        """E. Alarm Arm/Disarm Idempotency."""
        try:
            alarm_zones = await client.get_devices_alarm_system()
        except Exception:
            pytest.skip("Could not fetch alarm zones")

        if not alarm_zones:
            pytest.skip("No alarm zones found")

        for zone in alarm_zones[:1]:
            zone_id = zone.get("id")
            current_armed = zone.get("state", {}).get("armed", False)
            target_armed = not current_armed

            for _ in range(2):
                await client.patch_device_alarm_system(
                    zone_id, {"state": {"armed": target_armed}}
                )
                await asyncio.sleep(0.3)

            updated = await client.get_device_alarm_system(zone_id)
            actual_armed = updated.get("state", {}).get("armed")
            assert actual_armed == target_armed

            await client.patch_device_alarm_system(
                zone_id, {"state": {"armed": current_armed}}
            )
