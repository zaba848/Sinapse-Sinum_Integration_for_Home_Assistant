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
| P5.2 Camera motion events | Planned — requires VIDEO hub online |
| P5.3 SBUS blind position feedback | Planned |
| LoRa relay PATCH live validation | Blocked — no relay hardware |
| Schedule editing UI | Read-only sensors + service only |
| Performance metrics / observability | Backlog |

---

## Archived plans

- [V0.7.0_IMPLEMENTATION_PLAN.md](V0.7.0_IMPLEMENTATION_PLAN.md) — superseded by 0.8.x
- [POST_RELEASE_PLAN.md](POST_RELEASE_PLAN.md) — v0.6.0 post-release (historical)
