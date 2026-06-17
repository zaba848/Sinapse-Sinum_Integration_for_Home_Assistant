# Changelog

All notable changes to the Sinum (Sinapse) Home Assistant integration are documented here.

## [0.2.0] — 2026-06-17

### Added
- **Event entity** for button devices (`button_press`) — real-time automations without polling state
- New SBUS and virtual device types: `button`, `valve_pump`, `common_valve`, `analog_output`, `pulse_width_modulation`, `heat_pump_manager`
- Thermal schedule sensors: target/fallback temperature, active period, association count
- `SinumHeatPumpManagerClimate` — heat pump manager climate entity with heating/cooling/auto modes
- Hub connectivity binary sensors and firmware update entities for parent devices
- Coordinator bulk-fetch fallback: preserves cached device data during hub outages
- MQTT bridge v0.8.0: full device coverage for all supported types

### Changed
- Button `last_action` sensor is now disabled by default (use the new event entity for automations)
- MQTT bridge `OPTIONAL_FIELDS` expanded to cover all new device types
- Improved defensive coding in cover, switch, light, sensor entities

### Fixed
- Coordinator flood-log: 400+ WARNINGs on hub outage reduced to single DEBUG message
- Unused imports removed from `climate.py`, `light.py`, `cover.py`

---

## [0.1.0] — 2026-05-01

### Added
- Initial release supporting Sinum EH-01 hub (firmware 1.24.0-alpha)
- Local REST polling integration (configurable interval, default 30 s)
- Optional MQTT real-time transport via Lua bridge script
- Supported platforms: `climate`, `sensor`, `binary_sensor`, `switch`, `cover`, `light`, `button`, `number`, `update`, `alarm_control_panel`
- Two authentication modes: API token (recommended) and username + password (JWT with auto-refresh)
- Multi-language support: English (EN) and Polish (PL)
- HACS custom repository support
- Tested on two live hubs (firmware 1.24.0-alpha.3)
