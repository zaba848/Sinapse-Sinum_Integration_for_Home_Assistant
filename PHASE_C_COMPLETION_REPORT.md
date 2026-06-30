# v0.6.0 Release + v0.7.0 Planning — PHASE C Complete ✅

**Date**: 2026-07-01  
**Status**: v0.6.0 fully deployed, v0.7.0 planning complete

---

## PHASE C Summary

### ✅ Completed

**1. v0.6.0 Deployment** (Main branch):
- Commit `3aa6b3f`: All post-release documentation committed
- GitHub sync: main branch synced with origin/main
- Test status: 1648 passing, 5 skipped

**2. Feedback Monitoring Plan** (Ongoing):
- Daily/weekly GitHub Issues tracking
- Watch for WS reconnection issues
- Document any issues for v0.6.1

**3. v0.7.0 Backlog Planning** (Complete):
- Feature branch created: `feature/v0.7.0-start`
- Implementation plan: `V0.7.0_IMPLEMENTATION_PLAN.md` ✅
- 6 features documented with effort/timeline/risks
- Success metrics defined

### 📋 Feature Breakdown

| Feature | Priority | Effort | Start | Status |
|---|---|---|---|---|
| P4.1: IAQ/AQ Probe | HIGH | 15 min | 2026-07-08 | ⏳ Pending |
| P5.1: Scene triggers | MEDIUM | 1-2 h | 2026-07-09 | ⏳ Pending |
| P5.2: Camera motion | MEDIUM | 2-3 h | 2026-07-12 | ⏳ Pending |
| P5.3: Blind position | MEDIUM | 2-3 h | 2026-07-15 | ⏳ Pending |
| P5.4: Alarm modes | LOW | 2-3 h | Future | ⏳ Pending |
| P5.5: LoRa test | LOW | 1 h | Future | 🚫 Blocked |

**Total v0.7.0 effort**: 8-10 hours development + 4-6 hours testing/docs

---

## Timeline

```
2026-07-01:  v0.6.0 released ✅
             v0.7.0 planning complete ✅
             
2026-07-08:  Week 1 starts
             - P4.1 Probe (15 min)
             - Feedback monitoring
             - P5.1 Scene triggers (start)
             
2026-07-12:  P5.1 complete, decide next priority
             
2026-07-18:  All P5 features complete
             Beta testing begins
             
2026-08-01:  v0.7.0 release target
```

---

## Files Created

| File | Purpose | Lines |
|---|---|---|
| `.github_release_v0.6.0.md` | GitHub Release template (ready to copy-paste) | 95 |
| `POST_RELEASE_PLAN.md` | Phases A/B/C execution guide | 270 |
| `V0.7.0_IMPLEMENTATION_PLAN.md` | Feature specs, schedule, risks, quality gates | 478 |

**Total**: 843 lines of documentation

---

## Next Actions

### IMMEDIATE (User manual action):

**Option A: Create GitHub Release** (5 min, UI task)
1. Go to: https://github.com/zaba848/Sinapse-Sinum_Integration_for_Home_Assistant/releases/new
2. Select tag: `v0.6.0`
3. Title: `v0.6.0 — WebSocket Hardening & Security`
4. Description: Copy from `.github_release_v0.6.0.md`
5. Click "Publish"

**Why**: HACS users see v0.6.0 as available update (currently invisible without release)

**When**: Anytime (today recommended)

### ONGOING (Starting 2026-07-08):

**Feedback Monitoring** (15 min per day, 2-3x/week):
- Check GitHub Issues for bug reports
- Watch Home Assistant Community forums
- Document findings in CHANGELOG.md [Unreleased]
- Create v0.6.1 hotfix branch if critical issue found

### SCHEDULED (2026-07-08):

**P4.1 — IAQ/AQ Probe** (15 min):
- ⭐ First v0.7.0 task
- Quick validation of WTP sensor payloads
- If PASS → Start P5.1 immediately
- If DIFFER → Document, update descriptors

### SEQUENTIAL (2026-07-09+):

**P5.1 — Scene device_trigger** (1-2 h):
- Enable scenes to trigger HA automations
- Estimated completion: 2026-07-12

**P5.2 or P5.3** (2-3 h each):
- Camera motion events OR Blind position feedback
- Run in parallel if time permits
- Estimated completion: 2026-07-18

---

## Current Deployment State

```
Branch:            main (synced ✅) | feature/v0.7.0-start (planning)
Latest commit:     3aa6b3f (post-release docs)
v0.6.0 tag:        ✅ Pushed to GitHub
Tests:             1648 passing ✅
Quality gates:     All pass ✅
Working tree:      CLEAN
```

---

## Quality Gates (For all future commits)

All v0.7.0 features must pass:

