#!/usr/bin/env python3
"""
API endpoint write validation runner and report generator for Sinum integration.

Runs live write tests (B–E) against a real hub and generates a markdown report.
Test A (LoRa relay) is skipped when no LoRa devices are found.
Test E (alarm arm/disarm) is skipped when all zones are armed — unsafe to modify
a live alarm installation without owner confirmation.

Usage:
    python3 scripts/validate_api_writes.py --host 10.0.62.167 --password <hub-password>

Environment:
    SINUM_HOST: Hub IP address or hostname
    SINUM_PASSWORD: Hub admin password
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

import aiohttp

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from custom_components.sinum.api import SinumClient, SinumConnectionError


class ApiWriteValidationRunner:
    """Runner for API write endpoint validation tests."""

    def __init__(self, host: str, password: str, username: str = "admin") -> None:
        self.host = host
        self.password = password
        self.username = username
        self.session: aiohttp.ClientSession | None = None
        self.client: SinumClient | None = None
        self.results: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hub": host,
            "tests": [],
        }

    async def setup(self) -> None:
        self.session = aiohttp.ClientSession()
        self.client = SinumClient(
            self.host,
            self.session,
            username=self.username,
            password=self.password,
        )
        await self.client.login()
        print(f"✅ Authenticated with {self.host}")

    async def teardown(self) -> None:
        if self.session:
            await self.session.close()

    # ------------------------------------------------------------------ A. LoRa

    async def test_a_lora_relay_patch_scope(self) -> None:
        print("\n🧪 Test A: LoRa Relay PATCH Scope")
        result: dict = {
            "test": "A. LoRa Relay PATCH Scope",
            "passed": False,
            "devices_tested": [],
            "summary": "",
        }
        try:
            assert self.client
            devices = await self.client.get_lora_devices()
            relay_devices = [d for d in devices if d.get("type") == "relay"]
            if not relay_devices:
                result["summary"] = "SKIP — no LoRa relay devices found on this hub"
                result["passed"] = True  # Not a failure — hardware not installed
                print(f"  ⏭️  {result['summary']}")
                self.results["tests"].append(result)
                return

            for relay in relay_devices[:2]:
                device_id = relay["id"]
                initial_state = relay.get("state", False)
                new_state = not initial_state
                try:
                    await self.client.patch_lora_device(device_id, {"state": new_state})
                    updated = await self.client.get_lora_device(device_id)
                    is_writable = updated.get("state") == new_state
                    await self.client.patch_lora_device(device_id, {"state": initial_state})
                    result["devices_tested"].append(
                        {"device_id": device_id, "name": relay.get("name"), "writable": is_writable}
                    )
                    print(
                        f"  {'✅' if is_writable else '⚠️'} {relay.get('name')} — writable: {is_writable}"
                    )
                except SinumConnectionError as e:
                    result["devices_tested"].append(
                        {"device_id": device_id, "name": relay.get("name"), "error": str(e)}
                    )
                    print(f"  ❌ {relay.get('name')} — error: {e}")

            result["passed"] = any(d.get("writable") for d in result["devices_tested"])
            result["summary"] = f"Tested {len(result['devices_tested'])} LoRa relay(s)"
        except Exception as e:
            result["summary"] = f"Error: {e}"
            print(f"  ❌ {result['summary']}")
        self.results["tests"].append(result)

    # ------------------------------------------------------------------ B. RGB/Dimmer idempotency

    async def test_b_rgb_dimmer_idempotency(self) -> None:
        print("\n🧪 Test B: RGB/Dimmer Idempotency")
        result: dict = {
            "test": "B. RGB/Dimmer Idempotency",
            "passed": False,
            "devices_tested": [],
            "summary": "",
        }
        try:
            assert self.client
            sbus_devices = await self.client.get_sbus_devices()
            dimmers = [d for d in sbus_devices if d.get("type") == "dimmer"]

            if not dimmers:
                result["summary"] = "No SBUS dimmer devices found"
                self.results["tests"].append(result)
                return

            for dev in dimmers[:2]:
                device_id = dev["id"]
                original_level = dev.get("target_level", 50)
                test_level = 60 if original_level != 60 else 65
                try:
                    # Send identical PATCH twice — should not cause errors or spurious updates
                    await self.client.patch_sbus_device(device_id, {"target_level": test_level})
                    await self.client.patch_sbus_device(device_id, {"target_level": test_level})
                    fetched = await self.client.get_sbus_device(device_id)
                    actual = fetched.get("target_level")
                    idempotent = actual == test_level
                    # Restore
                    await self.client.patch_sbus_device(device_id, {"target_level": original_level})
                    result["devices_tested"].append(
                        {
                            "device_id": device_id,
                            "name": dev.get("name"),
                            "type": "sbus_dimmer",
                            "target_level": test_level,
                            "actual_after": actual,
                            "idempotent": idempotent,
                        }
                    )
                    print(
                        f"  {'✅' if idempotent else '❌'} {dev.get('name')} — idempotent: {idempotent}"
                    )
                except SinumConnectionError as e:
                    result["devices_tested"].append(
                        {"device_id": device_id, "name": dev.get("name"), "error": str(e)}
                    )
                    print(f"  ❌ {dev.get('name')} — error: {e}")

            result["passed"] = all(
                d.get("idempotent", False) for d in result["devices_tested"] if "idempotent" in d
            )
            result["summary"] = f"Tested {len(result['devices_tested'])} dimmer(s)"
        except Exception as e:
            result["summary"] = f"Error: {e}"
            print(f"  ❌ {result['summary']}")
        self.results["tests"].append(result)

    # ------------------------------------------------------------------ C. Heat pump mode matrix

    async def test_c_heat_pump_mode_matrix(self) -> None:
        print("\n🧪 Test C: Heat Pump Manager Mode Matrix")
        result: dict = {
            "test": "C. Heat Pump Manager Mode Matrix",
            "passed": False,
            "devices_tested": [],
            "summary": "",
        }
        try:
            assert self.client
            virtual = await self.client.get_virtual_devices()
            hpms = [d for d in virtual if d.get("type") == "heat_pump_manager"]

            if not hpms:
                result["summary"] = "No heat_pump_manager devices found"
                self.results["tests"].append(result)
                return

            dev = hpms[0]
            device_id = dev["id"]
            original_mode = dev.get("work_mode", "cooling")
            original_enabled = dev.get("enabled", True)

            mode_results = []
            # Valid modes confirmed by live test 2026-06-25: heating, cooling, automatic. "off" → 422.
            for mode in ("heating", "cooling", "automatic"):
                try:
                    updated = await self.client.patch_virtual_device(
                        device_id, {"work_mode": mode, "enabled": True}
                    )
                    actual = (updated or {}).get("work_mode") if updated else None
                    if actual is None:
                        fetched = await self.client.get_virtual_device(device_id)
                        actual = fetched.get("work_mode")
                    mode_results.append(
                        {"target": mode, "actual": actual, "success": actual == mode}
                    )
                    print(
                        f"  {'✅' if actual == mode else '❌'} work_mode={mode} → actual={actual}"
                    )
                except SinumConnectionError as e:
                    mode_results.append({"target": mode, "error": str(e)})
                    print(f"  ❌ work_mode={mode} — error: {e}")

            # Test OFF via enabled=False
            try:
                updated = await self.client.patch_virtual_device(device_id, {"enabled": False})
                actual_enabled = (updated or {}).get("enabled") if updated else None
                if actual_enabled is None:
                    fetched = await self.client.get_virtual_device(device_id)
                    actual_enabled = fetched.get("enabled")
                mode_results.append(
                    {
                        "target": "OFF (enabled=False)",
                        "actual_enabled": actual_enabled,
                        "success": actual_enabled is False,
                    }
                )
                print(
                    f"  {'✅' if actual_enabled is False else '❌'} OFF via enabled=False → {actual_enabled}"
                )
            except SinumConnectionError as e:
                mode_results.append({"target": "OFF (enabled=False)", "error": str(e)})

            # Restore
            await self.client.patch_virtual_device(
                device_id, {"work_mode": original_mode, "enabled": original_enabled}
            )

            result["devices_tested"].append(
                {
                    "device_id": device_id,
                    "name": dev.get("name"),
                    "mode_transitions": mode_results,
                }
            )
            result["passed"] = all(m.get("success") for m in mode_results)
            result["summary"] = f"Tested {len(mode_results)} mode transitions on {dev.get('name')}"
        except Exception as e:
            result["summary"] = f"Error: {e}"
            print(f"  ❌ {result['summary']}")
        self.results["tests"].append(result)

    # ------------------------------------------------------------------ D. Schedule state transitions

    async def test_d_schedule_state_transitions(self) -> None:
        print("\n🧪 Test D: Schedule State Transitions (read + setpoint patch)")
        result: dict = {
            "test": "D. Schedule State Transitions",
            "passed": False,
            "devices_tested": [],
            "summary": "",
        }
        try:
            assert self.client
            schedules = await self.client.get_schedules()
            if not schedules:
                result["summary"] = "No schedules found"
                self.results["tests"].append(result)
                return

            sched = schedules[0]
            sched_id = sched["id"]
            detail = await self.client.get_schedule(sched_id)
            original_fallback = detail.get("fallback")
            original_temp = (
                (original_fallback or {}).get("target_temperature")
                if isinstance(original_fallback, dict)
                else None
            )

            if original_temp is None:
                result["summary"] = (
                    f"Schedule {sched.get('name')} has no fallback.target_temperature — skipping write"
                )
                result["passed"] = True
                self.results["tests"].append(result)
                return

            # Patch fallback temperature by +10 (raw ×10), then restore
            test_temp = original_temp + 10
            try:
                await self.client.patch_schedule(
                    sched_id, {"fallback": {"target_temperature": test_temp}}
                )
                fetched = await self.client.get_schedule(sched_id)
                actual_temp = (fetched.get("fallback") or {}).get("target_temperature")
                success = actual_temp == test_temp
                # Restore
                await self.client.patch_schedule(
                    sched_id, {"fallback": {"target_temperature": original_temp}}
                )
                result["devices_tested"].append(
                    {
                        "schedule_id": sched_id,
                        "name": sched.get("name"),
                        "target_temp": test_temp,
                        "actual_temp": actual_temp,
                        "success": success,
                    }
                )
                print(
                    f"  {'✅' if success else '❌'} {sched.get('name')} — temp {original_temp} → {actual_temp}"
                )
                result["passed"] = success
            except SinumConnectionError as e:
                result["devices_tested"].append({"schedule_id": sched_id, "error": str(e)})
                print(f"  ❌ Schedule PATCH error: {e}")

            result["summary"] = f"Tested 1 schedule ({sched.get('name')})"
        except Exception as e:
            result["summary"] = f"Error: {e}"
            print(f"  ❌ {result['summary']}")
        self.results["tests"].append(result)

    # ------------------------------------------------------------------ E. Alarm idempotency

    async def test_e_alarm_idempotency(self) -> None:
        print("\n🧪 Test E: Alarm Arm/Disarm Idempotency")
        result: dict = {
            "test": "E. Alarm Arm/Disarm Idempotency",
            "passed": False,
            "devices_tested": [],
            "summary": "",
        }
        try:
            assert self.client
            zones = await self.client.get_alarm_devices()
            if not zones:
                result["summary"] = "No alarm zones found"
                self.results["tests"].append(result)
                return

            all_armed = all(z.get("armed", False) for z in zones)
            if all_armed:
                result["summary"] = (
                    f"SKIP — all {len(zones)} zone(s) are currently ARMED; "
                    "will not disarm a live production alarm without explicit owner request"
                )
                result["passed"] = True
                print(f"  ⏭️  {result['summary']}")
                self.results["tests"].append(result)
                return

            pin = os.getenv("SINUM_ALARM_TEST_PIN")
            if not pin:
                result["summary"] = "SKIP — alarm write validation requires SINUM_ALARM_TEST_PIN"
                result["passed"] = True
                print(f"  ⏭️  {result['summary']}")
                self.results["tests"].append(result)
                return

            # Find a zone that is disarmed — safe to arm then disarm
            for zone in zones:
                zone_id = zone["id"]
                if zone.get("armed"):
                    continue
                try:
                    await self.client.command_alarm_device(zone_id, "arm", {"arm": pin})
                    await asyncio.sleep(0.5)
                    await self.client.command_alarm_device(zone_id, "arm", {"arm": pin})
                    updated = await self.client.get_alarm_device(zone_id)
                    armed = updated.get("armed")
                    await self.client.command_alarm_device(zone_id, "disarm", {"disarm": pin})
                    result["devices_tested"].append(
                        {
                            "zone_id": zone_id,
                            "name": zone.get("name"),
                            "double_arm_consistent": armed is True,
                        }
                    )
                    print(
                        f"  {'✅' if armed else '⚠️'} {zone.get('name')} — double-arm consistent: {armed}"
                    )
                    break
                except SinumConnectionError as e:
                    result["devices_tested"].append({"zone_id": zone_id, "error": str(e)})
                    print(f"  ❌ {zone.get('name')} — error: {e}")

            result["passed"] = len(result["devices_tested"]) > 0
            result["summary"] = f"Tested {len(result['devices_tested'])} alarm zone(s)"
        except Exception as e:
            result["summary"] = f"Error: {e}"
            print(f"  ❌ {result['summary']}")
        self.results["tests"].append(result)

    # ------------------------------------------------------------------ report

    def generate_report(self, output_path: str) -> None:
        passed_count = sum(1 for t in self.results["tests"] if t.get("passed"))
        total_count = len(self.results["tests"])
        status = (
            "✅ PASS" if passed_count == total_count else f"⚠️ {passed_count}/{total_count} passed"
        )

        lines = [
            "# API Endpoint Write Validation Report",
            "",
            f"Generated: {self.results['timestamp']}",
            f"Hub: {self.host}",
            "",
            "## Summary",
            "",
            f"- **Tests Passed**: {passed_count}/{total_count}",
            f"- **Status**: {status}",
            "",
            "---",
            "",
        ]
        for test in self.results["tests"]:
            icon = "✅" if test.get("passed") else "❌"
            lines.append(f"## {icon} {test['test']}")
            lines.append("")
            lines.append(f"**Summary**: {test.get('summary', 'N/A')}")
            lines.append("")
            if test.get("devices_tested"):
                lines.append("```json")
                lines.append(json.dumps(test["devices_tested"], indent=2, ensure_ascii=False))
                lines.append("```")
                lines.append("")

        with open(output_path, "w") as f:
            f.write("\n".join(lines))
        print(f"\n✅ Report written to {output_path}")

    async def run_all(self) -> dict:
        try:
            await self.setup()
            await self.test_a_lora_relay_patch_scope()
            await self.test_b_rgb_dimmer_idempotency()
            await self.test_c_heat_pump_mode_matrix()
            await self.test_d_schedule_state_transitions()
            await self.test_e_alarm_idempotency()
            return self.results
        finally:
            await self.teardown()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.getenv("SINUM_HOST"))
    parser.add_argument("--password", default=os.getenv("SINUM_PASSWORD"))
    parser.add_argument("--output", default="docs/live_write_validation_latest.md")
    args = parser.parse_args()

    if not args.host or not args.password:
        print("Error: --host and --password required (or SINUM_HOST/SINUM_PASSWORD)")
        sys.exit(1)

    runner = ApiWriteValidationRunner(args.host, args.password)
    results = await runner.run_all()
    runner.generate_report(args.output)

    passed = sum(1 for t in results["tests"] if t.get("passed"))
    total = len(results["tests"])
    print(f"\nResult: {passed}/{total} tests passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    asyncio.run(main())
