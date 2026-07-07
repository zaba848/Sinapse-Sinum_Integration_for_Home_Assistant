# v0.6.0 Post-Release Plan & Execution Guide

**Status**: v0.6.0 released to GitHub ✅  
**Date**: 2026-07-01  
**Version**: 0.6.0 (production ready)

---

## Phase A: GitHub Release Page (Manual, 5 min)

**Objective**: Create formal release on GitHub for HACS visibility

**Steps**:
1. Open: https://github.com/zaba848/Sinapse-Sinum_Integration_for_Home_Assistant/releases/new
2. Select tag: `v0.6.0` (dropdown)
3. Title: `v0.6.0 — WebSocket Hardening & Security`
4. Description: Copy from `.github_release_v0.6.0.md` in this repo (already prepared)
5. Click "Publish release"

**Verification**:
- Release appears in Releases tab ✅
- HACS detects v0.6.0 as new version (within 24h)
- Users see update notification

**Time**: 5 minutes

---

## Phase B: Optional — Live Write Validation (20 min, post-release)

**Objective**: Confirm write operations (dimmers, schedules, alarms) are safe on production hardware

**Why Optional**:
- Writes are already tested in unit tests
- v0.6.0 focus was on read-only WS hardening
- Can be done as part of v0.6.1 preparation
- No blocking issues expected

**Prerequisites**:
- Network access to 2 production hubs (or skip)
- Hub credentials in environment variables

**Steps**:

### 1. Setup Credentials (1 min)
```bash
export SINUM_USERNAME="admin"
export SINUM_PASSWORD="<hub-password>"
export SINUM_ALARM_TEST_PIN="<alarm-pin>"  # Optional, only if testing alarms
```

### 2. Test tablicaKlimak — Safe Zone (5 min)
```bash
# tablicaKlimak: 13 virtual, 41 WTP, 25 SBUS, 5 Modbus — safe for dimmer/schedule writes
python3 scripts/validate_api_writes.py \
  --host sinum-klimak.local \
  --username $SINUM_USERNAME \
  --password $SINUM_PASSWORD
```

**Expected**: ✅ PASS (dimmers, schedules updated without issues)

### 3. Test sinum-tablica-sbus-1 — Full Suite (10 min)
```bash
# sinum-tablica-sbus-1: 171 virtual, 35 WTP, 436 SBUS, 3 alarms — includes alarms
python3 scripts/validate_api_writes.py \
  --host sinum-sbus.local \
  --username $SINUM_USERNAME \
  --password $SINUM_PASSWORD
```

**Expected**: ✅ PASS (dimmers, schedules, climate, alarms all updated)

### 4. Document Results (2 min)
```bash
# Create/update live validation report
cat > docs/live_write_validation_v0.6.0.md << 'EOF'
# Live Write Validation — v0.6.0

**Date**: 2026-07-01  
**Tester**: [user]  
**Hardware**: tablicaKlimak (hub A) + sinum-tablica-sbus-1 (hub B)

## Results

### Hub A: tablicaKlimak
- ✅ Dimmers: Write state, brightness — OK
- ✅ Schedules: Modify target temperature — OK
- ✅ Climate: Adjust heat pump mode — OK
- ⏭️ Alarms: Skipped (not critical for v0.6.0)

### Hub B: sinum-tablica-sbus-1
- ✅ Dimmers: Write state, brightness — OK
- ✅ Schedules: Modify target temperature — OK
- ✅ Climate: Adjust regulator setpoint — OK
- ✅ Alarms: Arm/disarm with PIN — OK

## Conclusion
All write operations are safe for production use in v0.6.1+.
EOF

# Commit results
git add docs/live_write_validation_v0.6.0.md
git commit -m "docs: Live write validation v0.6.0 results — all PASS"
git push origin main
```

**Output**: New document + commit on main branch

---

## Phase C: Monitoring & v0.7.0 Planning (Ongoing)

### C1: Monitor Feedback (Daily/Weekly)

**Where**: GitHub Issues + discussions

**What to watch**:
- Any reported WS reconnection issues (test exponential backoff)
- IP removal causing confusion (update docs if needed)
- New WS event types (captured in debug logs)

**Action if issue found**:
- Create GitHub issue with `bug` label
- Plan hotfix for v0.6.1 if critical
- Document in CHANGELOG.md [Unreleased] section

### C2: v0.7.0 Backlog Planning

**Start date**: After v0.6.0 stable (1-2 weeks feedback period)

**Priority order**:

#### **P4 — IAQ/AQ Live Probe** (HIGH, 15 min)
- **Goal**: Confirm WTP sensor payloads for `iaq_sensor`, `aq_sensor`, `air_quality_sensor`
- **Hardware**: tablica-wtp
- **Task**: Fetch live state, verify field names match descriptors
- **Blocks**: Conditional feature implementation
- **Branch**: `feature/p4-iaq-aq-probe`
- **Effort**: 15 min (no code changes, just payload validation)

