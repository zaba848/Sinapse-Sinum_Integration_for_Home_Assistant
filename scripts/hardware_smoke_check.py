#!/usr/bin/env python3
"""Run read-only hardware smoke checks for Sinum hubs.

Configuration comes from environment variables or CLI arguments; credentials
must not be stored in this repository.

Examples:
    SINUM_SMOKE_HUBS="WTP=http://sinum-wtp.local,SBUS=http://sinum-sbus.local" \
      SINUM_PASSWORD=... python3 scripts/hardware_smoke_check.py
    SINUM_SBUS_TOKEN=... python3 scripts/hardware_smoke_check.py --hub SBUS=sinum-sbus.local
    SINUM_LORA_TOKEN=... python3 scripts/hardware_smoke_check.py --hub LORA=sinum-lora.local
"""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_HUBS = ""
DEFAULT_USERNAME = "admin"

# These must return 200 on every hub — failure makes the hub FAIL.
REQUIRED_ENDPOINTS = (
    "/api/v1/info",
    "/api/v1/devices/wtp",
    "/api/v1/devices/sbus",
    "/api/v1/devices/virtual",
)

# 404 here means "bus not present on this firmware" — not a failure.
OPTIONAL_ENDPOINTS = (
    "/api/v1/devices/lora",
    "/api/v1/devices/slink",
    "/api/v1/devices/modbus",
)

ALL_ENDPOINTS = REQUIRED_ENDPOINTS + OPTIONAL_ENDPOINTS


@dataclass(frozen=True)
class Hub:
    label: str
    url: str


@dataclass
class HubResult:
    hub: Hub
    login: str
    endpoint_codes: dict[str, str] = field(default_factory=dict)
    lora_devices: list[dict] = field(default_factory=list)
    ok: bool = False


def _env_label(label: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", label.upper()).strip("_")


def _with_scheme(value: str) -> str:
    if value.startswith(("http://", "https://")):
        return value.rstrip("/")
    return f"http://{value.rstrip('/')}"


def _parse_hub_spec(spec: str) -> Hub:
    if "=" not in spec:
        raise ValueError(f"Hub spec must be LABEL=URL, got: {spec!r}")
    label, url = spec.split("=", 1)
    label = label.strip()
    url = url.strip()
    if not label or not url:
        raise ValueError(f"Hub spec must be LABEL=URL, got: {spec!r}")
    return Hub(label=label, url=_with_scheme(url))


def _hub_specs_from_cli_or_env(cli_hubs: list[str] | None) -> list[str]:
    if cli_hubs:
        return cli_hubs
    raw = os.getenv("SINUM_SMOKE_HUBS", DEFAULT_HUBS)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _load_hubs(cli_hubs: list[str] | None) -> list[Hub]:
    specs = _hub_specs_from_cli_or_env(cli_hubs)
    if not specs:
        raise ValueError("Provide at least one hub via --hub or SINUM_SMOKE_HUBS")
    return [_parse_hub_spec(spec) for spec in specs]


def _request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, bytes]:
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.getcode(), resp.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()
    except (OSError, TimeoutError, urllib.error.URLError) as err:
        return 0, str(err).encode()


def _token_for_hub(hub: Hub) -> str | None:
    env_label = _env_label(hub.label)
    return os.getenv(f"SINUM_{env_label}_TOKEN") or os.getenv("SINUM_API_TOKEN")


def _password_for_hub(hub: Hub) -> str | None:
    env_label = _env_label(hub.label)
    return os.getenv(f"SINUM_{env_label}_PASSWORD") or os.getenv("SINUM_PASSWORD")


def _username_for_hub(hub: Hub) -> str:
    env_label = _env_label(hub.label)
    return (
        os.getenv(f"SINUM_{env_label}_USERNAME") or os.getenv("SINUM_USERNAME") or DEFAULT_USERNAME
    )


def _login_session(hub: Hub) -> tuple[str, str | None]:
    token = _token_for_hub(hub)
    if token:
        return "TOKEN", token

    password = _password_for_hub(hub)
    if not password:
        return "NO_AUTH", None

    code, body = _request_json(
        f"{hub.url}/api/v1/login",
        method="POST",
        payload={
            "username": _username_for_hub(hub),
            "password": password,
            "os_info": "HA",
        },
    )
    if code != 200:
        return str(code or "FAIL"), None
    try:
        data = json.loads(body).get("data", {})
        session = data.get("session")
    except (TypeError, ValueError):
        session = None
    return ("200", session) if session else ("BAD_JSON", None)


