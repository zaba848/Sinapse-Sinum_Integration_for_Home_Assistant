#!/usr/bin/env python3
"""Run read-only hardware smoke checks for WTP and SBUS hubs.

Uses username/password login and validates core read endpoints.
Outputs a markdown report into docs/hardware_smoke_latest.md.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

WTP_HOST = "http://10.0.61.132"
SBUS_HOST = "http://10.0.62.167"
USERNAME = "admin"
PASSWORD = "admintablica"

ENDPOINTS = [
    "/api/v1/info",
    "/api/v1/devices/wtp",
    "/api/v1/devices/sbus",
    "/api/v1/devices/virtual",
]

OUT_MD = Path("docs/hardware_smoke_latest.md")


def post_json(url: str, payload: dict, headers: dict[str, str] | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.getcode(), resp.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()


def get_json(url: str, headers: dict[str, str] | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, method="GET", headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.getcode(), resp.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()


def login_session(host: str) -> str | None:
    code, body = post_json(
        f"{host}/api/v1/login",
        {"username": USERNAME, "password": PASSWORD, "os_info": "HA"},
    )
    if code != 200:
        return None
    try:
        data = json.loads(body).get("data", {})
        return data.get("session")
    except (ValueError, TypeError):
        return None


def check_hub(host: str) -> tuple[int, list[tuple[str, int]]]:
    session = login_session(host)
    if not session:
        return 0, []

    headers = {"Authorization": f"Bearer {session}"}
    results: list[tuple[str, int]] = []
    ok = 1
    for path in ENDPOINTS:
        code, _ = get_json(f"{host}{path}", headers=headers)
        results.append((path, code))
        if code != 200:
            ok = 0
    return ok, results


def main() -> int:
    wtp_ok, wtp_results = check_hub(WTP_HOST)
    sbus_ok, sbus_results = check_hub(SBUS_HOST)

    lines = [
        "# Hardware Smoke Test (Latest)",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}",
        "",
        "| Hub | Login | /info | /devices/wtp | /devices/sbus | /devices/virtual |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    def endpoint_code(results: list[tuple[str, int]], path: str) -> str:
        for p, code in results:
            if p == path:
                return str(code)
        return "N/A"

    lines.append(
        "| 10.0.61.132 (WTP) | "
        + ("200" if wtp_ok else "FAIL")
        + f" | {endpoint_code(wtp_results, '/api/v1/info')}"
        + f" | {endpoint_code(wtp_results, '/api/v1/devices/wtp')}"
        + f" | {endpoint_code(wtp_results, '/api/v1/devices/sbus')}"
        + f" | {endpoint_code(wtp_results, '/api/v1/devices/virtual')} |"
    )

    lines.append(
        "| 10.0.62.167 (SBUS) | "
        + ("200" if sbus_ok else "FAIL")
        + f" | {endpoint_code(sbus_results, '/api/v1/info')}"
        + f" | {endpoint_code(sbus_results, '/api/v1/devices/wtp')}"
        + f" | {endpoint_code(sbus_results, '/api/v1/devices/sbus')}"
        + f" | {endpoint_code(sbus_results, '/api/v1/devices/virtual')} |"
    )

    lines.extend(
        [
            "",
            "## Result",
            "",
            "PASS" if (wtp_ok and sbus_ok) else "FAIL",
        ]
    )

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Smoke report written to {OUT_MD}")

    return 0 if (wtp_ok and sbus_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
