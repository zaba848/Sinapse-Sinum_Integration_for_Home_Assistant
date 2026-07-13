# Sinapse — Maintenance & Release Plan

**Current release:** 0.8.1  
**Last updated:** 2026-07-08

---

## Maintenance Cycles (completed in 0.8.1)

| Cycle | Scope | Status |
|---|---|---|
| 0 | `_bus_registry.py` — central bus routing | Done |
| 1 | `services.py` extraction from `__init__.py` | Done |
| 2 | Coordinator fetch driven by `BUS_REGISTRY` | Done |
| 3 | Lifecycle multi-hub tests + reconfigure WS path | Done |
| 4 | Coverage gates extended (websocket, lifecycle, sensor_modbus, services) | Done |

---

## Release checklist

1. Full pytest suite + 100% coverage
2. `scripts/validate_coverage_gates.py`
3. `scripts/check_release_gate.py`
4. Hardware smoke (`scripts/hardware_smoke_check.py`)
5. Tag + GitHub Release + HACS visibility
6. Deploy to HA RPi (`scripts/deploy_rpi.sh`)

---

## v0.9.0 backlog (not blocking 0.8.1)

| Item | Status |
|---|---|
| P5.2 Camera motion events | **Done** (`event.py`, `websocket.py::_handle_motion_detected`) — verified in code + `test_event.py`; still needs a live re-check once VIDEO hub is back online |
| P5.3 SBUS blind position feedback | **Done** — live via generic `_bus_registry` WS/MQTT routing into `sbus_devices`, not just REST poll; verified in `cover_sbus.py` + `test_cover_extended.py` |
| LoRa relay PATCH live validation | Blocked — no relay hardware |
| Schedule editing UI | Not planned — `update_schedule` service + read-only sensors already cover this; a dedicated UI isn't idiomatic HA (service calls are the standard pattern) unless a concrete user ask surfaces |
| Performance metrics / observability | Undefined scope — `diagnostics.py` already exposes bus/device counts + snapshots via HA's built-in diagnostics download; needs a concrete ask (e.g. coordinator update latency, WS reconnect counters) before this is actionable |

---

## Archived plans

- [V0.7.0_IMPLEMENTATION_PLAN.md](V0.7.0_IMPLEMENTATION_PLAN.md) — superseded by 0.8.x
- [POST_RELEASE_PLAN.md](POST_RELEASE_PLAN.md) — v0.6.0 post-release (historical)