def _endpoint_code(results: dict[str, str], path: str) -> str:
    return results.get(path, "N/A")


def _parse_lora_devices(body: bytes) -> list[dict]:
    try:
        payload = json.loads(body)
        data = payload.get("data", [])
        # Hub returns data as a flat list of device dicts
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
        # Fallback: older/alternative structure data.lora.devices
        if isinstance(data, dict):
            devices = data.get("lora", {}).get("devices", [])
            return devices if isinstance(devices, list) else []
        return []
    except (TypeError, ValueError, KeyError):
        return []


def check_hub(hub: Hub) -> HubResult:
    login_status, token = _login_session(hub)
    if not token:
        return HubResult(hub=hub, login=login_status)

    headers = {"Authorization": f"Bearer {token}"}
    endpoint_codes: dict[str, str] = {}
    ok = True

    for path in ALL_ENDPOINTS:
        code, body = _request_json(f"{hub.url}{path}", headers=headers)
        endpoint_codes[path] = str(code or "ERR")

        if code != 200:
            if path in REQUIRED_ENDPOINTS:
                ok = False
            elif code not in {404, 0}:
                # Unexpected error on optional endpoint — still report but don't fail
                pass

    lora_devices: list[dict] = []
    lora_code = endpoint_codes.get("/api/v1/devices/lora", "N/A")
    if lora_code == "200":
        _, lora_body = _request_json(f"{hub.url}/api/v1/devices/lora", headers=headers)
        lora_devices = _parse_lora_devices(lora_body)

    result = HubResult(
        hub=hub,
        login=login_status,
        endpoint_codes=endpoint_codes,
        lora_devices=lora_devices,
        ok=ok,
    )
    return result


def _lora_device_summary(devices: list[dict]) -> str:
    if not devices:
        return ""
    lines = []
    for d in devices:
        eui = d.get("eui") or d.get("EUI") or "?"
        name = d.get("name") or d.get("_device_name") or "unnamed"
        sw = d.get("sw_version") or d.get("firmware") or ""
        lines.append(f"  EUI={eui} name={name!r}" + (f" fw={sw}" if sw else ""))
    return "\n".join(lines)


def _report_lines(results: list[HubResult]) -> list[str]:
    lines = [
        "# Hardware Smoke Test (Latest)",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}",
        "",
        "| Hub | Login | /info | /devices/wtp | /devices/sbus | /devices/virtual"
        " | /devices/lora | /devices/slink | /devices/modbus |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        label = result.hub.label
        lines.append(
            f"| {label} | {result.login}"
            f" | {_endpoint_code(result.endpoint_codes, '/api/v1/info')}"
            f" | {_endpoint_code(result.endpoint_codes, '/api/v1/devices/wtp')}"
            f" | {_endpoint_code(result.endpoint_codes, '/api/v1/devices/sbus')}"
            f" | {_endpoint_code(result.endpoint_codes, '/api/v1/devices/virtual')}"
            f" | {_endpoint_code(result.endpoint_codes, '/api/v1/devices/lora')}"
            f" | {_endpoint_code(result.endpoint_codes, '/api/v1/devices/slink')}"
            f" | {_endpoint_code(result.endpoint_codes, '/api/v1/devices/modbus')} |"
        )

    # LoRa device details
    lora_hubs = [r for r in results if r.lora_devices]
    if lora_hubs:
        lines.extend(["", "## LoRa Devices"])
        for result in lora_hubs:
            lines.append(f"\n### {result.hub.label}")
            summary = _lora_device_summary(result.lora_devices)
            lines.append(summary if summary else "(none)")

    lines.extend(["", "## Result", "", "PASS" if all(r.ok for r in results) else "FAIL"])
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Run read-only Sinum hardware smoke checks")
    parser.add_argument(
        "--hub",
        action="append",
        help="Hub definition in LABEL=URL form. Can be passed multiple times.",
    )
    parser.add_argument(
        "--output",
        default=os.getenv("SINUM_SMOKE_OUTPUT", "docs/hardware_smoke_latest.md"),
        help="Markdown report path",
    )
    args = parser.parse_args()

    try:
        hubs = _load_hubs(args.hub)
    except ValueError as err:
        parser.error(str(err))
    results = [check_hub(hub) for hub in hubs]
    lines = _report_lines(results)

    out_md = Path(args.output)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"Smoke report written to {out_md}")

    # Print LoRa device details to stdout for quick verification
    for result in results:
        if result.lora_devices:
            print(f"\n{result.hub.label} — {len(result.lora_devices)} LoRa device(s):")
            print(_lora_device_summary(result.lora_devices))

    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
