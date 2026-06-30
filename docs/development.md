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
  └── test_*.py                1675 passing tests across all platforms and device types
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

Test statistics: **1675 passing tests, 5 skipped live-write tests, 46 test files**, ~10 s runtime. All non-hardware tests must pass before merging.

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
| Tests | `pytest` | All 1675 non-hardware tests pass |
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
- [ ] `pytest tests/` — all 1675 non-hardware tests pass
- [ ] `pytest tests/test_code_quality.py` — CC gate clean (no `_LEGACY_ALLOWANCE` entries added)
- [ ] New device types have constants in `const.py`
- [ ] New functionality has at least 3 tests
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
