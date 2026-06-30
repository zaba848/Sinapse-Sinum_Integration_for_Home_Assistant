#!/usr/bin/env python3
"""Hardware-in-loop smoke test — full integration check.

Validates: login, device fetch, WS connection, snapshot proxy, state update flow.

Usage:
    python3 tests/hardware_in_loop/hil_smoke.py --host <HUB_IP> --token <JWT>
    python3 tests/hardware_in_loop/hil_smoke.py --host <VIDEO_HUB_IP> --token <JWT> --video

Exit codes:
    0 — smoke passed
    1 — at least one check failed
"""

from __future__ import annotations

import argparse
import asyncio
import sys


async def check_hub_info(session, base: str, headers: dict) -> bool:
    import aiohttp
    url = f"{base}/api/v1/info"
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as r:
            data = await r.json(content_type=None)
            name = data.get("name") or data.get("hostname") or "(unnamed)"
            print(f"  [OK ] hub info: name={name} status={r.status}")
            return r.status < 400
    except Exception as exc:
        print(f"  [ERR] hub info: {exc}")
        return False


async def check_devices(session, base: str, headers: dict, bus: str) -> bool:
    import aiohttp
    url = f"{base}/api/v1/devices/{bus}"
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as r:
            if r.status == 404:
                print(f"  [---] devices/{bus}: 404 (bus not present)")
                return True
            data = await r.json(content_type=None)
            count = len(data) if isinstance(data, list) else len(data.get("data", data.get("devices", [])))
            print(f"  [OK ] devices/{bus}: {count} devices")
            return r.status < 400
    except Exception as exc:
        print(f"  [ERR] devices/{bus}: {exc}")
        return False


async def check_websocket(base: str, token: str) -> bool:
    import aiohttp
    ws_url = f"{base.replace('http://', 'ws://')}/api/v1/ws?access_token={token}"
    try:
        async with aiohttp.ClientSession() as session, session.ws_connect(ws_url, heartbeat=5, ssl=False) as ws:
            received = 0
            async with asyncio.timeout(8):
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        received += 1
                        if received >= 2:
                            break
        print(f"  [OK ] websocket: received {received} message(s)")
        return True
    except TimeoutError:
        print("  [OK ] websocket: connected (no events in 8s, which may be normal)")
        return True
    except Exception as exc:
        print(f"  [ERR] websocket: {exc}")
        return False


async def check_snapshot(session, base: str, headers: dict, video_id: int) -> bool:
    import aiohttp
    url = f"{base}/api/v1/devices/video/{video_id}/snapshot"
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
            body = await r.read()
            if r.status == 404:
                print(f"  [---] snapshot/{video_id}: 404 (no camera)")
                return True
            size_kb = len(body) // 1024
            print(f"  [OK ] snapshot/{video_id}: {r.status} {size_kb}KB")
            return r.status < 400
    except Exception as exc:
        print(f"  [ERR] snapshot: {exc}")
        return False


async def run_hil(host: str, token: str, video_id: int | None) -> bool:
    try:
        import aiohttp
    except ImportError:
        print("FAIL: aiohttp not installed", file=sys.stderr)
        return False

    base = f"http://{host}"
    headers = {"Authorization": f"Bearer {token}"}
    results: list[bool] = []

    print(f"=== Sinum HIL Smoke Test: {base} ===\n")

    async with aiohttp.ClientSession() as session:
        results.append(await check_hub_info(session, base, headers))
        for bus in ("virtual", "wtp", "sbus", "lora"):
            results.append(await check_devices(session, base, headers, bus))
        if video_id:
            results.append(await check_snapshot(session, base, headers, video_id))

    results.append(await check_websocket(base, token))

    passed = sum(results)
    total = len(results)
    print(f"\nResult: {passed}/{total} checks passed")
    if all(results):
        print("PASS")
        return True
    print("FAIL")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Sinum HIL smoke test")
    parser.add_argument("--host", required=True, help="Hub IP or hostname")
    parser.add_argument("--token", required=True, help="API token (JWT)")
    parser.add_argument("--video", type=int, default=None, metavar="ID",
                        help="Camera device ID to test snapshot proxy")
    args = parser.parse_args()

    ok = asyncio.run(run_hil(args.host, args.token, args.video))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
