"""Code quality gate: enforce CC < 5 on all functions in the sinum integration.

Files with known legacy violations (pre-existing, not introduced in recent changes)
are tracked here. New violations in those files will still fail the test.
Reduce or remove entries as legacy code is cleaned up.
"""

from __future__ import annotations

import pathlib

import pytest

try:
    from radon.visitors import ComplexityVisitor

    _RADON_AVAILABLE = True
except ImportError:
    _RADON_AVAILABLE = False

_SINUM_DIR = pathlib.Path(__file__).parent.parent / "custom_components" / "sinum"
_MAX_CC = 4

_LEGACY_ALLOWANCE: dict[str, dict[str, int]] = {
    "alarm_control_panel.py": {
        "async_setup_entry": 7,
        "extra_state_attributes": 5,
    },
    "binary_sensor.py": {
        "_add_sensors_for_bus": 6,
        "is_on": 5,
        "extra_state_attributes": 5,
    },
    "button.py": {
        "async_setup_entry": 6,
    },
    "camera.py": {
        "extra_state_attributes": 5,
    },
    "cover.py": {
        "_restore_cover_from_last_state": 6,
        "async_added_to_hass": 5,
        "is_opening": 5,
        "is_closing": 5,
        "__init__": 5,
    },
    "light.py": {
        "_add_bus_lights": 7,
        "_supports_rgb": 6,
        "async_turn_on": 6,
        "_bus_light_entity": 5,
        "_color_mode": 5,
        "async_added_to_hass": 5,
        "_sbus_lua_commands": 5,
        "_apply_sbus_color": 5,
        "async_turn_off": 5,
    },
    "number.py": {
        "_load_variables": 5,
        "__init__": 5,
    },
    "sensor_schedule.py": {
        "_day_entries": 7,
    },
    "sensor_virtual.py": {
        "native_value": 6,
    },
    "switch.py": {
        "__init__": 6,
    },
}


def _is_legacy_allowed(filename: str, func_name: str, cc: int) -> bool:
    allowed = _LEGACY_ALLOWANCE.get(filename, {})
    return cc <= allowed.get(func_name, _MAX_CC)


def _collect_violations() -> list[tuple[str, str, int, int]]:
    violations: list[tuple[str, str, int, int]] = []
    for py_file in sorted(_SINUM_DIR.glob("*.py")):
        src = py_file.read_text(encoding="utf-8")
        try:
            blocks = ComplexityVisitor.from_code(src).blocks
        except SyntaxError:
            continue
        for block in blocks:
            if block.complexity > _MAX_CC:
                if not _is_legacy_allowed(py_file.name, block.name, block.complexity):
                    violations.append((py_file.name, block.name, block.complexity, block.lineno))
    return violations


@pytest.mark.skipif(not _RADON_AVAILABLE, reason="radon not installed")
def test_cyclomatic_complexity_gate() -> None:
    """All functions must have CC <= 4 (CC < 5).

    Functions in _LEGACY_ALLOWANCE are exempt up to their listed CC value.
    Remove entries as legacy code is cleaned up.
    """
    violations = _collect_violations()
    if not violations:
        return
    lines = [f"  {fn}:{name} L{ln} CC={cc}" for fn, name, cc, ln in violations]
    raise AssertionError(
        f"Cyclomatic complexity violations (CC > {_MAX_CC}):\n" + "\n".join(lines)
    )


@pytest.mark.skipif(not _RADON_AVAILABLE, reason="radon not installed")
def test_legacy_allowance_not_exceeded() -> None:
    """Legacy-allowed functions must not exceed their grandfathered CC limit.

    This catches regressions where legacy code gets even more complex.
    """
    violations: list[str] = []
    for py_file in sorted(_SINUM_DIR.glob("*.py")):
        filename = py_file.name
        if filename not in _LEGACY_ALLOWANCE:
            continue
        src = py_file.read_text(encoding="utf-8")
        try:
            blocks = ComplexityVisitor.from_code(src).blocks
        except SyntaxError:
            continue
        allowed = _LEGACY_ALLOWANCE[filename]
        for block in blocks:
            limit = allowed.get(block.name)
            if limit is not None and block.complexity > limit:
                violations.append(
                    f"  {filename}:{block.name} L{block.lineno} CC={block.complexity} (limit={limit})"
                )
    if violations:
        raise AssertionError(
            "Legacy functions exceeded their CC allowance:\n" + "\n".join(violations)
        )
