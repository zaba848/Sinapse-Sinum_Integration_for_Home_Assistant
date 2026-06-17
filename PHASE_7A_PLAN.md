# Phase 7A: WTP Fan Coil Climate Control

**Current Status**: 33% (SBUS ✅, WTP Climate Fields Dependent)

---

## What's Already Done

✅ **SBUS Fan Coils**: Full climate support (test_fan_coil.py with 22 tests)
- Temperature control (get/set)
- HVAC modes (heating, cooling, automatic, off)
- Fan speed control (3 gears)
- Fully tested and working

✅ **WTP Fan Coils (Full Climate)**: Already supported when hub provides full fields
- Code exists in `climate.py` lines 80-82
- Tests exist: `test_setup_adds_wtp_fan_coil_when_full_climate_fields_exist`
- Detection: requires both `work_mode` AND `target_temperature`
- Same climate entity class as SBUS: `SinumFanCoilClimate`

❌ **WTP Fan Coils (Partial/Shell)**: Not yet supported
- Some hubs expose WTP fan coils with only metadata (id, name, status)
- No temperature, mode, or fan control fields
- Currently skipped by the integration

---

## Phase 7A Implementation Strategy

### Step 1: Diagnostic (Run on your network)
```bash
python3 diagnose_wtp_climate.py
```
This will show:
- How many WTP fan coils your hub has
- Which ones have FULL climate fields (already supported)
- Which ones have PARTIAL fields (need Phase 7A)
- Which ones are SHELL ONLY (no climate data)

### Step 2: Decision Based on Diagnostic

**If all WTP fan coils have full climate fields:**
- Phase 7A is already ✅ COMPLETE
- No work needed; live testing will verify

**If some WTP fan coils have PARTIAL fields:**
- Implement fallback climate entity with available-only fields
- Or: fetch additional data from parent device / room / schedules
- Estimated effort: 2-3 hours

**If all WTP fan coils are SHELL ONLY:**
- Request firmware update from Sinum
- Or: implement diagnostic entity for metadata display
- Estimated effort: 1 hour

---

## Implementation Options (Conditional)

### Option A: Minimal Climate Entity (Fastest)
For WTP fan coils with only partial fields, create climate entity with:
- ✅ Current temperature (if available)
- ✅ Target temperature (if available)
- ✅ HVAC mode (if available)
- ❌ Fan control (if not available)
- ❌ Working state (if not available)

```python
def _has_any_climate_field(device):
    """Partial climate support: at least one temperature field."""
    return any(f in device for f in [
        "target_temperature",
        "room_temperature",
        "temperature"
    ])
```

### Option B: Data Enrichment (Robust)
If WTP fan coils lack climate fields, fetch from:
1. Parent device (usually contains aggregated state)
2. Room helpers (temperature targets)
3. Schedules (thermal schedules may have setpoints)
4. REST API additional endpoints

### Option C: Firmware Investigation (Best)
Contact Sinum support to understand why WTP fan coils lack climate fields:
- Is it a firmware limitation?
- Can fields be added via API update?
- Are fields available in different API endpoint?

---

## Files to Modify (If Needed)

### `custom_components/sinum/climate.py`
- Modify `_has_climate_control()` to support partial fields
- Add fallback logic for minimal climate entities
- Add data enrichment from parent devices (if Option B)

### `tests/test_fan_coil.py`
- Add test for partial WTP fan coil setup
- Add test for shell-only WTP fan coil (verify skipped)

### `tests/fixtures/sinum_devices.json`
- May need additional WTP fan coil variants for testing

---

## Testing Approach

1. **Unit Tests** (local):
   - Test partial climate entity creation
   - Test data enrichment from parent
   - Test fallback behavior

2. **Live Testing** (on your hub):
   - Verify real WTP fan coils are discovered as climate entities
   - Test temperature get/set operations
   - Test HVAC mode changes
   - Monitor MQTT for state updates

3. **Verification**:
   - HA Developer Tools → States (filter `sinum_`)
   - Should see all WTP fan coils exposed as climate entities
   - Entity count should match diagnostic output

---

## Effort Estimate

| Scenario | Effort | Completion |
|----------|--------|------------|
| All WTP have full fields | 0h | 100% ✅ |
| Some WTP partial fields | 2-3h | 95% (Option A or B) |
| All WTP shell only | 1h | 50% (Option C) |

---

## Next Steps

1. **Now**: Run `diagnose_wtp_climate.py` on your hub network
2. **Report**: Share diagnostic output showing WTP fan coil field availability
3. **Decide**: Which implementation option to pursue
4. **Implement**: Apply changes based on diagnostic findings
5. **Test**: Run live tests on your HA + hub system

---

## Acceptance Criteria (Phase 7A Complete)

- ✅ All WTP fan coils on your hub are discovered as climate entities (if they have any climate fields)
- ✅ Temperature get/set works for WTP fan coils
- ✅ HVAC modes available for WTP fan coils (if supported by hub)
- ✅ Tests updated for partial climate scenarios
- ✅ Live testing verifies MQTT state updates for WTP fan coils
- ✅ Documentation updated with WTP fan coil support status

