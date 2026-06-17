# Phase 7B.2: Temperature Regulator Climate Entities (Experimental)

**Status**: Implemented (Disabled by Default)
**Rationale**: Regulators are usually supervised by virtual thermostats; climate entities only useful if they add direct control not available via supervisor.

---

## Design

### Entity: SinumTemperatureRegulatorClimate

Similar to SinumThermostat but with awareness of supervision and mode constraints:

```python
class SinumTemperatureRegulatorClimate(CoordinatorEntity[SinumCoordinator], ClimateEntity):
    """Optional climate entity for WTP temperature regulators (Phase 7B.2).
    
    Disabled by default. Enable only if diagnostics show regulators add value
    not available through parent thermostat supervision.
    """
    - Read current temperature from device.temperature
    - Read/set target temperature (only if mode_mutable=true)
    - Display mode from system_mode (read-only if mode_mutable=false)
    - Show parent_id in attributes for supervisor context
    - Features: TARGET_TEMPERATURE (always), HVAC_MODE (only if mutable)
```

### Setup Logic (Currently Disabled)

```python
# In async_setup_entry (disabled by default, can be enabled via feature flag)
if ENABLE_EXPERIMENTAL_REGULATOR_CLIMATE:
    for device_id, device in coordinator.wtp_devices.items():
        if device.get("type") == WTYPE_TEMPERATURE_REGULATOR:
            # Only expose as climate if has temperature fields
            if "temperature" in device or "target_temperature" in device:
                entities.append(
                    SinumTemperatureRegulatorClimate(coordinator, device_id, entry.entry_id)
                )
```

### Constraints Enforced

- **mode_mutable = false**: No hvac_mode setter, read-only display
- **mode_mutable = true**: Full climate control available
- **Supervision**: parent_id shown in attributes for context
- **No duplication**: User can disable if conflicts with parent thermostat

---

## Tests (5 tests in test_climate.py)

1. **test_regulator_reads_temperature**: Current temperature reading
2. **test_regulator_reads_target_temperature**: Target temperature reading
3. **test_regulator_mutable_mode_allows_set**: set_hvac_mode works when mutable
4. **test_regulator_immutable_mode_no_set**: set_hvac_mode blocked when immutable
5. **test_regulator_shows_parent_in_attributes**: parent_id displayed

---

## Decision Matrix

| Real Hub Data | Recommendation | Implementation |
|---------------|----------------|-----------------|
| Regulators have same fields as supervisor | Skip (duplication) | Phase 7B.1 only (sensors) |
| Regulators add independent control | Implement | Phase 7B.2 (enable climate) |
| Users report duplication issues | Skip | Disable in future |
| Users want direct control | Implement | Phase 7B.2 (enable) |

---

## Implementation Status

- ✅ Class designed (SinumTemperatureRegulatorClimate)
- ✅ Tests written (5 tests)
- ✅ Disabled by default (no impact on Phase 7E deployment)
- ✅ Ready to enable after live testing decision

---

## Activation Process (When Needed)

1. User reports: "I want direct temperature control on regulators"
2. Enable: `ENABLE_EXPERIMENTAL_REGULATOR_CLIMATE = True`
3. Restart HA
4. Verify: Discover 8 additional climate entities (regulator controls)
5. Test: Set temperature, change HVAC mode
6. If working: Move to production
7. If duplication: Revert to sensors-only

---

## Next Steps

- [ ] Live testing: diagnose WTP regulator value
- [ ] Decision: climate entities needed?
- [ ] If YES: Enable Phase 7B.2 implementation
- [ ] If NO: Phase 7B complete at 50% (sensors-only)

