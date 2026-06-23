# Sinum API Coverage

Snapshot source: saved Swagger UI export from `https://apidocs.sinum.tech/`, rendered as Sinum Local API `1.22.0`. The rendered documentation exposed 420 operations. This integration intentionally covers the local-control surface that maps cleanly to Home Assistant and keeps administrative or destructive endpoints out of HA entities.

## Covered As Entities

| API area | Coverage |
|---|---|
| `/devices/virtual` | Thermostats, relays, blinds, gates, wickets, dimmer/RGB, heat pump manager, thermostat output group diagnostics |
| `/devices/wtp` | Sensors, relays, dimmers, RGB, blinds, fan coils, regulators, buttons, firmware status |
| `/devices/sbus` | Sensors, relays, dimmers, RGB, fan coils, regulators, analog input/output, impulse meters, buttons, valves, PWM |
| `/devices/lora` | Sensors, relay switches, read/patch client support |
| `/devices/alarm-system` | Alarm zones and commands |
| `/scenes` | Scene buttons and activation |
| `/variables` | Numeric Lua environment variables |
| `/schedules` | Thermal schedule sensors plus explicit `sinum.update_schedule` service |
| `/weather` | Weather sensors where supported by the hub |
| `/energy` | Legacy Energy Center aggregate sensors where supported |
| `/energy-center/*` | Diagnostic status sensor for endpoint availability |

## Covered As Read-Only API Helpers

These endpoints are available in `SinumClient` for diagnostics, tests, and future HA features, but are not directly exposed as writable entities:

- Scene details, Lua code, Lua extensions, schema, and logs: `/scenes/{id}/*`
- Automations list, details, Lua code, Lua extensions, schema, and logs: `/automations/*`
- Energy Center associations, flow monitor, prices, price settings/sources, storage, consumption, and production: `/energy-center/*`
- Single schedule fetch and partial schedule patch: `/schedules/{id}`

## Intentionally Out Of Scope

The Swagger export also documents administrative endpoints that are intentionally not exposed by the integration:

- Users, permissions, dashboards, UI directories, and cloud login
- Backup/restore, system update, reboot, shutdown, network, and security settings
- Video stream/media endpoints
- Generic custom-device Lua contracts as automatic HA entities
- Energy Center clear-data and other destructive maintenance operations

Those APIs can change hub state broadly or expose installation-specific contracts. They should stay behind explicit tools or diagnostics, not automatic Home Assistant entity mapping.
