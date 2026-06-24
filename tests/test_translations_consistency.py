"""UI/UX translation consistency tests.

These tests guard user-facing config/options/entity labels so translation drift
is caught in CI instead of at runtime.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parent.parent / "custom_components" / "sinum"
STRINGS_PATH = BASE / "strings.json"
EN_PATH = BASE / "translations" / "en.json"
PL_PATH = BASE / "translations" / "pl.json"


def _flatten_keys(node: object, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else key
            keys.add(path)
            keys |= _flatten_keys(value, path)
    return keys


def _focused_ui_keys(document: dict[str, object]) -> set[str]:
    out: set[str] = set()
    for section in ("config", "options", "entity"):
        if section in document:
            out |= _flatten_keys({section: document[section]})
    return out


@pytest.mark.parametrize("translation_path", [EN_PATH, PL_PATH])
def test_translation_keys_match_strings_json(translation_path: Path) -> None:
    strings = json.loads(STRINGS_PATH.read_text(encoding="utf-8"))
    translation = json.loads(translation_path.read_text(encoding="utf-8"))

    strings_keys = _focused_ui_keys(strings)
    translation_keys = _focused_ui_keys(translation)

    missing = sorted(strings_keys - translation_keys)
    extra = sorted(translation_keys - strings_keys)

    assert not missing, f"Missing keys in {translation_path.name}: {missing}"
    assert not extra, f"Unexpected keys in {translation_path.name}: {extra}"
