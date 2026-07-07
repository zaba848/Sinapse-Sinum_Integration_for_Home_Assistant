"""Coverage gate behavior tests."""

from __future__ import annotations

from scripts.validate_coverage_gates import (
    MODULE_THRESHOLDS,
    _normalize_filename,
    validate_gates,
)


def _full_coverage() -> dict[str, float]:
    return {module: 100.0 for module in MODULE_THRESHOLDS}


def test_validate_gates_passes_when_all_thresholds_are_met() -> None:
    assert validate_gates(_full_coverage())


def test_validate_gates_fails_when_a_module_drops_below_threshold() -> None:
    coverage = _full_coverage()
    coverage["custom_components/sinum/api.py"] = 99.0

    assert not validate_gates(coverage)


def test_validate_gates_fails_when_global_average_drops_below_threshold() -> None:
    coverage = _full_coverage()
    coverage["custom_components/sinum/extra.py"] = 99.0

    assert not validate_gates(coverage)


def test_normalize_filename_handles_absolute_and_windows_paths() -> None:
    assert (
        _normalize_filename("/tmp/repo/custom_components/sinum/api.py")
        == "custom_components/sinum/api.py"
    )
    assert (
        _normalize_filename(r"C:\repo\custom_components\sinum\api.py")
        == "custom_components/sinum/api.py"
    )
    assert _normalize_filename("api.py") == "custom_components/sinum/api.py"
    assert _normalize_filename("sinum/api.py") == "custom_components/sinum/api.py"
