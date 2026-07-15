# Sinapse — Maintenance & Release Plan

**Current release:** 0.8.2  
**Last updated:** 2026-07-15

---

## Maintenance Cycles (completed in 0.8.1)

| Cycle | Scope | Status |
|---|---|---|
| 0 | `_bus_registry.py` — central bus routing | Done |
| 1 | `services.py` extraction from `__init__.py` | Done |
| 2 | Coordinator fetch driven by `BUS_REGISTRY` | Done |
| 3 | Lifecycle multi-hub tests + reconfigure WS path | Done |
| 4 | Coverage gates extended (websocket, lifecycle, sensor_modbus, services) | Done |
| 5 | `patch_wtp_device`/`patch_sbus_device` dispatch + store-lookup consolidation (`_bus_registry.bus_patch_method`/`bus_store`) across climate/fan/select/light/event/sensor_bus | Done — 0.8.2 |

## Shipped in 0.8.2

- Cycle 5 above (dispatch/store-lookup consolidation)
- Performance metrics in `diagnostics.py`: request/retry/coalescing counters, coordinator update latency, WS reconnect counters — closes the "Performance metrics / observability" backlog item below

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
| Performance metrics / observability | **Done — 0.8.2** — `diagnostics.py` now includes `last_update_duration_ms`, `last_update_success_time`, `fetch_failure_count`, HTTP request/retry/coalescing counters, and WS `ws_connect_count`/`ws_reconnect_count`; verified live on `sinum-tablica-sbus-1` |

---

## Archived plans

- [V0.7.0_IMPLEMENTATION_PLAN.md](V0.7.0_IMPLEMENTATION_PLAN.md) — superseded by 0.8.x
- [POST_RELEASE_PLAN.md](POST_RELEASE_PLAN.md) — v0.6.0 post-release (historical)