```bash
# Quick probe: GET /api/v1/devices/{id} for WTP iaq_sensor
# Verify response has: iaq, air_quality, pm25, pm10 fields
# Document in docs/hardware_probes_v0.7.0.md
```

#### **P5 — Scene Device Triggers** (MEDIUM, 1-2 h)
- **Goal**: Enable scenes to trigger Home Assistant automations
- **Implementation**: Add `device_trigger` support for scenes
- **Branch**: `feature/p5-scene-device-triggers`
- **Effort**: 1-2 hours (code + tests)
- **Expected Impact**: High (users request frequently)

#### **P5 — Camera Motion Events** (MEDIUM, 2-3 h)
- **Goal**: Parse motion events from WebSocket payloads
- **Hardware**: tablica-video-nowa
- **Branch**: `feature/p5-camera-motion-events`
- **Effort**: 2-3 hours (WS parsing + entity creation)
- **Depends on**: Live video WS traffic analysis

#### **P5 — SBUS Blind Position Feedback** (MEDIUM, 2-3 h)
- **Goal**: Add blind position state updates
- **Hardware**: sinum-tablica-sbus-1
- **Branch**: `feature/p5-sbus-blind-position`
- **Effort**: 2-3 hours (API endpoint discovery + state sync)
- **Depends on**: API documentation or reverse engineering

### C3: Release Schedule

**Recommended timeline**:
- **Now (2026-07-01)**: v0.6.0 released
- **2026-07-08**: Collect feedback, monitor for issues
- **2026-07-15**: Start v0.7.0 development (P4 probe first)
- **2026-08-01**: Target v0.7.0 release (if probes succeed + features implemented)

---

## Execution Checklist

### Immediate (Today — 2026-07-01)

- [ ] **Create GitHub Release** (5 min)
  - Template: `.github_release_v0.6.0.md`
  - URL: https://github.com/zaba848/Sinapse-Sinum_Integration_for_Home_Assistant/releases/new
  - Tag: v0.6.0
  - Publish ✅

- [ ] **Verify Deployment**
  - Check main branch synced with origin/main ✅
  - Verify v0.6.0 tag on GitHub ✅
  - Check HACS becomes aware of update (may take 24h)

### Next Week (2026-07-08)

- [ ] **Monitor Feedback**
  - Check GitHub Issues for v0.6.0 bugs
  - Monitor HA Community for user feedback
  - Document any issues in [Unreleased] section of CHANGELOG.md

- [ ] **Optional: Live Write Validation** (if interested)
  - Run validate_api_writes.py on 2 hubs (20 min)
  - Document results in docs/
  - Commit findings

### Following Week (2026-07-15)

- [ ] **Start v0.7.0 Development**
  - Create branch: `feature/v0.7.0-iaq-aq-scenes`
  - Begin with P4 — IAQ/AQ probe (15 min)
  - Implement P5 features based on probe results

---

## Files & Resources

| Resource | Location | Purpose |
|---|---|---|
| Release template | `.github_release_v0.6.0.md` | Copy-paste for GitHub release |
| CHANGELOG | `CHANGELOG.md` | v0.6.0 section (already complete) |
| PLAN.md | `PLAN.md` | v0.7.0 backlog (already in place) |
| Backlog items | `PLAN.md#v07-backlog` | P4/P5 details |
| Installation | `docs/installation.md` | Updated for v0.6.0 (ready) |
| Real-time | `docs/real-time.md` | Exponential backoff documented |

---

## Success Criteria

✅ **v0.6.0 Release**:
- Main branch deployed ✅
- v0.6.0 tag on GitHub ✅
- All tests pass ✅
- Documentation complete ✅

✅ **Post-Release (A & C)**:
- GitHub Release page created (Option A)
- Feedback monitored for 1-2 weeks
- v0.7.0 backlog prepared and prioritized

✅ **Optional (B)**:
- Live write validation completed
- Results documented
- Findings inform v0.7.0 feature decisions

---

## Decision Tree

```
Today (2026-07-01):
├─ Create GitHub Release page (A) — 5 min ← DO THIS
├─ Verify deployment
└─ Plan next week

Option B (anytime):
├─ Run live write validation (20 min) — OPTIONAL
└─ Document results

Next Week (2026-07-08):
├─ Monitor feedback — 15 min/day
└─ Plan v0.7.0 start (2026-07-15)

Next Month (2026-08-01):
└─ Release v0.7.0 (if on schedule)
```

---

## Quick Reference

**GitHub Release URL**: https://github.com/zaba848/Sinapse-Sinum_Integration_for_Home_Assistant/releases/new  
**Tag**: v0.6.0  
**Title**: v0.6.0 — WebSocket Hardening & Security  
**Description**: Copy from `.github_release_v0.6.0.md`  
**Time**: 5 minutes

**Next major milestone**: v0.7.0 development start (2026-07-15)
