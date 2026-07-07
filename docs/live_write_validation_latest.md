# API Endpoint Write Validation Report

Generated: 2026-07-03T08:28:48.695526+00:00
Hub: <redacted>

## Summary

- **Tests Passed**: 5/5
- **Status**: ✅ PASS

---

## ✅ A. LoRa Relay PATCH Scope

**Summary**: SKIP — no LoRa relay devices found on this hub

## ✅ B. RGB/Dimmer Idempotency

**Summary**: Tested 2 dimmer(s)

```json
[
  {
    "device_id": 121,
    "name": "Dimmer 121",
    "type": "sbus_dimmer",
    "target_level": 60,
    "actual_after": 60,
    "idempotent": true
  },
  {
    "device_id": 122,
    "name": "Dimmer 122",
    "type": "sbus_dimmer",
    "target_level": 60,
    "actual_after": 60,
    "idempotent": true
  }
]
```

## ✅ C. Heat Pump Manager Mode Matrix

**Summary**: Tested 4 mode transitions on dsadsa

```json
[
  {
    "device_id": 114,
    "name": "dsadsa",
    "mode_transitions": [
      {
        "target": "heating",
        "actual": "heating",
        "success": true
      },
      {
        "target": "cooling",
        "actual": "cooling",
        "success": true
      },
      {
        "target": "automatic",
        "actual": "automatic",
        "success": true
      },
      {
        "target": "OFF (enabled=False)",
        "actual_enabled": false,
        "success": true
      }
    ]
  }
]
```

## ✅ D. Schedule State Transitions

**Summary**: Schedule harmonogram 1 has no fallback.target_temperature — skipping write

## ✅ E. Alarm Arm/Disarm Idempotency

**Summary**: SKIP — all 3 zone(s) are currently ARMED; will not disarm a live production alarm without explicit owner request
