# Performance Report — v0.8.1

Generated: 2026-07-13 04:52 UTC

## Method

Coordinator cycle timing measured directly against the largest live hub
(`sinum-tablica-sbus-1` — 169 virtual, 35 WTP, 436 SBUS, 60 rooms, 38 scenes),
by timing the exact HTTP endpoints `coordinator.py::_fetch_all` calls, grouped
into the same two `asyncio.gather` rounds the code actually uses:

- **Phase 1 (metadata)**: `/info`, `/rooms`, `/floors`, `/parent-devices`, `/scenes`, `/schedules`, `/automations`, `/variables`
- **Phase 2 (device stores)**: `/devices/virtual`, `/devices/wtp`, `/devices/sbus`, `/devices/lora`, `/devices/alarm`, `/devices/modbus`, `/devices/video`, `/devices/slink`

Measured from a workstation on the same LAN as the hub (comparable network
position to the RPi running Home Assistant).

## Results

| Endpoint | Latency | Payload |
|---|---:|---:|
| `/devices/virtual` | 1526 ms | 709 KB |
| `/devices/sbus` | 1252 ms | 362 KB |
| `/parent-devices` | 1090 ms | 273 KB |
| `/rooms` | 206 ms | 29 KB |
| `/devices/wtp` | 198 ms | 21 KB |
| `/scenes` | 59 ms | 10 KB |
| `/info` | 137 ms | <1 KB |
| all other endpoints | <60 ms each | <5 KB each |

| Metric | Value |
|---|---:|
| Phase 1 wall time (parallel) | 1090 ms |
| Phase 2 wall time (parallel) | 1526 ms |
| **Total coordinator cycle (2 sequential phases)** | **~2616 ms** |
| Total payload per cycle | 1.38 MB |
| Default `scan_interval` | 30 s |
| Cycle duration as % of interval | 8.7% |

## Code health (for context, not a bottleneck)

- 11,919 LOC across `custom_components/sinum/`
- Average cyclomatic complexity: **2.27 (grade A)** — no complexity hotspots; worst maintainability-index files (`_light_helpers.py`, `climate_heat_pump.py`, `config_flow.py`, `coordinator.py`) are still grade A
- Full test suite: 1953 tests in ~12s

**Conclusion: this is not a code-complexity problem, it's an I/O-shape problem.** The two heaviest endpoints (`/devices/virtual`, `/devices/sbus`) alone account for ~80% of both cycle latency and payload size, and `/parent-devices` — data that essentially never changes at runtime (hardware topology) — costs 1.09s and 273 KB on *every single 30-second poll*.

## Findings and proposed optimizations (not yet implemented — see below)

### 1. Merge the two `asyncio.gather` phases into one (~42% cycle latency cut)

`_fetch_all()` currently runs `_fetch_metadata()` and `_fetch_device_stores()`
as two *sequential* `asyncio.gather` rounds even though the device-store bulk
HTTP calls (`list_getter()`) don't actually need `rooms`/`bus_ids` until the
*response processing* step (`_process_bulk_devices`), not to fire the request.
Only the rare fallback path (per-device fetch on old firmware without a bulk
endpoint — not hit by any of the 6 current hubs) genuinely needs `rooms` before
it can start.

Firing both rounds concurrently instead of sequentially would cut the cycle
from `phase1 + phase2` (2616 ms) to `max(phase1, phase2)` (~1526 ms) — a
**~42% reduction** in coordinator update latency, with zero change to what
data is fetched.

**Risk**: `coordinator.py` is the highest-blast-radius file in the
integration — every entity depends on its output. This needs a restructure
of `_fetch_all`/`_fetch_device_stores` (not just a config flag), validated
against the full test suite including the real-HA `test_full_platform_setup.py`
harness. Recommend implementing behind careful review rather than shipping
silently.

### 2. Tiered refresh: poll quasi-static metadata less often than device state

`rooms`, `floors`, `parent-devices`, `scenes`, `schedules`, `automations`,
`variables` describe *configuration* (hardware topology, room layout, scene
definitions) that changes on the order of "when the user edits their hub
setup" — not every 30 seconds. `/parent-devices` alone is 1.09s / 273 KB of
the 2.6s cycle for data that is realistically static between hub-config edits.

Fetching this tier every Nth cycle (e.g. every 10th → ~5 min at the default
30s interval) instead of every cycle would remove ~1.09s and ~314 KB from
~90% of polls, while device *state* (the actual reason for 30s polling —
temperatures, switch states, positions) stays on the fast path untouched.

**Trade-off**: room/scene/schedule renames or hub-config edits would take up
to ~5 minutes (configurable) to reflect in HA instead of 30s. This is a
user-visible behavior change, not a pure refactor — needs a decision on
acceptable staleness before implementing.

### 3. Not actionable from our side

`/devices/virtual` (709 KB) and `/devices/sbus` (362 KB) payload sizes are
set by the hub's API response shape (verbose per-device fields), not by
integration code. No local optimization changes this; would require a
leaner hub-side API (out of scope).

## Current headroom

At 8.7% of the poll interval, the coordinator is **not** currently at risk of
overlapping updates or starving the event loop on the largest hub — these are
optimizations for headroom/responsiveness, not fixes for an active problem.
