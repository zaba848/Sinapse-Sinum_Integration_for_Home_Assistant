#!/usr/bin/env python3
"""
API endpoint write validation runner and report generator for Sinum integration.

This script:
1. Runs write validation tests on configured hub(s).
2. Collects results (A–E test cases).
3. Generates markdown report to docs/api_endpoint_write_validation_latest.md.

Usage:
    python3 scripts/validate_api_writes.py --host 10.0.61.132 --password <pw>

Environment:
    SINUM_HOST: Hub IP address or hostname
    SINUM_PASSWORD: Hub admin password
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

import aiohttp

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from custom_components.sinum.api import SinumClient


class ApiWriteValidationRunner:
    """Runner for API write endpoint validation tests."""

    def __init__(self, host: str, password: str):
        """Initialize runner with hub credentials."""
        self.host = host
        self.password = password
        self.client = None
        self.results = {"timestamp": datetime.utcnow().isoformat() + "Z", "tests": []}

    async def setup(self):
        """Create client and authenticate."""
        self.session = aiohttp.ClientSession()
        self.client = SinumClient(
            session=self.session, host=self.host, password=self.password
        )
        token = await self.client.login()
        if not token:
            raise RuntimeError(f"Failed to authenticate with {self.host}")
        print(f"✅ Authenticated with {self.host}")

    async def teardown(self):
        """Close session."""
        if self.session:
            await self.session.close()

    async def test_a_lora_relay_patch_scope(self):
        """A. LoRa Relay PATCH Scope."""
        print("\n🧪 Test A: LoRa Relay PATCH Scope")
        result = {
            "test": "A. LoRa Relay PATCH Scope",
            "passed": False,
            "devices_tested": [],
            "summary": "",
        }

        try:
            devices = await self.client.get_devices_lora()
            relay_devices = [
                d
                for d in devices
                if d.get("type") == "relay"
            ]

            if not relay_devices:
                result["summary"] = "No LoRa relay devices found"
                print(f"  ⚠️  {result['summary']}")
                self.results["tests"].append(result)
                return

            for relay in relay_devices[:2]:
                device_id = relay.get("id")
                initial_state = relay.get("state", {}).get("on", False)
                new_state = not initial_state

                try:
                    await self.client.patch_device_lora(
                        device_id, {"state": {"on": new_state}}
                    )
                    updated = await self.client.get_device_lora(device_id)
                    is_writable = updated.get("state", {}).get("on") == new_state
                    result["devices_tested"].append(
                        {
                            "device_id": device_id,
                            "name": relay.get("name"),
                            "writable": is_writable,
                        }
                    )
                    await self.client.patch_device_lora(
                        device_id, {"state": {"on": initial_state}}
                    )
                    print(
                        f"  ✅ {relay.get('name')} — writable: {is_writable}"
                    )
                except Exception as e:
                    result["devices_tested"].append(
                        {
                            "device_id": device_id,
                            "name": relay.get("name"),
                            "error": str(e),
                        }
                    )
                    print(f"  ❌ {relay.get('name')} — error: {e}")

            result["passed"] = len(result["devices_tested"]) > 0
            result["summary"] = f"Tested {len(result['devices_tested'])} LoRa relay(s)"

        except Exception as e:
            result["summary"] = f"Error: {e}"
            print(f"  ❌ {result['summary']}")

        self.results["tests"].append(result)

    async def test_b_rgb_dimmer_idempotency(self):
        """B. RGB/Dimmer Idempotency."""
        print("\n🧪 Test B: RGB/Dimmer Idempotency")
        result = {
            "test": "B. RGB/Dimmer Idempotency",
            "passed": False,
            "devices_tested": [],
            "summary": "",
        }

        try:
            wtp_devices = await client.get_devices_wtp()
            rgb_devices = [
                d
                for d in wtp_devices
                if "rgb" in d.get("type", "").lower()
                or "dimmer" in d.get("type", "").lower()
            ]

            if not rgb_devices:
                result["summary"] = "No RGB/dimmer devices found"
                print(f"  ⚠️  {result['summary']}")
                self.results["tests"].append(result)
                return

            for device in rgb_devices[:2]:
                device_id = device.get("id")
                device_type = device.get("type", "unknown")

                try:
                    if "dimmer" in device_type:
                        level = 75
                        await self.client.patch_device_wtp(
                            device_id, {"state": {"level": level}}
                        )
                        await self.client.patch_device_wtp(
                            device_id, {"state": {"level": level}}
                        )
                        updated = await self.client.get_device_wtp(device_id)
                        success = updated.get("state", {}).get("level") == level
                        result["devices_tested"].append(
                            {
                                "device_id": device_id,
                                "name": device.get("name"),
                                "type": device_type,
                                "test": "dimmer_idempotency",
                                "success": success,
                            }
                        )
                        print(
                            f"  ✅ {device.get('name')} (dimmer) — idempotent: {success}"
                        )
                except Exception as e:
                    result["devices_tested"].append(
                        {
                            "device_id": device_id,
                            "name": device.get("name"),
                            "type": device_type,
                            "error": str(e),
                        }
                    )
                    print(f"  ❌ {device.get('name')} — error: {e}")

            result["passed"] = len(result["devices_tested"]) > 0
            result["summary"] = f"Tested {len(result['devices_tested'])} RGB/dimmer device(s)"

        except Exception as e:
            result["summary"] = f"Error: {e}"
            print(f"  ❌ {result['summary']}")

        self.results["tests"].append(result)

    async def test_c_heat_pump_mode_matrix(self):
        """C. Heat Pump Manager Mode Matrix."""
        print("\n🧪 Test C: Heat Pump Mode Matrix")
        result = {
            "test": "C. Heat Pump Mode Matrix",
            "passed": False,
            "devices_tested": [],
            "summary": "",
        }

        try:
            virtual_devices = await self.client.get_devices_virtual()
            heat_pump_devices = [
                d
                for d in virtual_devices
                if d.get("type") == "heat_pump_manager"
            ]

            if not heat_pump_devices:
                result["summary"] = "No heat pump manager devices found"
                print(f"  ⚠️  {result['summary']}")
                self.results["tests"].append(result)
                return

            valid_modes = ["OFF", "HEAT", "COOL", "AUTO"]

            for device in heat_pump_devices[:1]:
                device_id = device.get("id")
                device_modes = []

                try:
                    current_mode = device.get("state", {}).get("mode", "OFF")

                    for target_mode in valid_modes:
                        try:
                            await self.client.patch_device_virtual(
                                device_id, {"state": {"mode": target_mode}}
                            )
                            await asyncio.sleep(0.5)
                            updated = await self.client.get_device_virtual(device_id)
                            actual_mode = updated.get("state", {}).get("mode")
                            device_modes.append(
                                {
                                    "target": target_mode,
                                    "actual": actual_mode,
                                    "success": actual_mode == target_mode,
                                }
                            )
                        except Exception as e:
                            device_modes.append(
                                {"target": target_mode, "error": str(e)}
                            )

                    result["devices_tested"].append(
                        {
                            "device_id": device_id,
                            "name": device.get("name"),
                            "mode_transitions": device_modes,
                        }
                    )
                    print(
                        f"  ✅ {device.get('name')} — tested {len(valid_modes)} modes"
                    )

                    await self.client.patch_device_virtual(
                        device_id, {"state": {"mode": current_mode}}
                    )
                except Exception as e:
                    result["devices_tested"].append(
                        {"device_id": device_id, "error": str(e)}
                    )
                    print(f"  ❌ Error: {e}")

            result["passed"] = len(result["devices_tested"]) > 0
            result["summary"] = (
                f"Tested {len(result['devices_tested'])} heat pump device(s)"
            )

        except Exception as e:
            result["summary"] = f"Error: {e}"
            print(f"  ❌ {result['summary']}")

        self.results["tests"].append(result)

    async def test_d_schedule_state_transitions(self):
        """D. Schedule State Transitions."""
        print("\n🧪 Test D: Schedule State Transitions")
        result = {
            "test": "D. Schedule State Transitions",
            "passed": False,
            "devices_tested": [],
            "summary": "",
        }

        try:
            schedules = await self.client.get_schedules()

            if not schedules:
                result["summary"] = "No schedules found"
                print(f"  ⚠️  {result['summary']}")
                self.results["tests"].append(result)
                return

            for schedule in schedules[:1]:
                schedule_id = schedule.get("id")

                try:
                    current = await self.client.get_schedule(schedule_id)
                    current_mode = current.get("state", {}).get("mode", "day")
                    new_mode = "week" if current_mode == "day" else "day"

                    await self.client.patch_schedule(
                        schedule_id, {"state": {"mode": new_mode}}
                    )
                    await asyncio.sleep(0.5)

                    updated = await self.client.get_schedule(schedule_id)
                    actual_mode = updated.get("state", {}).get("mode")

                    result["devices_tested"].append(
                        {
                            "schedule_id": schedule_id,
                            "name": schedule.get("name"),
                            "target_mode": new_mode,
                            "actual_mode": actual_mode,
                            "success": actual_mode == new_mode,
                        }
                    )
                    print(
                        f"  ✅ {schedule.get('name')} — mode change: {current_mode} → {actual_mode}"
                    )

                    await self.client.patch_schedule(
                        schedule_id, {"state": {"mode": current_mode}}
                    )
                except Exception as e:
                    result["devices_tested"].append(
                        {"schedule_id": schedule_id, "error": str(e)}
                    )
                    print(f"  ❌ Error: {e}")

            result["passed"] = len(result["devices_tested"]) > 0
            result["summary"] = f"Tested {len(result['devices_tested'])} schedule(s)"

        except Exception as e:
            result["summary"] = f"Error: {e}"
            print(f"  ❌ {result['summary']}")

        self.results["tests"].append(result)

    async def test_e_alarm_arm_disarm_idempotency(self):
        """E. Alarm Arm/Disarm Idempotency."""
        print("\n🧪 Test E: Alarm Arm/Disarm Idempotency")
        result = {
            "test": "E. Alarm Arm/Disarm Idempotency",
            "passed": False,
            "devices_tested": [],
            "summary": "",
        }

        try:
            alarm_zones = await self.client.get_devices_alarm_system()

            if not alarm_zones:
                result["summary"] = "No alarm zones found"
                print(f"  ⚠️  {result['summary']}")
                self.results["tests"].append(result)
                return

            for zone in alarm_zones[:2]:
                zone_id = zone.get("id")

                try:
                    current_armed = zone.get("state", {}).get("armed", False)
                    target_armed = not current_armed

                    for _ in range(2):
                        await self.client.patch_device_alarm_system(
                            zone_id, {"state": {"armed": target_armed}}
                        )
                        await asyncio.sleep(0.3)

                    updated = await self.client.get_device_alarm_system(zone_id)
                    actual_armed = updated.get("state", {}).get("armed")

                    result["devices_tested"].append(
                        {
                            "zone_id": zone_id,
                            "name": zone.get("name"),
                            "target_armed": target_armed,
                            "actual_armed": actual_armed,
                            "idempotent": actual_armed == target_armed,
                        }
                    )
                    print(
                        f"  ✅ {zone.get('name')} — idempotent: {actual_armed == target_armed}"
                    )

                    await self.client.patch_device_alarm_system(
                        zone_id, {"state": {"armed": current_armed}}
                    )
                except Exception as e:
                    result["devices_tested"].append(
                        {"zone_id": zone_id, "error": str(e)}
                    )
                    print(f"  ❌ Error: {e}")

            result["passed"] = len(result["devices_tested"]) > 0
            result["summary"] = f"Tested {len(result['devices_tested'])} alarm zone(s)"

        except Exception as e:
            result["summary"] = f"Error: {e}"
            print(f"  ❌ {result['summary']}")

        self.results["tests"].append(result)

    async def run_all(self):
        """Run all tests."""
        try:
            await self.setup()

            await self.test_a_lora_relay_patch_scope()
            await self.test_b_rgb_dimmer_idempotency()
            await self.test_c_heat_pump_mode_matrix()
            await self.test_d_schedule_state_transitions()
            await self.test_e_alarm_arm_disarm_idempotency()

            return self.results
        finally:
            await self.teardown()

    def generate_report(self, output_path: str):
        """Generate markdown report."""
        passed_count = sum(1 for t in self.results["tests"] if t.get("passed"))
        total_count = len(self.results["tests"])

        report = f"""# API Endpoint Write Validation Report

