"""Pure helper functions for SinumWebSocketBridge."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import aiohttp

from .const import DEFAULT_WS_PATH


def _patch_device(
    store: dict[int, dict[str, Any]],
    device_id: int,
    details: Any,
    payload: dict[str, Any],
) -> None:
    current = store.get(device_id, {"id": device_id})
    if isinstance(details, str) and details and details in payload:
        current[details] = payload[details]
    else:
        current.update(payload)
    store[device_id] = current


def _normalize_ws_path(path: str | None) -> str:
    raw = (path or DEFAULT_WS_PATH).strip()
    if not raw or _is_full_url(raw):
        return DEFAULT_WS_PATH
    return _ensure_leading_slash(raw)


def _ensure_leading_slash(raw: str) -> str:
    return raw if raw.startswith("/") else f"/{raw}"


def _is_full_url(raw: str) -> bool:
    return raw.startswith(("ws://", "wss://", "http://", "https://"))


def _iter_events(payload: Any) -> Iterator[dict[str, Any]]:
    if isinstance(payload, list):
        yield from _filter_dicts(payload)
        return
    if not isinstance(payload, dict):
        return
    nested = _find_nested_list(payload)
    if nested is not None:
        yield from _filter_dicts(nested)
        return
    yield payload


def _filter_dicts(lst: list[Any]) -> Iterator[dict[str, Any]]:
    for item in lst:
        if isinstance(item, dict):
            yield item


def _find_nested_list(payload: dict[str, Any]) -> list[Any] | None:
    for key in ("events", "items"):
        val = payload.get(key)
        if isinstance(val, list):
            return val
    return None


def _ws_should_continue(msg_type: aiohttp.WSMsgType) -> bool:
    if msg_type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
        return False
    if msg_type == aiohttp.WSMsgType.ERROR:
        raise RuntimeError("WS message stream entered error state")
    return True


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _device_class(value: Any) -> str:
    cls = str(value or "").lower()
    for prefix in ("virtual", "wtp", "sbus", "lora", "modbus", "video"):
        if cls.startswith(prefix):
            return prefix
    return ""
