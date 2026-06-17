# Sinapse — Sinum Integration for Home Assistant

**Sinapse** connects a TECH Sterowniki Sinum EH-01 hub to Home Assistant over the local network.

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io)
[![Sinum API](https://img.shields.io/badge/Sinum%20API-1.4-informational)](https://www.techsterowniki.pl/baza-wiedzy-sinum)
[![License](https://img.shields.io/badge/License-Commercial-red.svg)](LICENSE)

The integration is local-first: REST polling is the baseline transport, with an optional Lua/MQTT bridge for lower-latency updates.

---

## Current Status

Verified on a real Sinum hub:

| Field | Value |
|---|---|
| Firmware | `1.24.0-alpha.1` |
| API | `1.4` |
| Lua manual | `v1.24.0`, rev. `2026-06-16` |
| Hub model | EH-01 / `sinum` |

The code now discovers devices from full class endpoints:

- `/api/v1/devices/virtual`
- `/api/v1/devices/wtp`
- `/api/v1/devices/sbus`

This matters because devices do not have to be assigned to rooms. `/api/v1/rooms` is used for area mapping and fallback discovery only.

---

## Supported Today

| Platform | Sinum sources | Status |
|---|---|---|
| `climate` | Virtual thermostats | ✅ |
| `sensor` | WTP temperature/humidity, WTP air/energy, SBUS temperature/humidity, weather, hub diagnostics | ✅ |
| `binary_sensor` | WTP/SBUS two-state sensors, parent device status | ✅ |
| `switch` | Virtual relay, wicket | ✅ |
| `cover` | Virtual blind, gate | ✅ |
| `light` | Virtual dimmer/RGB | ✅ |
| `button` | Sinum scenes/scripts | ✅ |
| `number` | Numeric Lua variables | ✅ |
| `update` | Parent device firmware | ✅ |

**Coming Soon (Planned Phases)**

| Feature | Phase | Status |
|---|---|---|
| Fan coil climate entities (WTP + SBUS) | 7A | 33% — SBUS done, WTP pending |
| Temperature regulator climate/sensors | 7B | Planned |
| Thermal schedule entities | 7C | Planned |
| MQTT bridge (v0.6) | 7D | ✅ Complete |
| Quality gate & testing | 7E | In progress |
| TECH RS ventilation sensors | 8 | Future |
| Modbus heat pump / DHW | 9 | Future |

**Not Supported**

- LoRa, SLINK, video cameras (require specific hardware)
- Energy Center (API endpoint not available on verified hub)
- Custom device types (complex Lua modules)

See [PLAN.md](PLAN.md) for detailed roadmap and verified device counts.

---

## Installation

### HACS

1. HACS -> Integrations -> three-dot menu -> **Custom repositories**
2. Add this repository as category **Integration**
3. Install **Sinapse**
4. Restart Home Assistant

### Manual

```bash
cd /config
cp -r /path/to/ha-sinapse/custom_components/sinum custom_components/
```

Restart Home Assistant.

---

## Configuration

Go to **Settings -> Devices & Services -> Add Integration -> Sinum (Sinapse)**.

Recommended authentication:

| Method | Notes |
|---|---|
| API token | Preferred. Static token created in Sinum app settings. |
| Username/password | Supported. Integration logs in and refreshes session JWT. |

The integration sends authorization as:

```text
Authorization: Bearer <token>
```

Do not commit API tokens, passwords, exported diagnostics with secrets, or local test credentials.

---

## Optional MQTT

MQTT is optional. REST polling works without it and is the supported baseline.

### Prerequisites

1. MQTT broker configured in Home Assistant (e.g., Mosquitto add-on)
2. Sinum hub network access to the MQTT broker
3. Manual upload of Lua bridge script to Sinum hub

### Setup Workflow

**Step 1: Configure MQTT in Sinum Hub**
1. Open Sinum hub web UI → Integrations → Add MQTT client
2. Enter your MQTT broker IP, port (usually 1883), username, password
3. **Note the MQTT Client ID assigned by Sinum** (shown after saving)
4. Save and verify connection

**Step 2: Upload Lua Bridge Script**
1. Open Sinum hub web UI → Settings → Lua Scripts
2. Create a new script or replace existing
3. Copy full contents of [`lua_scripts/mqtt_bridge.lua`](lua_scripts/mqtt_bridge.lua) 
4. **Important**: Set `CLIENT_ID = <the ID from Step 1>` at line 17
5. Save and Enable the script
6. Check Sinum logs for startup message: `[Sinapse] MQTT bridge v0.7 started`

**Step 3: Enable in Home Assistant**
1. Go to Sinum integration settings → Options
2. Toggle "Enable MQTT real-time transport"
3. Save

### MQTT Message Topics

| Topic | Direction | Payload |
|---|---|---|
| `sinum/state/{device_id}` | Sinum → HA | Complete device state JSON (see below) |
| `sinum/event/heartbeat` | Sinum → HA | Heartbeat pulse (every minute) |

### Example Payload

```json
{
  "id": 123,
  "type": "fan_coil",
  "name": "Salon Floor",
  "room_id": 5,
  "parent_id": 42,
  "state": true,
  "source": "wtp",
  "room_temperature": 195,
  "target_temperature": 220,
  "humidity": 450,
  "work_mode": "heating",
  "working_state": "heating_active",
  "updated_at": 1718545200
}
```

### Troubleshooting

| Issue | Solution |
|---|---|
| No messages in HA | Check MQTT broker connectivity, verify script logs on hub |
| Device updates slow | Check network latency, verify MQTT client online status |
| Script errors on hub | Check CLIENT_ID matches hub's configured value, verify JSON syntax |

**Note**: Command topics (`sinum/cmd/#`) are disabled until write payloads are verified. Use REST API for device control.

---

## Optional Lua HTTP Extension

[`lua_scripts/sinapse_api.lua`](lua_scripts/sinapse_api.lua) can expose extra hub diagnostics, especially Wi-Fi details not returned by regular REST `/api/v1/info` on every firmware build.

Expected endpoint:

```text
GET /api/v1/lua/http-server/sinapse/info
```

The integration treats this as best-effort. If the script is not installed, setup continues normally.

---

## Verified REST Endpoints

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/login` | Password login |
| `POST /api/v1/refresh` | Refresh JWT |
| `GET /api/v1/info` | Hub info |
| `GET /api/v1/rooms` | Rooms and room device references |
| `GET /api/v1/floors` | Floors for suggested areas |
| `GET /api/v1/parent-devices` | Bus/module health |
| `GET /api/v1/devices/virtual` | Virtual devices |
| `GET /api/v1/devices/wtp` | WTP devices |
| `GET /api/v1/devices/sbus` | SBUS devices |
| `GET/PATCH /api/v1/devices/virtual/{id}` | Virtual device read/write |
| `GET/PATCH /api/v1/devices/sbus/{id}` | SBUS device read/write |
| `GET /api/v1/scenes` | Scenes and Lua code scripts |
| `PATCH /api/v1/scenes/{id}` | Trigger scene/script with `{"trigger": true}` |
| `GET /api/v1/schedules` | Thermal schedules and temperature curves |
| `GET /api/v1/weather` | Weather payload |
| `GET /api/v1/devices/alarm-system` | Alarm panels, empty on verified hub |

`/api/v1/energy` returned `404` on the verified hub, so Energy Center support remains future work.

---

## Development

### Environment Setup

**Requirements**: Python 3.9+

```bash
# Clone or fork repository
cd sinapse
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# OR on Windows:
# venv\Scripts\activate

# Install dependencies
pip install -r requirements-dev.txt
```

### Running Tests

```bash
# Run all tests (51 tests, ~0.3s)
pytest tests/

# Run specific test file
pytest tests/test_api.py

# Run with verbose output
pytest -vv tests/

# Run with coverage
pytest --cov=custom_components/sinum tests/
```

**Expected output**: All 51 tests passing

### Code Quality Checks

```bash
# Type checking with mypy
python3 -m mypy custom_components/sinum/

# Linting with ruff
ruff check custom_components/sinum/

# Syntax verification
python3 -m compileall custom_components/sinum tests

# All checks (use this before committing)
ruff check custom_components/sinum/ && \
python3 -m mypy custom_components/sinum/ && \
pytest tests/ && \
python3 -m compileall custom_components/sinum tests
```

### Project Structure

```
custom_components/sinum/
  ├── __init__.py           # Integration entry point
  ├── api.py                # REST API client (334 LOC)
  ├── climate.py            # Climate entities (fan coil, thermostat)
  ├── coordinator.py        # DataUpdateCoordinator (device discovery)
  ├── config_flow.py        # Configuration UI
  ├── sensor.py             # Sensor entities (763 LOC)
  ├── binary_sensor.py      # Binary sensor entities
  ├── switch.py, cover.py, light.py, button.py, number.py, update.py
  ├── strings.json          # UI strings (EN)
  └── translations/pl.json  # Polish translations

lua_scripts/
  ├── mqtt_bridge.lua       # MQTT state bridge (v0.7.1)
  └── sinapse_api.lua       # HTTP server diagnostics

tests/
  ├── conftest.py           # Pytest fixtures
  ├── fixtures/             # Test data
  ├── test_api.py           # API client tests
  ├── test_config_flow.py   # Config flow tests
  ├── test_climate.py       # Climate entity tests
  ├── test_coordinator.py   # Coordinator tests
  └── test_fan_coil.py      # Fan coil tests (22 tests)
```

### Adding a New Entity Type

1. Create new file `custom_components/sinum/new_platform.py`
2. Inherit from appropriate Home Assistant entity base class
3. Implement required properties and methods
4. Register in `__init__.py` (entry point)
5. Add tests in `tests/test_new_platform.py`
6. Add translation keys to `strings.json` and `translations/pl.json`

See [PLAN.md](PLAN.md) for upcoming entity work (fan coil, regulators, schedules).

---

## Roadmap

See [PLAN.md](PLAN.md) for detailed timeline and device counts.

### Current Phase: 7E — Quality Gate

- ✅ Fix JSON translation bugs
- ✅ Create pyproject.toml with ruff/mypy config
- ✅ Add test fixtures for SBUS sensors
- ⏳ Add Phase 7E tests (collection discovery, SBUS sensors, scene trigger, Energy 404, alarm empty)
- ⏳ Run mypy type checking
- ⏳ Run ruff linting
- ⏳ Verify HA custom integration checks

### Completed Phases

| Phase | Feature | Status |
|---|---|---|
| 7D | MQTT Bridge Hardening | ✅ v0.7.1 complete |
| Previous | Device discovery, sensors, binary sensors, switches, covers, lights, buttons, numbers, updates | ✅ |

### Planned Phases

| Phase | Feature | ETA |
|---|---|---|
| 7A | Fan coil climate entities (WTP + SBUS) | Next |
| 7B | Temperature regulator support | Q3 |
| 7C | Thermal schedule entities | Q3 |
| 8 | TECH RS ventilation/heat pump | Q3/Q4 |
| 9 | Modbus DHW / energy integration | Q4 |
| 10 | Energy Center (if endpoint available) | Future |
| 11 | LoRa / SLINK / cameras | When hardware present |
| 12 | Long-term statistics | Future |

---

## License

**Source Available — Commercial Use Restricted**

© 2026 Tomasz Panek — All Rights Reserved.

| Use case | Allowed |
|---|---|
| Personal home automation, non-commercial | Yes |
| Business / organization deployment | License required |
| Integration into a paid product or service | License required |
| Resale or redistribution | License required |

Commercial license: **zaba9214@gmail.com**  
See [LICENSE](LICENSE) for full terms.