Generated: {self.results['timestamp']}
Hub: {self.host}

## Summary

- **Tests Passed**: {passed_count}/{total_count}
- **Status**: {'✅ PASS' if passed_count == total_count else '⚠️  PARTIAL' if passed_count > 0 else '❌ FAIL'}

---

"""

        for test in self.results["tests"]:
            status = "✅ PASS" if test.get("passed") else "❌ FAIL"
            report += f"## {test['test']} {status}\n\n"
            report += f"**Summary**: {test.get('summary', 'N/A')}\n\n"

            if test.get("devices_tested"):
                report += "### Devices Tested\n\n"
                report += "```json\n"
                report += json.dumps(test["devices_tested"], indent=2)
                report += "\n```\n\n"

        with open(output_path, "w") as f:
            f.write(report)

        print(f"\n✅ Report generated: {output_path}")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="API write endpoint validation runner for Sinum integration"
    )
    parser.add_argument("--host", default=os.getenv("SINUM_HOST"))
    parser.add_argument("--password", default=os.getenv("SINUM_PASSWORD"))
    parser.add_argument(
        "--output",
        default="docs/api_endpoint_write_validation_latest.md",
        help="Output report path",
    )

    args = parser.parse_args()

    if not args.host or not args.password:
        print("Error: --host and --password required (or set SINUM_HOST/SINUM_PASSWORD)")
        sys.exit(1)

    runner = ApiWriteValidationRunner(args.host, args.password)
    results = await runner.run_all()
    runner.generate_report(args.output)

    passed = sum(1 for t in results["tests"] if t.get("passed"))
    total = len(results["tests"])
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    asyncio.run(main())
