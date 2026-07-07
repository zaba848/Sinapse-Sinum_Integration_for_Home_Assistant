"""Release metadata consistency checks."""

from __future__ import annotations

import json
import re
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "custom_components" / "sinum" / "manifest.json"
PYPROJECT = ROOT / "pyproject.toml"
README_FILES = (ROOT / "README.md", ROOT / "README.pl.md")
CHANGELOG = ROOT / "CHANGELOG.md"
SECURITY = ROOT / "SECURITY.md"


def _manifest_version() -> str:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["version"]


def test_manifest_and_pyproject_versions_match() -> None:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    assert project["project"]["version"] == _manifest_version()


def test_readme_version_badges_match_manifest() -> None:
    version = _manifest_version()
    for readme in README_FILES:
        text = readme.read_text(encoding="utf-8")
        assert f"-{version}-blue.svg" in text
        assert "-0.7.5-blue.svg" not in text


def test_changelog_has_current_release_section() -> None:
    version = _manifest_version()
    text = CHANGELOG.read_text(encoding="utf-8")
    assert re.search(rf"^## \[{re.escape(version)}\] ", text, flags=re.MULTILINE)


def test_security_policy_mentions_current_minor_line() -> None:
    version = _manifest_version()
    major, minor, _patch = version.split(".", maxsplit=2)
    text = SECURITY.read_text(encoding="utf-8")
    assert f"{major}.{minor}.x" in text
