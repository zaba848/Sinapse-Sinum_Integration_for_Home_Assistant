# Changelog

All notable changes to the Sinum (Sinapse) Home Assistant integration are documented here.

## [Unreleased]

### Changed
- CI quality gates strengthened: single-pass coverage report generation with `coverage.xml` and pip cache in `ci.yml`.
- `tests.yml` now runs **Functional Smoke Tests** (critical behavior paths) instead of duplicating the full suite.
- Hardware validation process formalized in `HARDWARE_TEST_PLAN.md` with a release checklist and explicit CC + smoke + manual hardware gate.
- `validate.yml` no longer skips HACS validation on push/PR due to repository visibility checks.
- Added a documented hardware smoke test result (2026-06-24) for WTP and SBUS hubs.
- `SECURITY.md` replaced template content with an actionable vulnerability handling policy for current release lines.
- `codeql.yml` now always executes CodeQL in public-repo mode (no soft skip fallback).

### Added
- New `dependency-review.yml` workflow for pull requests to detect risky dependency changes.
- Translation consistency tests (`test_translations_consistency.py`) to keep config/options/entity UI labels synchronized across `strings.json`, `en.json`, and `pl.json`.
- Additional functional tests for WTP-specific sensor types (`co2_sensor`, `pressure_sensor`, `iaq_sensor`, `aq_sensor`) and WTP `fan_coil_v2` climate setup path.

## [0.2.6] — 2026-06-24

### Changed
- **Repository rebranding**: canonical repository path updated to
  `zaba848/sinapse-sinum-integration-for-home-assistant`.
- **Project metadata**: integration manifest and Python project metadata version bumped to `0.2.6`.
- **Documentation links**: README installation and clone instructions now point to the new repository URL.
- **Contributor docs**: issue tracker links in `CONTRIBUTING.md` updated to the renamed repository.

## [0.2.5] — 2026-06-24

### Changed
- **`sensor_bus.py` split**: sensor descriptions (pure data) extracted to
  `sensor_bus_descriptions.py`; `sensor_bus.py` now contains only entity classes.
  Backward-compatible re-export keeps all existing imports unchanged.
- **`cover.py` RestoreEntity guard**: position/tilt properties now use `if self._device:`
  pattern (same as `light.py`) — when hub is online, live coordinator data is always
  authoritative and never falls back to stale restored values.
- **`SinumDeviceAvailableMixin`**: added `_device` property stub so mypy
  understands the contract; removed now-redundant `# type: ignore` comments.
- **`diagnostics.py`**: LoRa devices (`lora_devices`, `lora_count`) included in output.
- **Translations**: `reconfigure` step and `reconfigure_successful` abort synced to
  `en.json` and `pl.json` (were only in `strings.json`).

### Added
- **Device trigger tests** (`tests/test_device_trigger.py`): 16 tests covering all
  `async_get_triggers`, `async_attach_trigger`, and `async_validate_trigger_config` paths.
- **`mypy` clean**: all 24 source files pass `mypy --ignore-missing-imports` with 0 errors.

---

## [0.2.4] — 2026-06-24

### Added
- **`SinumDeviceAvailableMixin`** — all 28 entity classes now report `unavailable` immediately when
  the hub is offline or the device is missing from the coordinator snapshot.
- **`async_step_reconfigure`** in config flow — change hub IP or credentials without removing
  the integration; all entities and automations are preserved.
- **`async_migrate_entry`** — automatic data migration for older config entries (backfills
  `auth_mode` key missing from pre-0.2 entries).
- **`RestoreEntity`** for all cover and light classes — last-known position, tilt, brightness,
  and color survive a Home Assistant restart without waiting for the next hub poll.
- **`device_trigger.py`** — Sinum buttons appear as native device triggers in the HA automation
  editor ("A button was pressed").
- **`quality_scale: silver`** in `manifest.json`.
- GitHub issue templates (bug report, feature request), Dependabot weekly updates, CodeQL workflow.
- Config flow tests for reconfigure flow and `async_migrate_entry` (1020 tests total).
- LoRa devices included in `diagnostics.py` output (`lora_devices`, `lora_count`).
- `reconfigure` step translations in `en.json` and `pl.json`.

### Fixed
- `translations/en.json` and `pl.json` were missing `reconfigure` step and
  `reconfigure_successful` abort reason — now in sync with `strings.json`.

---

## [0.2.3] — 2026-06-22

### Fixed
- **SBUS button polling**: SBUS hub resets `action` field to `""` immediately after press —
  by the time the coordinator polls, the action type is gone. Press is now always detected via
  `buttons_count` increment. Event fires with `action=None` when action has already been reset;
  for real-time action type use the MQTT bridge.
- **hacs.json**: removed `"homeassistant"` key that caused HACS validation failure

### Added
- Brand assets (`custom_components/sinum/brand/icon.png`, `icon@2x.png`) for HACS v2 listing
- HACS GitHub Actions validation workflow (`.github/workflows/validate.yml`)

---

## [0.2.2] — 2026-06-23

### Fixed
- **Button event: consecutive same-type presses no longer missed** — `SinumButtonEvent` now also
  tracks `buttons_count` (hub-side cumulative counter). If `action` stays at e.g. `"single"` but
  the count increments, the event fires again. Previously a second single-press would be silently
  dropped if the hub didn't reset the `action` field between presses.

### Changed
- **Event entity payload** now includes `buttons_count` alongside `action`
- **README**: new "Event — Physical Buttons" section with action values, automation YAML examples,
  step-by-step MQTT setup guide for instant button response (< 1 s), comparison table

### Added
- 3 new tests for `buttons_count`-based event detection (990 total)

---

## [0.2.1] — 2026-06-23

### Fixed
- **API: robust JSON parsing** — new `_read_json()` helper replaces direct `resp.json()` calls;
  handles empty response body, non-JSON / HTML error pages, and body-read failures
  (`ClientPayloadError`) by raising `SinumConnectionError` with a clear message instead of crashing
- **Token refresh**: `_refresh_jwt()` returns `False` instead of raising when the refresh
  endpoint returns non-JSON, preventing an unhandled exception in the auth retry path
- **`content_length` guard** was unreliable when hub omits the `Content-Length` header;
  replaced with raw-byte read + empty check
- **`light.py` ruff E402**: `_LOGGER` moved after all imports

### Changed
- **Button backlights** (`button` RGB backlight channel) moved to `EntityCategory.CONFIG` —
  visible only in the device configuration page, not on the main dashboard
- **Temperature sensors returning 0.0 °C**: virtual thermostats and SBUS sensors without a
  physical probe now report `unknown` instead of `0.0` via `zero_is_unavailable` flag
- **RGB Controller — SBUS**: full color control via persistent Lua scenes (`_ha_rgb_sbus_{id}`);
  REST PATCH replaced for color and brightness to avoid hub read-only field errors
- **Tests expanded**: 880 → 987 tests; 5 new `TestReadJsonErrorHandling` tests added
- **README** rewritten with architecture diagram, entity reference, dev guide,
  Lua integration examples, and "Adding New Device Types" walkthrough

---

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
