# Phase 7B: Temperature Regulator Support

**Status**: 0% (Planning & Implementation)
**Estimated Effort**: 3-4 hours
**Priority**: Q3 (after Phase 7A verification)

---

## What Are Temperature Regulators?

Temperature regulators are WTP devices that manage heating/cooling in zones. They:
- Read room temperature
- Control target temperature
- Have HVAC modes (heating, cooling, automatic, off)
- Are usually supervised by virtual thermostats (may duplicate)
- Have `mode_mutable` flag to control writability

**Real Hub Status** (from PLAN.md):
- Count: 8 WTP temperature regulators
- Status: Online
- Link: Supervised by virtual thermostats

---

## Device Structure

```json
{
  "id": 100,
  "type": "temperature_regulator",
  "class": "wtp",
  "name": "Zone Temperature Regulator",
  "room_id": 1,
  "temperature": 210,              // Current room temperature (×10)
  "target_temperature": 220,       // Target temperature (×10)
  "target_temperature_minimum": 50,
  "target_temperature_maximum": 300,
  "system_mode": "heating",        // Current mode
  "target_temperature_mode": "heating",  // Target mode
  "mode_mutable": true,            // Can user change mode?
  "parent_id": 10,                 // Supervised by parent device
  "status": "online"
}
```

---

## Implementation Strategy

### Option 1: Sensor-Only (Phase 7B.1) — START HERE
- Add as sensor entities (temperature display only)
- Add attributes: target_temp, mode, mode_mutable
- Minimal risk, useful diagnostics
- ~1.5 hours

### Option 2: Climate Entity (Phase 7B.2) — CONDITIONAL
- Add as climate entity (temperature control)
- Only enable if mode_mutable = true
- Link parent thermostat if available
- Decide after seeing real data
- ~1.5 hours

### Option 3: Thermostat Attributes (Phase 7B.3) — OPTIONAL
- Add as attributes on parent virtual thermostat
- Link zones to their supervisor
- Advanced feature
- ~1 hour

---

## Phase 7B.1: Sensor-Only Implementation (First Target)

### Files to Create/Modify
1. **custom_components/sinum/const.py**:
   - Add temperature regulator constants (already has WTYPE_TEMPERATURE_REGULATOR)

2. **tests/fixtures/sinum_devices.json**:
   - Add test fixtures: `wtp_temperature_regulator` variants

3. **custom_components/sinum/sensor.py**:
   - Add temperature regulator sensor entities
   - Current temperature, target temperature
   - Attributes: mode, mode_mutable, system_mode

4. **tests/test_sensor.py**:
   - Add tests for temperature regulator sensors

### Test Fixtures Needed
- `wtp_regulator_full`: Complete data with all fields
- `wtp_regulator_partial`: Minimal data (id, name, type)
- `wtp_regulator_immutable`: mode_mutable=false (read-only)

### Expected Entities
- `sensor.zone_temperature_regulator_temperature`: Current room temp (read-only)
- `sensor.zone_temperature_regulator_target_temperature`: Target temp (may become input_number later)
- Attributes on both: mode, mode_mutable, system_mode, parent_id

### Tests Required (Phase 7B.1)
- [ ] Regulator sensor reads current temperature
- [ ] Regulator sensor reads target temperature
- [ ] Attributes include mode, mode_mutable
- [ ] Partial regulator (missing fields) handles gracefully
- [ ] Setup discovers regulator sensors

---

## Phase 7B.2: Climate Entity (Conditional, After 7B.1)

Only if real diagnostic shows regulators should be climate entities.

### Considerations
1. **Duplication Risk**: Virtual thermostat already controls via parent
2. **Mode Control**: Respect mode_mutable flag
3. **Hierarchy**: Check if regulator is "supervised" by thermostat
4. **Entity Naming**: Show relationship to parent ("Zone 1 Regulator" not "Regulator")

### Implementation Notes
- Reuse SinumThermostat or SinumFanCoilClimate class logic
- Check mode_mutable before exposing set_hvac_mode
- Link parent_id to parent device for context
- Add in climate.py async_setup_entry

---

## Acceptance Criteria (Phase 7B Complete)

### Phase 7B.1: Sensor Entities ✅
- [ ] Temperature regulator current temperature sensor works
- [ ] Temperature regulator target temperature sensor works
- [ ] Attributes show mode, mode_mutable, system_mode
- [ ] Gracefully handles missing fields
- [ ] 4+ new tests passing
- [ ] Setup discovers all WTP temperature regulators as sensors

### Phase 7B.2: Climate Entity (If Needed)
- [ ] Climate entity optional (behind feature flag or explicit enable)
- [ ] Respects mode_mutable flag
- [ ] Temperature set/get works
- [ ] HVAC mode changes work
- [ ] MQTT updates received via real-time bridge
- [ ] Tests verify duplication handling

### Phase 7B Final
- [ ] Live testing on real hub confirms 8 regulators discovered
- [ ] Entity count: 8 current temp + 8 target temp sensors (minimum)
- [ ] No entity conflicts with existing thermostats
- [ ] Documentation updated with regulator support status

---

## Next Steps

1. **Create test fixtures** (wtp_regulator_*)
2. **Add sensor entities** in sensor.py
3. **Add tests** (4+ for Phase 7B.1)
4. **Run live test** when diagnostic ready
5. **Decide on climate** based on real hub data

---

## Timeline

| Phase | Task | Effort |
|-------|------|--------|
| 7B.1 | Sensor entities + tests | 1.5 hrs |
| 7B.2 | Climate entities (conditional) | 1.5 hrs |
| Live Testing | Verification on real hub | 30 min |
| **Total** | | 3-4 hrs |

