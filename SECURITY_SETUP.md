# Repository Hardening — Manual Setup Steps

This document provides step-by-step instructions for configuring GitHub security and quality settings that cannot be automated via code or workflows.

---

## 1. Branch Protection Rules (GitHub UI Required)

**Purpose**: Enforce code review, passing checks, and status verification before merge to main.

### Steps:

1. Go to repository: https://github.com/zaba848/sinapse-sinum-integration-for-home-assistant
2. Click **Settings** (top tab)
3. Select **Branches** (left sidebar under "Code and automation")
4. Click **Add rule** under "Branch protection rules"
5. Configure as follows:

| Setting | Value |
|---------|-------|
| Apply to | `main` |
| Require a pull request before merging | ✅ Checked |
| Require approvals | ✅ Checked (1 approval minimum) |
| Require status checks to pass before merging | ✅ Checked |
| Require branches to be up to date before merging | ✅ Checked |
| Require code quality gates | ✅ Checked |

6. **Under "Status checks that are required to pass"**, enable:
   - `CI / test`
   - `CodeQL`
   - `Lint`
   - `Functional Smoke Tests`
   - `Dependency Review`
   - `HACS Validation`

7. ✅ Click **Create** (or **Save changes** if updating)

**Result**: All future PRs to `main` will require passing tests + approvals.

---

## 2. Repository Security Settings (GitHub UI Required)

**Purpose**: Detect and prevent security vulnerabilities from entering the codebase.

### 2.1 Enable Dependabot Alerts

1. Go to **Settings** → **Security & analysis** (left sidebar)
2. Scroll to **Dependabot alerts**
3. Click **Enable** if disabled
4. Wait ~5–10 minutes for GitHub to scan existing dependencies

**Result**: Alerts will appear in the **Security** tab if vulnerable dependencies are found.

### 2.2 Enable Secret Scanning

1. Go to **Settings** → **Security & analysis**
2. Scroll to **Secret scanning**
3. Click **Enable** if disabled (may require GitHub Pro or public repo feature)

**Result**: GitHub will scan all commits for accidentally committed secrets (API keys, tokens, etc.).

### 2.3 Enable Push Protection

1. Go to **Settings** → **Security & analysis**
2. Scroll to **Push protection for secret scanning**
3. Click **Enable**

**Result**: Developers will be blocked from pushing commits containing secrets.

---

## 3. Security Tab Configuration (GitHub UI Required)

**Purpose**: Make security findings visible and actionable.

### Steps:

1. Go to **Security** tab (top)
2. Click **Set repository security and analysis settings** (if prompted)
3. Verify:
   - **Dependabot alerts** — enabled ✅
   - **Secret scanning** — enabled ✅
   - **Code scanning** (CodeQL) — enabled ✅

**Result**: Security findings will appear in the Security tab; developers will see alerts.

---

## 4. Nightly Hardware Tests — Self-Hosted Runner Setup

**Purpose**: Run actual hardware smoke tests every night on your test hubs.

**Prerequisites**:
- Test hubs running and reachable from the runner LAN/VPN
- macOS or Linux self-hosted runner with labels `self-hosted` and `sinum-lan`

### Steps:

1. **Create runner on test machine**:
   ```bash
   cd /path/to/runner/directory
   ./config.sh --url https://github.com/zaba848/sinapse-sinum-integration-for-home-assistant --token <TOKEN>
   ```
   (Token obtained from **Settings** → **Actions** → **Runners** → **New self-hosted runner**)

2. **Add runner secrets** (Settings → **Secrets and variables** → **Actions**):
   - Name: `SINUM_USERNAME` → Value: `admin` or your hub login
   - Name: `SINUM_PASSWORD` → Value: `<your-hub-password>`
   - Optional per-hub tokens: `SINUM_WTP_TOKEN`, `SINUM_SBUS_TOKEN`, `SINUM_VIDEO_TOKEN`

3. **Optional repository variable**:
   - Name: `SINUM_SMOKE_HUBS`
   - Value example: `WTP=http://<WTP_HUB_IP>,SBUS=http://<SBUS_HUB_IP>,VIDEO=http://<VIDEO_HUB_IP>`

4. **Verify workflow** is active:
   - Go to **.github/workflows/hardware-nightly.yml** (already committed)
   - It runs at 02:00 UTC daily or on manual trigger

**Result**: Every night at 02:00 UTC, GitHub runs smoke tests on your real hardware.

---

## 5. Per-Module Quality Gates — Monitoring

**Already Automated** ✅

These quality gates are **already live** in your CI:

- **`ci.yml`**: Runs `validate_coverage_gates.py` after test suite
- **Thresholds**:
  - `api.py`: 90% (currently 85% — will fail until reached)
  - `light.py`: 90% (currently 85%)
  - `cover.py`: 90% (currently 86%)
  - `sensor_virtual.py`: 90% (currently 87%)
  - Global: 80% (passing ✅)

**How to Improve**:
1. Add more test cases to the gap modules
2. Watch CI run: GitHub Actions → **CI** → **test** → **Validate per-module quality gates**

---

## 6. Release Notes Template (Already Available)

**Already Automated** ✅

- File: [CHANGELOG.md](CHANGELOG.md)
- Contains upgrade guide, best practices, and release notes sections
- New releases should follow the template

**Next steps for releases**:
1. Add new `## [X.Y.Z] — YYYY-MM-DD` section under `[Unreleased]`
2. Document changes under `### Added`, `### Changed`, `### Deprecated`, `### Fixed`, `### Removed`
3. Run release workflow (automatically creates GitHub release)

---

## 7. Test Stability Tracking (Already Active)

**Already Automated** ✅

- Workflow: `.github/workflows/test-stability.yml`
- Runs: Every Monday at 08:00 UTC + on manual trigger
- Reports: Slowest 10 tests, pass rate, failed count

**How to view results**:
1. Go to **Actions** tab
2. Select **Test Stability Report**
3. View latest run details and summary

---

## Summary

| Item | Status | Action |
|------|--------|--------|
| CODEOWNERS | ✅ Done | None — already in repo |
| Branch protection | 🟡 Manual | Follow section 1 above |
| Dependabot alerts | 🟡 Manual | Follow section 2.1 above |
| Secret scanning | 🟡 Manual | Follow section 2.2 above |
| Push protection | 🟡 Manual | Follow section 2.3 above |
| Quality gates | ✅ Done | Automatically runs in CI |
| Hardware nightly | 🟡 Manual | Follow section 4 above (requires runner) |
| Release template | ✅ Done | Use CHANGELOG.md format |
| Test stability | ✅ Done | Automatic weekly runs |

---

## Questions?

- Review [SECURITY.md](SECURITY.md) for vulnerability reporting
- Check [CONTRIBUTING.md](CONTRIBUTING.md) for contributor guidelines
- Open an issue if setup steps need clarification