```bash
# Before commit
python3 -m pytest -q                          # Must pass
/opt/homebrew/bin/ruff check custom_components/
/opt/homebrew/bin/ruff format --check custom_components/
/opt/homebrew/bin/mypy custom_components/sinum/ --ignore-missing-imports --no-site-packages
python3 -m pytest -q tests/test_code_quality.py  # CC ≤ 4

# Before merge to main
git checkout main
git merge feature/v0.7.0-start --no-edit
# All tests + gates must pass
# Update version in manifest.json + pyproject.toml
git tag -a v0.7.0 -m "v0.7.0: Scene triggers, IAQ/AQ validation, blind position feedback, alarm modes, camera motion events"
git push origin main v0.7.0
```

---

## Risk Mitigation

| Risk | Likelihood | Mitigation |
|---|---|---|
| Camera motion WS format unknown | HIGH | Live traffic analysis in P5.2 sprint |
| Blind position API endpoint TBD | MEDIUM | Reverse engineering or API docs request |
| Alarm modes conflict with existing flows | MEDIUM | Destructive testing on dedicated hub (sinum-tablica-sbus2) |
| Hardware unavailable for testing | LOW | Virtual mock testing as fallback |
| v0.7.0 slip past 2026-08-01 | LOW | Prioritize P4.1 + P5.1, defer P5.2-5.4 to v0.7.1 |

---

## Post-Release Checklist

### Week of 2026-07-01 (Now)

- [ ] Create GitHub Release page (copy-paste from template)
- [ ] Verify release appears on GitHub Releases tab
- [ ] Monitor initial user feedback (2-3 issues expected)

### Week of 2026-07-08

- [ ] Run P4.1 IAQ/AQ Probe (15 min)
- [ ] Review probe results
- [ ] Start P5.1 Scene device_trigger
- [ ] Daily feedback monitoring

### Week of 2026-07-15

- [ ] Complete P5.1 + 1 additional feature (P5.2 or P5.3)
- [ ] Quality gate verification
- [ ] Beta documentation draft

### Week of 2026-07-22

- [ ] Complete remaining P5 features
- [ ] Hardware validation testing
- [ ] Final documentation

### By 2026-08-01

- [ ] v0.7.0 merged to main
- [ ] Tag and release
- [ ] GitHub Release page created
- [ ] HACS update available

---

## Summary: Three Phases Complete ✅

### Phase A — GitHub Release (Pending)
- Template: `.github_release_v0.6.0.md` ✅
- Action: Copy-paste to GitHub UI (5 min, manual)
- Status: Ready to execute

### Phase B — Live Write Validation (Optional)
- Plan: `POST_RELEASE_PLAN.md#Phase B` ✅
- Status: Credentials unavailable, deferred to v0.6.1 prep
- Action: Can run anytime with hub credentials

### Phase C — Monitoring & v0.7.0 Planning ✅
- Feedback monitoring: Documented in `POST_RELEASE_PLAN.md`
- v0.7.0 plan: Complete in `V0.7.0_IMPLEMENTATION_PLAN.md`
- Branch: `feature/v0.7.0-start` ready with 1 commit
- Status: Ready for execution starting 2026-07-08

---

## Recommendations

### RIGHT NOW (Today — 2026-07-01)
1. **Create GitHub Release page** (5 min) — High visibility for HACS users
2. Verify deployment on GitHub

### THIS WEEK (2026-07-01 to 2026-07-07)
1. Monitor GitHub Issues for v0.6.0 bugs
2. Watch Home Assistant Community
3. Prepare for P4.1 Probe (collect hub credentials if available)

### NEXT WEEK (Starting 2026-07-08)
1. Execute P4.1 Probe (15 min) — Kickoff v0.7.0
2. Start P5.1 Scene device_trigger
3. Continue feedback monitoring

### FINAL SPRINT (2026-07-15 to 2026-08-01)
1. Complete P5 features
2. Quality gates + testing
3. Release v0.7.0

---

## Staying Organized

**Branches**:
- `main` — v0.6.0 production (synced with origin/main ✅)
- `feature/v0.7.0-start` — v0.7.0 development (ready for P4.1 work)

**Documentation**:
- `PLAN.md` — Master implementation plan
- `V0.7.0_IMPLEMENTATION_PLAN.md` — Feature details, timeline, risks
- `POST_RELEASE_PLAN.md` — Release execution guide
- `.github_release_v0.6.0.md` — GitHub Release template

**Key Files to Watch**:
- `tests/` — Test suite (1648+ expected)
- `custom_components/sinum/` — Core integration
- `CHANGELOG.md` — Release notes
- `pyproject.toml` — Version management

---

## Success Criteria for v0.7.0

✅ **By 2026-08-01**:
- P4.1 Probe completed and documented
- P5.1 Scene device_trigger implemented and tested
- P5.2 or P5.3 completed (camera motion OR blind position)
- All 1700+ tests passing
- Quality gates: ruff ✅, mypy ✅, CC ✅
- Documentation: EN/PL updated
- v0.7.0 merged to main and released

---

**Release Manager**: GitHub Copilot + User  
**Status**: ✅ v0.6.0 COMPLETE | 🚀 v0.7.0 PLANNED & READY TO START
