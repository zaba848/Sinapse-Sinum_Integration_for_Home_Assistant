"""List-response normalisation helpers shared across API mixins."""

from __future__ import annotations

from typing import Any


def _dict_list(items: Any) -> list[dict[str, Any]]:
    """Return only dictionary items from a list-like API collection."""
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _extract_from_value(value: Any) -> list[dict[str, Any]] | None:
    if isinstance(value, list):
        return _dict_list(value)
    if isinstance(value, dict):
        nested = _list_result(value)
        return nested or None
    return None


def _extract_by_keys(result: dict[str, Any], keys: tuple[str, ...]) -> list[dict[str, Any]] | None:
    for key in keys:
        extracted = _extract_from_value(result.get(key))
        if extracted is not None:
            return extracted
    return None


def _flatten_values(result: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for value in result.values():
        _append_value_to_flat_list(out, value)
    return out


def _append_value_to_flat_list(out: list[dict[str, Any]], value: Any) -> None:
    if isinstance(value, list):
        out.extend(_dict_list(value))
    elif isinstance(value, dict) and "id" in value:
        out.append(value)


def _list_result_from_dict(
    result: dict[str, Any], preferred_keys: tuple[str, ...]
) -> list[dict[str, Any]]:
    extracted = _extract_by_keys(result, (*preferred_keys, "items", "devices", "results", "data"))
    if extracted is not None:
        return extracted
    if "id" in result:
        return [result]
    return _flatten_values(result)


def _partition_energy_results(
    keys: tuple[str, ...], results: list[Any]
) -> tuple[dict[str, Any], list[str]]:
    available: dict[str, Any] = {}
    missing: list[str] = []
    for key, result in zip(keys, results):
        if result is not None:
            available[key] = result
        else:
            missing.append(key)
    return available, missing


def _list_result(result: Any, *preferred_keys: str) -> list[dict[str, Any]]:
    """Normalize Sinum list responses across firmware variants.

    Most documented endpoints return a bare list after the {"data": ...} envelope
    is unwrapped. Some firmware builds return maps keyed by id/bus, or wrap the
    list once more in keys such as "items" or "devices".
    """
    if isinstance(result, list):
        return _dict_list(result)
    if not isinstance(result, dict):
        return []
    return _list_result_from_dict(result, preferred_keys)
