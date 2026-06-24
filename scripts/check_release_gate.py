#!/usr/bin/env python3
"""Check release gate status from GitHub Actions.

Validates that required workflows have a recent successful run on main.
Intended for release operators and CI visibility.
"""

from __future__ import annotations

import json
import os
import urllib.request

REPO = os.getenv("GITHUB_REPOSITORY", "zaba848/Sinapse-Sinum_Integration_for_Home_Assistant")
API_URL = f"https://api.github.com/repos/{REPO}/actions/runs?per_page=100"
REQUIRED = {
    "CI",
    "CodeQL Security Analysis",
    "HACS Validation",
    "Lint",
}

# PR-only workflows are informative and should not block release on main.
OPTIONAL = {
    "Dependency Review",
}

# In push-triggered gate workflows, required runs can still be queued/in_progress.
# Allow these as non-blocking to avoid false-negative failures right after push.
ALLOW_PENDING = (
    os.getenv(
        "RELEASE_GATE_ALLOW_PENDING",
        "1" if os.getenv("GITHUB_EVENT_NAME") == "push" else "0",
    )
    == "1"
)


def fetch_runs() -> list[dict]:
    req = urllib.request.Request(API_URL, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.load(resp)
    return payload.get("workflow_runs", [])


def _latest_required_runs(runs: list[dict]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for run in runs:
        name = run.get("name")
        branch = run.get("head_branch")
        if name in REQUIRED and branch == "main" and name not in latest:
            latest[name] = run
    return latest


def _print_required_status(latest: dict[str, dict]) -> bool:
    failed = False
    for workflow in sorted(REQUIRED):
        run = latest.get(workflow)
        if not run:
            print(f"- {workflow}: MISSING")
            failed = True
            continue

        status = run.get("status")
        conclusion = run.get("conclusion")
        is_pending = status in {"queued", "in_progress"}
        ok = status == "completed" and conclusion == "success"
        mark = "PENDING" if is_pending and ALLOW_PENDING else ("OK" if ok else "FAIL")
        print(f"- {workflow}: {mark} (status={status}, conclusion={conclusion})")
        print(f"  {run.get('html_url')}")
        if not ok and not (is_pending and ALLOW_PENDING):
            failed = True
    return failed


def _print_optional_status(runs: list[dict]) -> None:
    for workflow in sorted(OPTIONAL):
        run = next(
            (r for r in runs if r.get("name") == workflow and r.get("head_branch") == "main"),
            None,
        )
        if not run:
            print(f"- {workflow}: OPTIONAL/MISSING")
            continue
        print(
            f"- {workflow}: OPTIONAL (status={run.get('status')}, conclusion={run.get('conclusion')})"
        )
        print(f"  {run.get('html_url')}")


def main() -> int:
    runs = fetch_runs()
    latest = _latest_required_runs(runs)

    print("Release Gate Check\n")
    failed = _print_required_status(latest)
    _print_optional_status(runs)

    print()
    if failed:
        print("Result: RELEASE GATE NOT MET")
        return 1

    print("Result: RELEASE GATE MET")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
