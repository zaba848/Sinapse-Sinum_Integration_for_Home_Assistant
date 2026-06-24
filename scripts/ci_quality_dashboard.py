#!/usr/bin/env python3
"""Generate CI quality dashboard summary from GitHub Actions runs."""

from __future__ import annotations

import json
import os
import statistics
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = os.getenv("GITHUB_REPOSITORY", "zaba848/Sinapse-Sinum_Integration_for_Home_Assistant")
API_URL = f"https://api.github.com/repos/{REPO}/actions/runs?per_page=100"
OUT_MD = Path("docs/ci_quality_dashboard.md")


def fetch_runs() -> list[dict]:
    req = urllib.request.Request(API_URL, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.load(resp)
    return payload.get("workflow_runs", [])


def minutes_between(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    s = datetime.fromisoformat(start.replace("Z", "+00:00"))
    e = datetime.fromisoformat(end.replace("Z", "+00:00"))
    return (e - s).total_seconds() / 60


def main() -> int:
    runs = fetch_runs()

    ci_main = [r for r in runs if r.get("name") == "CI" and r.get("head_branch") == "main"]
    ci_completed = [r for r in ci_main if r.get("status") == "completed"]
    ci_success = [r for r in ci_completed if r.get("conclusion") == "success"]

    pass_rate = (len(ci_success) / len(ci_completed) * 100) if ci_completed else 0.0
    durations = [
        d
        for d in (
            minutes_between(r.get("run_started_at"), r.get("updated_at")) for r in ci_completed
        )
        if d is not None
    ]
    avg_duration = statistics.mean(durations) if durations else 0.0
    p95_duration = (
        statistics.quantiles(durations, n=20)[18] if len(durations) >= 20 else avg_duration
    )

    flaky_proxy = len([r for r in ci_completed if int(r.get("run_attempt", 1)) > 1])

    lines = [
        "# CI Quality Dashboard",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}",
        "",
        "## Main Metrics (CI on main)",
        f"- Total completed runs analyzed: {len(ci_completed)}",
        f"- Pass rate: {pass_rate:.1f}%",
        f"- Average duration: {avg_duration:.2f} min",
        f"- P95 duration: {p95_duration:.2f} min",
        f"- Flaky proxy (rerun attempts > 1): {flaky_proxy}",
        "",
        "## Recent CI Runs",
    ]

    for run in ci_main[:10]:
        lines.append(
            f"- {run.get('status')}/{run.get('conclusion')} | #{run.get('run_number')} | {run.get('html_url')}"
        )

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")

    print(f"Dashboard written to {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
