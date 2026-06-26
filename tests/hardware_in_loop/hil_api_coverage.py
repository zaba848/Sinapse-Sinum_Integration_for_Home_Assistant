#!/usr/bin/env python3
"""Hardware-in-loop API coverage test.

Probes all known Sinum REST API endpoints and reports which are available.
Run against a live hub to ensure API client coverage is complete.

Usage:
    python3 tests/hardware_in_loop/hil_api_coverage.py --host 10.0.62.167 --token <JWT>

Exit codes:
    0 — all critical endpoints responded (non-500)
    1 — at least one critical endpoint failed
"""

from __future__ import annotations

import argparse
import asyncio
import sys


async def run_hil(host: str, token: str) -> bool:  # noqa: C901
    try:
        import aiohttp
    except ImportError:
        print("FAIL: aiohttp not installed", file=sys.stderr)
        return False

    base = f"http://{host}"
    headers = {"Authorization": f"Bearer {token}"}

    # (path, is_critical, label)
    endpoints = [
        ("/api/v1/info", True, "hub info"),
        ("/api/v1/rooms", True, "rooms"),
        ("/api/v1/floors", False, "floors"),
        ("/api/v1/devices/virtual", True, "virtual devices"),
        ("/api/v1/devices/wtp", True, "WTP devices"),
        ("/api/v1/devices/sbus", True, "SBUS devices"),
        ("/api/v1/devices/lora", False, "LoRa devices"),
        ("/api/v1/devices/modbus", False, "Modbus devices"),
        ("/api/v1/devices/video", False, "video devices"),
        ("/api/v1/devices/alarm", False, "alarm devices"),
        ("/api/v1/parent_devices", False, "parent devices"),
        ("/api/v1/scenes", False, "scenes"),
        ("/api/v1/schedules", False, "schedules"),
        ("/api/v1/automations", False, "automations"),
        ("/api/v1/variables", False, "variables"),
        ("/api/v1/notifications", False, "notifications"),
        ("/api/v1/ws", False, "websocket endpoint (101 expected)"),
    ]

    print(f"Testing {base} with {len(endpoints)} endpoints...\n")
    failed_critical = 0
    passed = 0
    skipped = 0

    async with aiohttp.ClientSession() as session:
        for path, critical, label in endpoints:
            url = f"{base}{path}"
            try:
                if path == "/api/v1/ws":
                    # WebSocket probe: just check HTTP 101
                    resp = await session.get(
                        url, headers={**headers, "Upgrade": "websocket",
                                      "Connection": "Upgrade",
                                      "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
                                      "Sec-WebSocket-Version": "13"},
                        allow_redirects=False, timeout=aiohttp.ClientTimeout(total=5),
                    )
                    code = resp.status
                else:
                    resp = await session.get(
                        url, headers=headers,
                        timeout=aiohttp.ClientTimeout(total=5),
                    )
                    code = resp.status

                ok = code < 500
                mark = "OK  " if ok else "FAIL"
                note = "" if ok else " ← CRITICAL" if critical else " (optional)"
                print(f"  [{mark}] {code:3d}  {path:<40} {label}{note}")
                if ok:
                    passed += 1
                elif critical:
                    failed_critical += 1
            except Exception as exc:
                mark = "ERR "
                print(f"  [{mark}]  ---  {path:<40} {label}  ({exc})")
                if critical:
                    failed_critical += 1
                else:
                    skipped += 1

    print(f"\nResult: {passed} passed, {failed_critical} critical failures, {skipped} optional skipped")
    if failed_critical:
        print("FAIL: critical endpoints unavailable")
        return False
    print("PASS: all critical endpoints OK")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Sinum API coverage HIL test")
    parser.add_argument("--host", required=True, help="Hub IP or hostname")
    parser.add_argument("--token", required=True, help="API token (JWT)")
    args = parser.parse_args()

    ok = asyncio.run(run_hil(args.host, args.token))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
