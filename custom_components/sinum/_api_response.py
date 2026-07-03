"""HTTP response parsing helpers for the Sinum API client."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp

from ._api_errors import SinumConnectionError, SinumNotSupportedError


async def read_json(resp: aiohttp.ClientResponse, path: str) -> dict[str, Any]:
    """Read response body and parse JSON; handle empty/non-JSON responses gracefully."""
    try:
        raw = await resp.read()
    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
        raise SinumConnectionError(f"Failed to read response body for {path}: {err}") from err
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError) as err:
        raise SinumConnectionError(
            f"Non-JSON response from {path} (status {resp.status}): {raw[:80]!r}"
        ) from err


def unwrap_data(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        return {}
    data = body.get("data", body)
    return data if isinstance(data, dict) else {}


def validation_error_details(body: dict[str, Any]) -> str:
    errors = body.get("error", {}).get("errors", {})
    return "; ".join(
        f"{key}: {value.get('text', value)}" if isinstance(value, dict) else f"{key}: {value}"
        for key, value in errors.items()
    )


def raise_for_unexpected_status(status: int, path: str) -> None:
    if status in (200, 201, 204):
        return
    if status == 404:
        raise SinumNotSupportedError(f"Endpoint not found on this hub: {path}")
    raise SinumConnectionError(f"API error {status} for {path}")
