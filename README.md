# Sinapse — Sinum Integration for Home Assistant

**Sinapse** connects a TECH Sterowniki Sinum EH-01 hub to Home Assistant over the local network.

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io)
[![Tests](https://img.shields.io/badge/tests-98%20passing-brightgreen.svg)](tests/)
[![Sinum API](https://img.shields.io/badge/Sinum%20API-1.4-informational)](https://www.techsterowniki.pl/baza-wiedzy-sinum)

Local-first integration: REST polling is the baseline, with an optional Lua/MQTT bridge for lower-latency real-time updates.

---

## Supported Entities

| Platform | Description | Status |
|---|---|---|
| `climate` | Virtual thermostats, SBUS/WTP fan coils, temperature regulators (optional) | ✅ |
| `sensor` | WTP/SBUS temperature & humidity, weather, energy, hub diagnostics, thermal schedule summaries | ✅ |
| `binary_sensor` | WTP/SBUS flood/motion/opening/smoke sensors, WTP fan coil valve state, parent device connectivity | ✅ |
| `switch` | Virtual relay integrators, wicket (electric strike) | ✅ |
| `cover` | Virtual blind controller, gate | ✅ |
| `light` | Virtual dimmer/RGB controller | ✅ |
| `button` | Sinum scenes and Lua code scripts | ✅ |
| `number` | Numeric Lua variables | ✅ |
| `update` | Parent device firmware tracker | ✅ |
| `alarm_control_panel` | Alarm system (if present) | ✅ |

### Supported Device Types

**Virtual devices**: thermostat, relay_integrator, blind_controller_integrator, gate, wicket, dimmer_rgb_controller_integrator

**WTP bus**: temperature_sensor, humidity_sensor, temperature_regulator, fan_coil, fan_coil_v2, flood_sensor, motion_sensor, opening_sensor, smoke_sensor, two_state_input_sensor

**SBUS bus**: temperature_sensor, humidity_sensor, two_state_input_sensor, fan_coil

---

## Installation

### HACS (recommended)

1. HACS → Integrations → three-dot menu → **Custom repositories**
2. Add `https://github.com/zaba848/Sinum_HomeAsistant_connector` as category **Integration**
3. Find and install **Sinapse**
4. Restart Home Assistant

### Manual

```bash
cp -r custom_components/sinum /config/custom_components/
```

Restart Home Assistant.

---

## Configuration

**Settings → Devices & Services → Add Integration → Sinum (Sinapse)**

| Auth method | Notes |
|---|---|
| API Token (recommended) | Static token from Sinum app → Settings → Integrations → API Tokens |
| Username + password | Standard login; integration manages JWT refresh automatically |

The polling interval defaults to 30 seconds and can be changed in integration options.

---

## Optional MQTT Real-Time Updates

MQTT is optional — REST polling is fully supported without it.

### Prerequisites

- MQTT broker configured in Home Assistant (e.g. Mosquitto add-on)
- Sinum hub can reach the MQTT broker on the local network

### Setup

**1. Add MQTT client on hub**

Open Sinum hub web UI → Integrations → Add MQTT client. Note the assigned **Client ID**.

**2. Upload Lua bridge script**

Sinum hub web UI → Settings → Lua Scripts → New script.  
Paste contents of [`lua_scripts/mqtt_bridge.lua`](lua_scripts/mqtt_bridge.lua).  
Set `CLIENT_ID = <id from step 1>` at line 17, save and enable.

Verify by checking hub logs for `[Sinapse] Published:` entries.

**3. Enable in HA**

Sinum integration → Options → Enable MQTT real-time transport → Save.

### MQTT Topics

| Topic | Direction | Content |
|---|---|---|
| `sinum/state/{device_id}` | Hub → HA | Full device state JSON |
| `sinum/event/heartbeat` | Hub → HA | Heartbeat every minute |

---

## Verified Hub

| Field | Value |
|---|---|
| Model | EH-01 |
| Firmware | `1.24.0-alpha.3` |
| API version | `1.4` |
| Virtual devices | 12 (9 thermostats, 3 custom) |
| WTP devices | 34 (8 regulators, 8 temp sensors, 8 humidity sensors, 7 fan coils, 1 fan_coil_v2, 2 two-state inputs) |
| SBUS devices | 10 (2 temp, 2 humidity, 4 two-state inputs, 2 fan coils) |
| Parent devices | 23 (WTP, SBUS, TECH, Modbus, system modules) |
| Predicted HA entities | ~153 (12 climate, 54 sensor, 59 binary, 5 button, 23 update) |

**Note**: The hub runs alpha firmware. The `/api/v1/rooms` and bus list endpoints occasionally return HTTP 408 (bus timeout) — the integration handles this gracefully using cached data.

---

## Development

### Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
```

### Tests

```bash
pytest tests/        # 98 tests, ~0.5s
pytest -v tests/     # verbose
pytest --cov=custom_components/sinum tests/  # with coverage
```

### Structure

```
custom_components/sinum/
  ├── __init__.py
  ├── api.py               # REST client (SinumClient)
  ├── coordinator.py       # DataUpdateCoordinator
  ├── config_flow.py       # UI setup flow
  ├── climate.py           # Thermostats, fan coils, regulators
  ├── sensor.py            # Temperature, humidity, hub diagnostics, schedules
  ├── binary_sensor.py     # Flood, motion, valve, connectivity
  ├── switch.py            # Relay, wicket
  ├── cover.py             # Blind, gate
  ├── light.py             # Dimmer/RGB
  ├── button.py            # Scenes
  ├── number.py            # Lua variables
  ├── update.py            # Firmware update tracker
  ├── alarm_control_panel.py
  ├── mqtt.py              # MQTT bridge transport
  ├── strings.json         # UI strings (EN)
  └── translations/
      ├── en.json
      └── pl.json

lua_scripts/
  ├── mqtt_bridge.lua      # MQTT state bridge (v0.7.2)
  └── sinapse_api.lua      # Optional HTTP diagnostics endpoint

tests/
  ├── fixtures/sinum_devices.json
  ├── test_api.py
  ├── test_binary_sensor.py
  ├── test_button.py
  ├── test_climate.py
  ├── test_config_flow.py
  ├── test_coordinator.py
  ├── test_fan_coil.py
  ├── test_mqtt.py
  ├── test_schedule_sensors.py
  └── test_sensor.py
```

---

## Known Limitations

- Energy Center (`/api/v1/energy`) not available on verified hub — entities will not appear
- LoRa, SLINK, video cameras not supported (require specific hardware modules)
- Custom `custom_device` virtual types not mapped (complex Lua contracts vary per installation)
- Hub alpha firmware may cause intermittent HTTP 408 on bus polling — handled gracefully

---

## License

**Source Available — Commercial Use Restricted**

© 2026 Tomasz Panek — All Rights Reserved.

Personal/non-commercial home automation: **allowed**.  
Business, organizational, or product deployment: **license required** — contact zaba9214@gmail.com.

See [LICENSE](LICENSE) for full terms.
