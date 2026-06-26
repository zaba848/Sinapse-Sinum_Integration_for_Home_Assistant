#!/usr/bin/env python3
"""Hardware-in-loop WebSocket test.

Connects to a live Sinum hub, validates the WebSocket endpoint,
and verifies that device_state_changed events arrive in the expected format.

Usage:
    python3 tests/hardware_in_loop/hil_websocket.py --host 10.0.62.167 --token <JWT>
    python3 tests/hardware_in_loop/hil_websocket.py --host 10.0.62.117 --token <JWT>

Exit codes:
    0 — all checks passed
    1 — connection or format failure
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter


async def run_hil(host: str, token: str, timeout: float) -> bool:  # noqa: C901
    try:
        import aiohttp
    except ImportError:
        print("FAIL: aiohttp not installed", file=sys.stderr)
        return False

    ws_url = f"ws://{host}/api/v1/ws?access_token={token}"
    print(f"Connecting to {ws_url[:60]}...")

    results: list[dict] = []
    type_counter: Counter = Counter()

    async with aiohttp.ClientSession() as session:
        try:
            async with session.ws_connect(ws_url, heartbeat=10, ssl=False) as ws:
                print("Connected OK")
                try:
                    async with asyncio.timeout(timeout):
                        async for msg in ws:
                            if msg.type != aiohttp.WSMsgType.TEXT:
                                print(f"  Non-text message: {msg.type}")
                                break
                            data = json.loads(msg.data)
                            if not isinstance(data, list):
                                print(f"  FAIL: payload is {type(data).__name__}, expected list")
                                return False
                            for event in data:
                                evt_data = event.get("data", event)
                                evt_type = evt_data.get("type")
                                type_counter[evt_type] += 1
                                if evt_type == "device_state_changed":
                                    results.append(evt_data)
                            if len(results) >= 5:
                                break
                except TimeoutError:
                    print(f"  Timeout after {timeout}s")
        except aiohttp.WSServerHandshakeError as exc:
            print(f"FAIL: WebSocket handshake failed: {exc}")
            return False
        except Exception as exc:
            print(f"FAIL: {exc}")
            return False

    print(f"\nReceived {sum(type_counter.values())} events, types: {dict(type_counter)}")
    print(f"device_state_changed events: {len(results)}")

    if not results:
        print("FAIL: no device_state_changed events received")
        return False

    ok = True
    for i, evt in enumerate(results[:3]):
        payload = evt.get("payload")
        details = evt.get("details")
        if not isinstance(payload, dict):
            print(f"  [event {i}] FAIL: payload is not dict: {payload!r}")
            ok = False
            continue
        device_id = payload.get("id")
        device_class = payload.get("class")
        if device_id is None:
            print(f"  [event {i}] FAIL: missing 'id' in payload")
            ok = False
        if not device_class:
            print(f"  [event {i}] FAIL: missing 'class' in payload")
            ok = False
        if details and details not in payload:
            print(f"  [event {i}] WARN: details='{details}' not found as key in payload")
        if ok:
            print(f"  [event {i}] OK: class={device_class} id={device_id} details={details}")

    if ok:
        print("\nPASS: WebSocket HIL test succeeded")
    else:
        print("\nFAIL: format validation failed")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description="Sinum WebSocket HIL test")
    parser.add_argument("--host", required=True, help="Hub IP or hostname")
    parser.add_argument("--token", required=True, help="API token (JWT)")
    parser.add_argument("--timeout", type=float, default=15.0,
                        help="Seconds to wait for events (default: 15)")
    args = parser.parse_args()

    ok = asyncio.run(run_hil(args.host, args.token, args.timeout))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
