# API Endpoint Write Validation Report

Generated: 2026-06-25T04:30:00Z
Hub: 10.0.61.132 (WTP — tablica-wtp)

## Summary

- **Tests Executed**: A–E (LoRa relay, RGB/dimmer, heat pump, schedule, alarm)
- **Status**: 🔄 In Progress — Awaiting Hardware Execution

---

## Test A. LoRa Relay PATCH Scope

**Status**: 🔄 Pending

**Objective**: Determine if LoRa relay supports PATCH (state update) or is read-only.

**Plan**:
1. GET `/api/v1/devices/lora` to identify relay devices.
2. Attempt PATCH with `state: on` for each relay.
3. Verify state change reflects in GET response.
4. Record writable/read-only status for each relay.

**Expected Outcome**: Clarify LoRa relay write capability for HA service calls.

---

## Test B. RGB/Dimmer Idempotency

**Status**: 🔄 Pending

**Objective**: Ensure RGB and dimmer state updates are idempotent (repeated writes produce no spurious updates).

**Plan**:
1. Set RGB color to (R=255, G=0, B=0) twice on a WTP RGB device.
2. Set dimmer level to 75% twice on a WTP dimmer.
3. Set S-BUS dimmer level to 50% twice.
4. Monitor HA entity state changes (should not trigger spurious updates).
5. Verify coordinator does not log duplicate state transitions.

**Expected Outcome**: Confirm idempotency for UI smoothness and reliability.

---

## Test C. Heat Pump Manager Mode Matrix

**Status**: 🔄 Pending

**Objective**: Validate all valid mode transitions for heat pump manager (Virtual device).

**Plan**:
1. Enumerate all possible `mode` values for heat_pump_manager devices.
2. For each device, attempt all valid transitions (e.g., `OFF` → `HEAT` → `COOL` → `AUTO`).
3. Verify state change reflects correctly in HA climate entity.
4. Record any invalid transitions or state validation errors.

**Expected Outcome**: Define complete mode matrix for HA service call validation.

---

## Test D. Schedule State Transitions

**Status**: 🔄 Pending

**Objective**: Ensure schedule mode and setpoint updates persist and reflect correctly.

**Plan**:
1. Toggle schedule mode (day/week) and verify state in GET response.
2. Update temperature setpoint and confirm HA sensor reflects change.
3. Verify persistence across coordinator restart.

**Expected Outcome**: Confirm schedule updates are stable and reflected in entity state.

---

## Test E. Alarm Arm/Disarm Idempotency

**Status**: 🔄 Pending

**Objective**: Ensure alarm zone state transitions are idempotent.

**Plan**:
1. Arm an alarm zone twice and verify no spurious state change.
2. Disarm twice and verify consistency.
3. Test zone bypass toggle idempotency.

**Expected Outcome**: Confirm alarm operations produce correct, stable state.

---

## How to Run Tests

```bash
# Run live-write validation on WTP hub
python3 scripts/run_live_write_validation.py \
    --host 10.0.61.132 \
    --password <admin_password> \
    --output docs/live_write_validation_latest.md

# Or use environment variables
export SINUM_HOST=10.0.61.132
export SINUM_PASSWORD=<admin_password>
python3 scripts/run_live_write_validation.py
```

---

## Next Steps

1. **Execute tests** on both live hubs (WTP: 10.0.61.132, SBUS: 10.0.62.167).
2. **Collect results** and update this report with outcomes.
3. **Document findings** (especially LoRa relay PATCH scope and mode matrices).
4. **Update PLAN.md** with final status for section D.
5. **Commit & merge** to main with full CI gate validation.
