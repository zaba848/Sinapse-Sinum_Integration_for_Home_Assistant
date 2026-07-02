# Development Guide — Sinapse / Sinum Integration

**[← Back to README](../README.md)** · **[Polski](development.pl.md)**

---

## Contents

- [Project Structure](#project-structure)
- [Development Setup](#development-setup)
- [Running Tests](#running-tests)
- [Code Quality Gates](#code-quality-gates)
- [Key Internals](#key-internals)
- [Adding a New Sensor](#adding-a-new-sensor)
- [Adding a New Entity Platform](#adding-a-new-entity-platform)
- [Adding a New Virtual Device Type](#adding-a-new-virtual-device-type)
- [Writing Tests](#writing-tests)
- [Debugging on a Live Hub](#debugging-on-a-live-hub)
- [Contributing](#contributing)

---

## Project Structure

```
custom_components/sinum/
  ├── __init__.py              Entry point: setup, reload, unload, HA services
  ├── api.py                   REST client (SinumClient, error types)
  ├── coordinator.py           DataUpdateCoordinator — polls all buses in parallel
  ├── config_flow.py           UI setup + re-auth + options flow
  ├── const.py                 All constants: API paths, device types, defaults
  │
  ├── climate.py               Thermostats, fan coils, regulators, heat pump manager
  ├── sensor.py                Sensor platform entry point
  ├── sensor_bus.py            WTP / SBUS / LoRa sensor entity classes
  ├── sensor_bus_descriptions.py  SensorDescription data + WTP/SBUS/LoRa tuples
  ├── sensor_virtual.py        Virtual, weather, Energy Center, hub diagnostic sensors
  ├── sensor_schedule.py       Thermal schedule sensors
  ├── binary_sensor.py         Flood, motion, opening, valve state, connectivity
  ├── switch.py                Relays, wicket, valve_pump, common_valve
  ├── cover.py                 Blind controllers, gates
  ├── light.py                 Dimmers, RGB (virtual + WTP + SBUS)
  ├── button.py                Sinum scenes as HA button entities
  ├── event.py                 Physical button press events
  ├── number.py                Lua variables + SBUS analog output
  ├── camera.py                IP/ONVIF cameras via hub snapshot proxy
  ├── notify.py                send_notification → hub push notification
  ├── update.py                Parent device firmware tracker
  ├── alarm_control_panel.py   Alarm system
  ├── websocket.py             WebSocket real-time transport (SinumWebSocketBridge)
  ├── mqtt.py                  MQTT legacy bridge transport
  ├── diagnostics.py           HA diagnostics (redacts credentials)
  │
  ├── services.yaml            HA service schemas
  ├── strings.json             UI strings (EN)
  └── translations/
      ├── en.json
      └── pl.json

lua_scripts/
  ├── mqtt_bridge.lua          MQTT bridge Lua script v0.8.1 — upload to hub
  └── sinapse_api.lua          Optional HTTP diagnostics endpoint on hub

tests/
  ├── conftest.py              pytest fixtures (hass, make_response, etc.)
  ├── fixtures/
  │   └── sinum_devices.json   Sample hub API payloads used across tests
  ├── test_code_quality.py     CC gate — all functions must have CC ≤ 4
  ├── hardware_in_loop/        HIL scripts for live hub smoke testing
  └── test_*.py                1741 passing tests across all platforms and device types
```

---

## Development Setup

```bash
git clone https://github.com/zaba848/sinapse-sinum-integration-for-home-assistant
cd sinapse-sinum-integration-for-home-assistant
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
```

The integration uses Python 3.12+. All type annotations are required. No magic strings — add constants to `const.py`.

---

## Running Tests

```bash
# Full suite (~8 s)
pytest tests/

# Single file, verbose
pytest -v tests/test_api.py

# Coverage report
pytest --cov=custom_components/sinum tests/

# Cyclomatic complexity gate
pytest tests/test_code_quality.py -v
```

Test statistics: **1741 passing tests, 5 skipped live-write tests, 46 test files**, ~10 s runtime. All non-hardware tests must pass before merging.

Skip markers:
- live-write tests in `tests/test_api_endpoint_write.py` are skipped unless `SINUM_WRITE_TESTS=1` and live credentials are provided
- HIL scripts in `tests/hardware_in_loop/` are standalone Python scripts, not normal pytest test modules

---

## Code Quality Gates

All pull requests must pass:

| Gate | Tool | Requirement |
|---|---|---|
| Lint | `ruff check` | Zero errors |
| Format | `ruff format` | No diffs |
| Types | `mypy` | Zero errors |
| Cyclomatic complexity | `radon` via `tests/test_code_quality.py` | All functions CC ≤ 4 |
| Tests | `pytest` | All 1741 non-hardware tests pass |
| HACS | hacs-action | Valid `hacs.json` and manifest |

```bash
ruff check custom_components/        # lint
ruff format custom_components/       # auto-format
mypy custom_components/sinum/        # type check
pytest tests/test_code_quality.py    # CC gate
```

### CC ≤ 4 rule

Every function in `custom_components/sinum/` must have cyclomatic complexity ≤ 4. This is enforced by `tests/test_code_quality.py` (uses `radon`). The `_LEGACY_ALLOWANCE` dict is empty — there are no exemptions.

When adding code that would exceed CC 4, extract into focused helper functions at module level.

Things that add +1 to CC in radon:
- `if` / `elif` / `else`
- `for` / `while`
- `try` / `except`
- `and` / `or`
- ternary expression (`x if cond else y`)
- `any()` / `all()` with generator expressions
- List comprehensions with conditions

---

## Key Internals

### `SinumClient` (`api.py`)

Async HTTP client. One instance per coordinator entry.

- **Auth**: static `api_token` header, or JWT with `_refresh_jwt()` on 401
- **Retry**: one automatic retry on HTTP 408 (bus busy), after 1 s sleep
- **Error types**: `SinumConnectionError` (network/timeout/JSON), `SinumAuthError` (credentials), `SinumNotSupportedError` (404 — endpoint not on this hub)
- **`_read_json()`**: reads raw bytes, handles empty body, raises `SinumConnectionError` on non-JSON

### `SinumCoordinator` (`coordinator.py`)

Extends `DataUpdateCoordinator`. On each poll:

1. Fetches rooms (device ID lists + room metadata)
2. Fetches all bus device collections in parallel (`asyncio.gather`)
3. On bulk API failure: falls back to previous dict (entities stay alive)
4. On per-device failure: logs warning, keeps old value for that device
5. Injects room name, floor name, and parent hardware model into each device dict
6. Computes `removed_ids` (devices gone since last poll) for entity registry cleanup

### `SinumSensorDescription` (`sensor_bus_descriptions.py`)

Dataclass extending `SensorEntityDescription`. Extra fields:

| Field | Type | Purpose |
|---|---|---|
| `source` | `str` | Bus: `"wtp"`, `"sbus"`, `"lora"` |
| `api_key` | `str` | Key in the raw device dict |
| `scale` | `float` | Raw value multiplier (e.g. `0.1` for °C×10) |
| `zero_is_unavailable` | `bool` | Return `None` instead of `0.0` when raw value is zero |
| `wtp_type` / `sbus_type` / `lora_type` | `str` | Device type that provides this field |

### Entity availability

All Sinum entities extend `SinumDeviceAvailableMixin`:

```python
@property
def available(self) -> bool:
    return bool(self._device)
```

`self._device` returns the device dict from the coordinator (`coordinator.wtp_devices.get(id, {})`). An empty dict is falsy — entities go `unavailable` when the device is not in the latest coordinator data.

---

## Adding a New Sensor

### Sensor on an existing bus (WTP / SBUS / LoRa)

Add a `SinumSensorDescription` entry to the relevant tuple in `sensor_bus_descriptions.py`:

```python
# In WTP_SENSORS tuple
SinumSensorDescription(
    key="pm2_5",                           # unique key within this device type
    api_key="pm2_5",                       # field name in raw hub JSON
    source="wtp",
    wtp_type="air_quality_sensor",         # hub device type that has this field
    device_class=SensorDeviceClass.PM25,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement="µg/m³",
    scale=1.0,
    suggested_display_precision=0,
    # zero_is_unavailable=True,            # set if 0 means "no sensor attached"
),
```

No other changes needed — `sensor.py` imports the tuples and creates entities automatically.

### Sensor for a new device type

If the device type is new (not yet handled by any sensor description), add the type constant to `const.py` first:

```python
WTYPE_AIR_QUALITY = "air_quality_sensor"
```

Then add `SinumSensorDescription` entries as above, referencing the new type in `wtp_type`.

---

## Adding a New Entity Platform

1. Create `custom_components/sinum/myplatform.py`
2. Define an entity class extending the appropriate HA base:

```python
from homeassistant.components.switch import SwitchEntity
from .coordinator import SinumCoordinator

class MySinumEntity(SwitchEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: SinumCoordinator, device_id: int, entry_id: str) -> None:
        self._coordinator = coordinator
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_wtp_{device_id}_myplatform"

    @property
    def _device(self) -> dict:
        return self._coordinator.wtp_devices.get(self._device_id, {})

    @property
    def available(self) -> bool:
        return bool(self._device)

    @property
    def is_on(self) -> bool:
        return bool(self._device.get("state"))

    async def async_turn_on(self, **kwargs):
        await self._coordinator.client.patch_wtp_device(self._device_id, {"state": True})
        self._coordinator.wtp_devices[self._device_id]["state"] = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        await self._coordinator.client.patch_wtp_device(self._device_id, {"state": False})
        self._coordinator.wtp_devices[self._device_id]["state"] = False
        self.async_write_ha_state()
```

3. Add `async_setup_entry`:

```python
async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    entities = [
        MySinumEntity(coordinator, device_id, entry.entry_id)
        for device_id, device in coordinator.wtp_devices.items()
        if device.get("type") == "my_device_type"
    ]
    async_add_entities(entities)
```

4. Add the platform to `PLATFORMS` in `__init__.py`:

```python
from homeassistant.const import Platform

PLATFORMS: list[Platform] = [
    ...,
    Platform.SWITCH,   # already there — just add your new one
]
```

---

## Adding a New Virtual Device Type

Virtual devices live in `coordinator.virtual_devices`. Filter by `device.get("type")`:

```python
entities = [
    MyVirtualEntity(coordinator, device_id, entry.entry_id)
    for device_id, device in coordinator.virtual_devices.items()
    if device.get("type") == "my_virtual_type"
]
```

Write changes via `coordinator.client.patch_virtual_device(id, payload)`.

Add the type constant to `const.py`:

```python
VTYPE_MY_VIRTUAL_TYPE = "my_virtual_type"
```

---

## Writing Tests

All tests live in `tests/test_*.py`. Use the `make_response()` helper to mock hub HTTP responses:

```python
from unittest.mock import AsyncMock, MagicMock
import json

def make_response(status: int, data: object = None) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    _data = data if data is not None else {}
    resp.read = AsyncMock(return_value=json.dumps(_data).encode())
    return resp
```

Mock the coordinator for entity tests:

```python
def _make_coordinator(virtual=None, wtp=None, sbus=None):
    c = MagicMock()
    c.virtual_devices = virtual or {}
    c.wtp_devices = wtp or {}
    c.sbus_devices = sbus or {}
    c.client = MagicMock()
    c.client.patch_virtual_device = AsyncMock(return_value={})
    c.client.patch_wtp_device = AsyncMock(return_value={})
    return c
```

Test structure requirements:
- Every new device type: at minimum 3 tests (entity creation, state reading, write command)
- Every new platform: test `async_setup_entry`, entity properties, and write actions
- Every error path: test that `HomeAssistantError` is raised with a meaningful message

Add fixture data to `tests/fixtures/sinum_devices.json` for complex device payloads shared across tests.

---

## Hardware Testing Workflow

All releases must be validated on real hubs before deployment to production. The workflow uses 5 known production hubs with known inventory.

### Pre-Release (Local PC)

All local quality gates must pass before pushing to GitHub:

```bash
# Unit tests (no hardware needed)
python3 -m pytest -q

# Code quality (CC <= 4, ruff, mypy)
python3 -m pytest -q tests/test_code_quality.py
/opt/homebrew/bin/ruff check custom_components/
/opt/homebrew/bin/mypy custom_components/sinum/ --ignore-missing-imports --no-site-packages

# No credentials in commits
git diff --cached | grep -iE "password|token|secret" && echo "❌ FAIL" || echo "✓ PASS"
```

### Post-Release (5 Live Hubs)

#### Phase 1: Read-Only Smoke Test

No writes, no credentials needed. Tests that endpoints are reachable and payloads are parseable.

```bash
export SINUM_SMOKE_HUBS="WTP=http://<IP1>,SBUS=http://<IP2>,VIDEO=http://<IP3>,KLIMAK=http://<IP4>,SBUS2=http://<IP5>"
python3 scripts/hardware_smoke_check.py
```

**Expected output**:
```
[2026-07-01T12:00:00] WTP: 30 virtual, 254 WTP, 8 SBUS, 2 SLINK, 1 alarm ✓
[2026-07-01T12:00:05] SBUS: 171 virtual, 35 WTP, 436 SBUS, 1 Modbus, 3 alarms ✓
[2026-07-01T12:00:10] VIDEO: 6 virtual, 21 WTP, 77 SBUS, 1 Modbus, 6 video ✓
[2026-07-01T12:00:15] KLIMAK: 13 virtual, 41 WTP, 25 SBUS, 5 Modbus ✓
[2026-07-01T12:00:20] SBUS2: 29 virtual, 50 WTP, 191 SBUS, 2 SLINK, 3 Modbus, 16 alarms ✓

Smoke results: 5/5 hubs PASS
```

#### Phase 2: API Coverage & Device-Level Validation

Tests all endpoints for proper response codes, field presence, and type correctness. No writes.

```bash
export SINUM_SMOKE_HUBS="SBUS=http://<SBUS_IP>"
python3 tests/hardware_in_loop/hil_api_coverage.py --host <SBUS_IP> --token "$SINUM_API_TOKEN"
```

#### Phase 3: Safe Write Validation (Dimmers + Schedules)

Tests PATCH operations on non-destructive devices (dimmers, schedules, RTSP URLs). Writes are immediately rolled back.

```bash
export SINUM_SBUS_TOKEN="<api-token>"
python3 scripts/validate_api_writes.py
```

**Writes tested**:
- Dimmer brightness (set to 50%, verify, restore to 100%)
- Schedule active status (toggle, verify, restore)
- RTSP URL (if applicable)

#### Phase 4: Alarm-Specific Testing (Requires Explicit Approval)

**DESTRUCTIVE** — Do not run without explicit user approval and backups. Tests ARM_HOME, ARM_NIGHT, and zone bypass.

```bash
export SINUM_ALARM_TEST_PIN="<PIN>"    # Only set if alarm testing approved
python3 scripts/validate_api_writes.py --alarm-only
```

**Sequence**:
1. Disarm alarm (baseline)
2. Arm in HOME mode (verify zone_status)
3. Disarm (immediate cleanup)
4. Arm in NIGHT mode
5. Disarm
6. Verify alarm is in original state

#### Phase 5: WebSocket Event Validation (30s Passive Listen)

Captures any WS events flowing through the bridge. Does not require motion or button presses.

```bash
python3 tests/hardware_in_loop/hil_websocket.py --host <SBUS_IP> --token "$SINUM_API_TOKEN" --duration=30
```

**Expected capture** (if motion/events occur):
- `device_state_changed` events for updated devices
- `motion_detected` events if cameras see motion
- `button_pressed` events if buttons are pressed

### Post-Test Documentation

After all phases complete, update:

- `docs/hardware_smoke_latest.md` — Test dates, hub firmware versions, endpoint counts, PASS/FAIL status
- `docs/hardware_in_loop/live_write_validation_latest.md` — Write test results, safe devices, excluded operations
- `docs/ci_quality_dashboard.md` — Test count trend, CC violations (if any), ruff/mypy status

Example entry for `hardware_smoke_latest.md`:

```markdown
## 2026-07-01 (v0.7.2 Release Validation)

| Hub | Firmware | Entities | Status |
|---|---|---|---|
| tablica-wtp | 1.24.0-alpha.2 | 295 | ✅ PASS |
| sinum-tablica-sbus-1 | 1.24.0-alpha.4 | 646 | ✅ PASS |
| tablica-video-nowa | 1.24.0-alpha.4 | 105 | ✅ PASS |
| tablicaKlimak | 1.24.0-alpha.4 | 84 | ✅ PASS |
| sinum-tablica-sbus2 | 1.24.0-alpha.3 | 273 | ✅ PASS |

**Result**: 5/5 hubs PASS · No regressions
```

---

## Debugging on a Live Hub

Enable debug logging in HA `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.sinum: debug
```

Then use the read-only smoke runner (credentials via env, never committed):

```bash
export SINUM_SMOKE_HUBS="SBUS=http://10.0.62.167"
export SINUM_PASSWORD=your_password
python3 scripts/hardware_smoke_check.py
```

For deeper probes, run the standalone HIL scripts with a token:

```bash
python3 tests/hardware_in_loop/hil_smoke.py --host 10.0.62.167 --token "$SINUM_API_TOKEN"
python3 tests/hardware_in_loop/hil_api_coverage.py --host 10.0.62.167 --token "$SINUM_API_TOKEN"
python3 tests/hardware_in_loop/hil_websocket.py --host 10.0.62.167 --token "$SINUM_API_TOKEN"
```

Or use the diagnostic script to survey device fields on your hub:

```bash
python3 scripts/validate_v040_features.py
```

---

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for the full contribution guide.

Quick checklist before submitting a PR:

- [ ] `ruff check custom_components/` passes
- [ ] `ruff format custom_components/` produces no diffs
- [ ] `mypy custom_components/sinum/` passes
- [ ] `pytest tests/` — all 1741 non-hardware tests pass
- [ ] `pytest tests/test_code_quality.py` — CC gate clean (no `_LEGACY_ALLOWANCE` entries added)
- [ ] New device types have constants in `const.py`
- [ ] New functionality has at least 3 tests
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
