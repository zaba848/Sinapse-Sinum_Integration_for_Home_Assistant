"""Public artifact sanitization checks."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRIVATE_IP_RE = re.compile(
    r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b"
)


def _public_artifacts() -> list[Path]:
    files: list[Path] = []
    files.extend(sorted(ROOT.glob("*.md")))
    files.extend(sorted((ROOT / "docs").glob("*.md")))
    files.extend(sorted((ROOT / "scripts").glob("*.py")))
    files.extend(sorted((ROOT / ".github" / "workflows").glob("*.yml")))
    files.extend(sorted((ROOT / ".github" / "workflows").glob("*.yaml")))
    return files


def test_public_artifacts_do_not_embed_private_lab_ips() -> None:
    offenders: list[str] = []
    for path in _public_artifacts():
        text = path.read_text(encoding="utf-8")
        for match in PRIVATE_IP_RE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{path.relative_to(ROOT)}:{line}: {match.group(0)}")

    assert not offenders, "Private lab IPs found in public artifacts:\n" + "\n".join(offenders)
