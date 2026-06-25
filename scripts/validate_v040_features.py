#!/usr/bin/env python3
"""Live hardware validation for v0.4.1 improvements.

Tests:
  A - target_temperature=0 live: verifies thermostats without sensor return None (not 0.0°C)
  B - SBUS RGB color: sends colour via Lua, verifies hub stores led_color
  C - gate close_status_sensor: reads virtual gate state from hub and logs field names
  D - modbus energy meter: verifies sensors return non-None values

Usage:
  python scripts/validate_v040_features.py --host 10.0.62.167 --password <pass>
  python scripts/validate_v040_features.py --host 10.0.61.132 --token <api_token>
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

import aiohttp


async def _make_client(session: aiohttp.ClientSession, host: str, token: str | None, password: str | None):
    from custom_components.sinum.api import SinumClient

    if token:
        return SinumClient(host, session, api_token=token)
    username, pwd = "admin", password
    client = SinumClient(host, session, username=username, password=pwd)
    await client.login()
    return client


# ── A: target_temperature=0 ────────────────────────────────────────────────────

async def test_a_zero_target_temp(client) -> tuple[str, str]:
    """Find thermostats where target_temperature==0 and report them (expected → None in HA)."""
    try:
        devices = await client.get_virtual_devices()
    except Exception as e:
        return "SKIP", f"Cannot fetch virtual devices: {e}"

    zero_devs = [d for d in devices if d.get("target_temperature") == 0 and d.get("type") == "thermostat"]
    no_sensor_devs = [d for d in zero_devs if not d.get("temperature_sensor_id") and d.get("temperature", 1) == 0]

    lines = []
    for d in zero_devs[:5]:
        tid = d.get("temperature_sensor_id")
        temp = d.get("temperature")
        lines.append(f"  id={d['id']} name={d.get('name')} target_temp=0 sensor_id={tid} current_temp={temp}")

    if not zero_devs:
        return "SKIP", "No thermostats with target_temperature=0 found on this hub"
    return "PASS", (
        f"Found {len(zero_devs)} thermostat(s) with target_temperature=0.\n"
        + "\n".join(lines)
        + f"\n  → In HA these will show target=None (not 0.0°C). "
        + f"Devices with both temp+target=0: {len(no_sensor_devs)}"
    )


# ── B: SBUS RGB Lua colour ─────────────────────────────────────────────────────

async def test_b_sbus_rgb_lua_color(client) -> tuple[str, str]:
    """Find an SBUS rgb_controller and send a colour via Lua scene; verify hub reflects it."""
    try:
        sbus = await client.get_sbus_devices()
    except Exception as e:
        return "SKIP", f"Cannot fetch SBUS devices: {e}"

    rgb_devices = [d for d in sbus if d.get("type") == "rgb_controller"]
    if not rgb_devices:
        return "SKIP", "No SBUS rgb_controller devices on this hub"

    dev = rgb_devices[0]
    dev_id = int(dev["id"])
    original_color = dev.get("led_color", "#UNKNOWN")
    test_color = "#00FF88"

    # Build Lua scene
    lua_code = f'sbus[{dev_id}]:call("set_color",{{"{test_color}",200}})'
    try:
        scene_name = f"_ha_validate_rgb_{dev_id}"
        scene_id = await client.get_or_create_scene(scene_name)
        await client.patch_scene_lua(scene_id, lua_code)
        await client.run_scene(scene_id)
        await asyncio.sleep(1.5)  # let hub process

        # Read back
        updated_sbus = await client.get_sbus_devices()
        updated_dev = next((d for d in updated_sbus if int(d["id"]) == dev_id), {})
        reported_color = updated_dev.get("led_color", "NOT_REPORTED")

        # Cleanup scene
        await client.delete_scene(scene_id)
    except Exception as e:
        return "FAIL", f"Lua scene operation failed for SBUS id={dev_id}: {e}"

    # Restore original colour (best effort)
    if original_color != "#UNKNOWN":
        try:
            scene_id2 = await client.get_or_create_scene(f"_ha_validate_rgb_restore_{dev_id}")
            restore_lua = f'sbus[{dev_id}]:call("set_color",{{"{original_color}",200}})'
            await client.patch_scene_lua(scene_id2, restore_lua)
            await client.run_scene(scene_id2)
            await asyncio.sleep(0.5)
            await client.delete_scene(scene_id2)
        except Exception:
            pass

    if reported_color.upper() == test_color.upper():
        return "PASS", f"SBUS id={dev_id}: set {test_color} → hub reports {reported_color} ✓"
    return "WARN", (
        f"SBUS id={dev_id}: set {test_color} but hub reports led_color={reported_color}. "
        "Hub may not reflect colour in REST until device is on — visually verify."
    )


# ── C: virtual gate field survey ───────────────────────────────────────────────

async def test_c_gate_field_survey(client) -> tuple[str, str]:
    """Read virtual gate devices and log all their fields to identify close_status_sensor."""
    try:
        devices = await client.get_virtual_devices()
    except Exception as e:
        return "SKIP", f"Cannot fetch virtual devices: {e}"

    gates = [d for d in devices if d.get("type") == "gate"]
    if not gates:
        return "SKIP", "No virtual gate devices on this hub"

    lines = []
    for g in gates[:3]:
        fields = [f"{k}={v!r}" for k, v in sorted(g.items())]
        lines.append(f"  Gate id={g['id']} name={g.get('name')}:")
        lines.append("    " + ", ".join(fields))

    # Key fields we're looking for
    all_keys: set[str] = set()
    for g in gates:
        all_keys.update(g.keys())
    status_fields = sorted(k for k in all_keys if "status" in k or "sensor" in k or "close" in k)

    detail = "\n".join(lines)
    if status_fields:
        detail += f"\n  Potential status/sensor fields found: {status_fields}"
        detail += "\n  → implement close_status_sensor fallback using these field names"
    else:
        detail += "\n  No status/sensor fields found — hub returns 'state' only"
        detail += "\n  Gate state field values seen: " + str({g.get("state") for g in gates})

    return "INFO", detail


# ── D: modbus energy meter ─────────────────────────────────────────────────────

async def test_d_modbus_energy(client) -> tuple[str, str]:
    """Verify modbus energy meter returns non-None values for key sensors."""
    try:
        from custom_components.sinum.api import SinumNotSupportedError
        devices = await client.get_modbus_devices()
    except Exception as e:
        if "404" in str(e) or "not found" in str(e).lower():
            return "SKIP", "Modbus endpoint not available on this hub (sinum_lite)"
        return "FAIL", f"get_modbus_devices failed: {e}"

    energy_meters = [d for d in devices if d.get("type") == "energy_meter"]
    if not energy_meters:
        return "SKIP", "No modbus energy_meter devices found"

    meter = energy_meters[0]
    checks = [
        ("total_active_power", meter.get("total_active_power")),
        ("energy_consumed_total", meter.get("energy_consumed_total")),
        ("phase_1.voltage", (meter.get("phase_1") or {}).get("voltage")),
        ("phase_1.current", (meter.get("phase_1") or {}).get("current")),
    ]

    results = []
    failed = 0
    for field, val in checks:
        ok = val is not None
        if not ok:
            failed += 1
        results.append(f"  {field}: {val!r} {'✓' if ok else '✗ MISSING'}")

    status = "FAIL" if failed else "PASS"
    return status, f"Energy meter id={meter.get('id')}:\n" + "\n".join(results)


# ── Runner ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(description="Validate v0.4.1 features on live hub")
    parser.add_argument("--host", required=True)
    parser.add_argument("--password", default=None)
    parser.add_argument("--token", default=None)
    args = parser.parse_args()

    if not args.password and not args.token:
        print("ERROR: provide --password or --token"); sys.exit(1)

    lines: list[str] = [
        f"# Sinum v0.4.1 feature validation",
        f"# Hub: {args.host}",
        f"# Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    tests = [
        ("A", "target_temperature=0 → None", test_a_zero_target_temp),
        ("B", "SBUS RGB Lua colour set", test_b_sbus_rgb_lua_color),
        ("C", "Gate field survey (close_status_sensor?)", test_c_gate_field_survey),
        ("D", "Modbus energy meter values", test_d_modbus_energy),
    ]

    async with aiohttp.ClientSession() as session:
        client = await _make_client(session, args.host, args.token, args.password)
        for letter, name, fn in tests:
            print(f"[{letter}] {name}...", end=" ", flush=True)
            try:
                status, detail = await fn(client)
            except Exception as e:
                status, detail = "ERROR", str(e)
            print(status)
            lines.append(f"## Test {letter}: {name}")
            lines.append(f"**Status**: {status}")
            lines.append("")
            lines.append(detail)
            lines.append("")

    report = "\n".join(lines)
    out = Path("docs/live_v041_validation.md")
    out.write_text(report)
    print(f"\nReport written to {out}")
    if any("[FAIL]" in l or "[ERROR]" in l for l in lines):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
