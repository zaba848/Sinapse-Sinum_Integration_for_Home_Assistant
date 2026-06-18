# Sinapse — Sinum Integration for Home Assistant

**Sinapse** connects a TECH Sterowniki Sinum EH-01 hub to Home Assistant over the local network.

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io)
[![Tests](https://img.shields.io/badge/tests-502%20passing-brightgreen.svg)](tests/)
[![Sinum API](https://img.shields.io/badge/Sinum%20API-1.4-informational)](https://www.techsterowniki.pl/baza-wiedzy-sinum)

Local-first integration: REST polling is the baseline, with an optional Lua/MQTT bridge for lower-latency real-time updates.

---

## Supported Entities

| Platform | Description | Status |
|---|---|---|
| `climate` | Virtual thermostats, SBUS/WTP fan coils, SBUS/WTP temperature regulators, heat pump manager | ✅ |
| `sensor` | Temperature, humidity, illuminance, CO₂, pressure, PM, IAQ, power, energy, voltage, current, weather, hub diagnostics, thermal schedule summaries, SBUS regulator target temp | ✅ |
| `binary_sensor` | Flood, motion, opening, smoke, two-state input, WTP fan coil valve state, parent device connectivity | ✅ |
| `switch` | Virtual relay integrators, wicket (electric strike), WTP/SBUS physical relays, valve_pump, common_valve | ✅ |
| `cover` | Virtual blind controller, gate, WTP blind controller | ✅ |
| `light` | Virtual dimmer/RGB, WTP/SBUS dimmer, WTP/SBUS RGB controller | ✅ |
| `event` | Button press event — fires per action, ideal for automations | ✅ |
| `button` | Sinum scenes and Lua code scripts | ✅ |
| `number` | Numeric Lua variables, SBUS analog output (0–10V) | ✅ |
| `update` | Parent device firmware tracker | ✅ |
| `alarm_control_panel` | Alarm system (if present) | ✅ |

### Supported Device Types

**Virtual devices**: `thermostat`, `relay_integrator`, `blind_controller_integrator`, `gate`, `wicket`, `dimmer_rgb_controller_integrator`, `dimmer_rgb_integrator`, `heat_pump_manager`

**WTP bus**: `temperature_sensor`, `humidity_sensor`, `pressure_sensor`, `light_sensor`, `co2_sensor`, `iaq_sensor`, `aq_sensor`, `motion_sensor`, `flood_sensor`, `opening_sensor`, `smoke_sensor`, `two_state_input_sensor`, `relay`, `dimmer`, `rgb_controller`, `blind_controller`, `energy_meter`, `fan_coil`, `fan_coil_v2`, `temperature_regulator`, `button`

**SBUS bus**: `temperature_sensor`, `humidity_sensor`, `light_sensor`, `motion_sensor`, `two_state_input_sensor`, `analog_input`, `analog_output`, `impulse_meter`, `relay`, `dimmer`, `rgb_controller`, `fan_coil`, `temperature_regulator`, `button`, `valve_pump`, `common_valve`, `pulse_width_modulation`

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

## Tested Hubs

Integration is continuously tested against two live hubs with different hardware configurations:

| Hub | Type | Firmware | Virtual | WTP | SBUS | HA entities |
|---|---|---|---|---|---|---|
| Hub 1 | sinum_plus | 1.24.0-alpha.2 | 28 | 254 | 8 | — |
| Hub 2 | sinum_lite | 1.24.0-alpha.2 | 169 | 35 | 436 | ~1 200 |

**Hub 2 entity breakdown** (active in HA, Phase 12):
- 137 climate (83 virtual thermostats + 51 SBUS regulators + 2 WTP regulators + 1 heat_pump_manager)
- ~503 sensor (+ 30 button last_action + 2 PWM)
- 287 binary_sensor
- 89 switch (69 SBUS relay + 11 WTP relay + 5 virtual + 2 valve_pump + 2 common_valve)
- 45 light (38 SBUS dimmer + 6 SBUS RGB + 1 virtual)
- 5 cover (3 virtual blind + 2 virtual gate)
- 3 number (SBUS analog_output)

**Note**: The hubs run alpha firmware. The `/api/v1/rooms` and bus list endpoints occasionally return HTTP 408 (bus timeout) — the integration handles this gracefully using cached data.

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
pytest tests/        # 502 tests, ~1.9s
pytest -v tests/     # verbose
pytest --cov=custom_components/sinum tests/  # with coverage (93%+)
```

### Structure

```
custom_components/sinum/
  ├── __init__.py
  ├── api.py               # REST client (SinumClient)
  ├── coordinator.py       # DataUpdateCoordinator
  ├── config_flow.py       # UI setup flow
  ├── climate.py           # Thermostats, fan coils, regulators, heat_pump_manager
  ├── sensor.py            # Temperature, humidity, IAQ, PM, power, schedules, buttons, PWM
  ├── binary_sensor.py     # Flood, motion, valve, connectivity
  ├── switch.py            # Relay integrators, wicket, WTP/SBUS relays, valve_pump, common_valve
  ├── cover.py             # Blind, gate (virtual + WTP)
  ├── light.py             # Dimmer/RGB (virtual + WTP/SBUS)
  ├── button.py            # Scenes
  ├── event.py             # Button press events (SinumButtonEvent)
  ├── number.py            # Lua variables + SBUS analog_output
  ├── update.py            # Firmware update tracker
  ├── alarm_control_panel.py
  ├── mqtt.py              # MQTT bridge transport
  ├── services.yaml        # send_notification service
  ├── strings.json         # UI strings (EN)
  └── translations/
      ├── en.json
      └── pl.json

lua_scripts/
  ├── mqtt_bridge.lua      # MQTT state bridge (v0.8.0)
  └── sinapse_api.lua      # Optional HTTP diagnostics endpoint

tests/
  ├── fixtures/sinum_devices.json
  ├── test_api.py
  ├── test_api_extended.py
  ├── test_alarm_control_panel.py
  ├── test_binary_sensor.py
  ├── test_binary_sensor_setup.py
  ├── test_button.py
  ├── test_climate.py
  ├── test_config_flow.py
  ├── test_coordinator.py
  ├── test_cover_extended.py
  ├── test_diagnostics.py
  ├── test_event.py
  ├── test_fan_coil.py
  ├── test_mqtt.py
  ├── test_new_device_types.py
  ├── test_new_entities.py
  ├── test_new_sbus_types.py
  ├── test_number_extended.py
  ├── test_schedule_sensors.py
  ├── test_sensor.py
  ├── test_switch_setup.py
  └── test_update.py
```

---

## Known Limitations

- `button` devices — exposed as `last_action` sensor (disabled by default); for real-time triggers use the **Event entity** with MQTT bridge
- `custom_device` virtual type — complex Lua contracts vary per installation, intentionally skipped
- Energy Center (`/api/v1/energy`) not available on all hubs — entities will not appear where missing
- LoRa, SLINK, video cameras not supported (require specific hardware modules)
- Hub alpha firmware may cause intermittent HTTP 408 on bus polling — handled gracefully

---

## License

**Source Available — Commercial Use Restricted**

© 2026 Tomasz Panek — All Rights Reserved.

Personal/non-commercial home automation: **allowed**.  
Business, organizational, or product deployment: **license required** — contact zaba9214@gmail.com.

See [LICENSE](LICENSE) for full terms.
