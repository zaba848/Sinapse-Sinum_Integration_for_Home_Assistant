# Changelog

All notable changes to the Sinum (Sinapse) Home Assistant integration are documented here.

---
## Upgrading

### Before You Update
1. **Backup your Home Assistant configuration**: `config/custom_components/sinum/` directory.
2. **Check for breaking changes**: Review the release notes below for your version.
3. **Test in staging first**: If you have a development HA instance, test there first.

### After You Update
1. **Reload the integration**: Go to **Settings** -> **Devices & Services** -> **Sinum** -> **Reload**.
2. **Verify entities**: Check that all entities are still available in **Settings** -> **Devices & Services** -> **Sinum**.
3. **Check automations**: If you use Sinum buttons/events in automations, verify they still trigger correctly.

### Reporting Issues
- Use [GitHub Issues](https://github.com/zaba848/sinapse-sinum-integration-for-home-assistant/issues) for bugs.
- For security vulnerabilities, see [SECURITY.md](SECURITY.md).

---

## [Unreleased]

## [0.5.9] — 2026-06-29

### New Features
- **Camera support**: IP cameras and ONVIF cameras configured in the Sinum hub are now exposed as HA `camera` entities.
  - Snapshots fetched via hub proxy endpoint (`/api/v1/devices/video/{id}/snapshot`).
  - Live streaming (`CameraEntityFeature.STREAM`) enabled for `ip_camera` and `onvif_camera` types — HA proxies RTSP via its internal stream engine; the URL is never sent to the browser.
  - `stream_source()` calls the individual device endpoint to obtain unmasked credentials (the list endpoint masks passwords as `*******`); returns `None` when hub still masks credentials, HA falls back to snapshot-only mode.
  - Camera attributes exposed: `video_type`, `ip`, `port`, `url_path`, `mac`, `status`, `purpose`, `room_id` (passwords and login credentials never exposed in entity state).
  - Brand populated from hub `variant` field (e.g. `hikvision`); `generic` variants return `None`.
  - Availability follows coordinator `last_update_success` (standard `CoordinatorEntity` pattern).
- **Total: 1 516 tests** across 45 files

## [0.5.8] — 2026-06-29

### Bug Fixes
- **WTP temperature regulator sensor: 0.0°C → unavailable**: regulators without a physical sensor previously showed `0.0°C`; now correctly report "Unavailable" when the hub sends `temperature: 0`. Achieved by setting `zero_is_unavailable=True` on the `wtp_regulator` temperature sensor description.

### Code Quality
- **mypy clean**: fixed `light._is_button_with_color` signature — `dev_type: str` widened to `str | None` (was flagged by mypy as incompatible with `device.get("type")` return type).
- **Total: 1 499 tests** across 44 files

## [0.5.7] — 2026-06-26

### Documentation
- **PL docs complete**: added `docs/installation.pl.md`, `docs/entities.pl.md`, `docs/real-time.pl.md`, `docs/development.pl.md` — full Polish translations of all 4 docs files; README.pl.md now links to `.pl.md` versions
- **EN↔PL language switchers**: all 4 EN docs now include `· Polski` links; all PL docs link back to EN
- **Official Sinum resources section**: added to both READMEs with links to `apidocs.sinum.tech`, Lua scripting manual PDF, Sinum FAQ, knowledge base, and Google Home integration guide
- **Translations `upload_mqtt_bridge`**: service added to both `translations/en.json` and `translations/pl.json` (was missing)

### Code Quality
- **Ruff lint clean**: 32 ruff errors fixed (22 auto-fixed + 10 manual): import sorting, unused imports, `SIM117`/`SIM105`/`SIM102` simplifications, F821 forward refs removed, HIL `C901` suppressed

## [0.5.6] — 2026-06-26

### Quality — Code & Tests
- **websocket.py 100% coverage**: +10 tests covering `_run`, `_wait_reconnect`, `_consume_loop`, `_receive_messages`, and edge cases (`_handle_event` non-dict data, `_apply_device_state` non-dict payload)
- **`ConfigEntryAuthFailed` on auth errors**: `_safe_fetch` now re-raises `SinumAuthError` (was silently swallowed); `_async_update_data` wraps the fetch in a try/except and converts it to `ConfigEntryAuthFailed` — HA automatically shows a "Re-authenticate" persistent notification
- **Device registry cleanup**: `_cleanup_stale_entities` now also removes device cards from the device registry (not just entity registry entries) when a hub device disappears
- **Total: 1 498 tests** across 44 files

### Bug Fixes
- **README.pl.md**: fixed 4 broken links pointing to non-existent `docs/*.pl.md` files (now point to EN docs)

## [0.5.5] — 2026-06-26

### Quality — Code & Tests
- **CC zero-legacy**: all 19 previously exempted functions refactored to CC ≤ 4. `_LEGACY_ALLOWANCE = {}` — no exemptions remain.
  - `alarm_control_panel`: extracted `_format_alarm_inputs` helper
  - `binary_sensor`: extracted `_fan_coil_gear_active` helper
  - `camera`: extracted `_camera_base_attrs` + `_CAMERA_BASE_KEYS` constant
  - `cover`: extracted `_apply_restored_position`, `_apply_restored_tilt`, `_compare_target_current`, `_sbus_blind_features`, `_sbus_blind_device_info`
  - `light`: 13 new module-level helpers/constants (rgb detection, color mode, restore state, Lua command builders)
- **WebSocket edge tests** (+19 tests): PING dispatch, `source` field fallback, auth-fail `PermissionError`, reconnect exception handling, stop-event exit
- **Stale device cleanup**: coordinator tracks `removed_ids` per bus after each refresh; `__init__.py` registers a listener that removes entity registry entries for disappeared device IDs. Protects against accidental removal on API failures.
- **Stale cleanup tests** (+10 tests): `_stale_uid_prefixes`, `_is_stale_entity`, `_cleanup_stale_entities` coverage
- **Total: 1 481 tests** across 44 files (~8 s runtime)

### Documentation — Full Overhaul
- **README.md**: rewritten as a compact, scannable landing page with architecture diagram, entity table, tested hubs matrix, all docs linked
- **README.pl.md**: full Polish translation matching EN structure (previously incomplete)
- **docs/installation.md**: step-by-step guide with all setup screenshots, troubleshooting table, rollback instructions
- **docs/entities.md**: complete entity reference — all platforms, attributes, availability semantics, automation examples
- **docs/real-time.md**: WebSocket + MQTT transport guide with architecture diagrams and troubleshooting tables
- **docs/development.md**: developer guide — project structure, CC rules, adding new sensors/platforms/virtual types, test patterns, live hub debugging

## [0.3.9] — 2026-06-25

### Hardening — Onboarding & Connection Resilience
- **Host validation**: Config flow now rejects invalid host formats (e.g., URLs with path, query, or fragment).
- **Retry logic**: Connection probes during onboarding automatically retry on transient errors.
- **Fallback mode**: If hub info retrieval is temporarily unavailable after successful login, onboarding proceeds with a graceful fallback using hub name from host.
- **User-facing error messages**: New `invalid_host` error translation in EN/PL.
- **Test coverage**: Comprehensive test suite for failsafe/fallback paths and retry logic.

### Quality
- Live hardware validation: Both hubs (WTP, SBUS) verified ✅ — all key API endpoints responsive (200).
- 100% line coverage maintained across config_flow, API client, and retry helpers.
- All CI/Lint/CodeQL/HACS workflows passing.

## [0.3.8] — 2026-06-24

### Test Coverage
- `custom_components/sinum` reached 100% line coverage (`4071/4071`).
- Final missing branches were covered in setup/filtering and helper edge-case paths.

### Quality
- Full local validation passed: `1234 passed`.
- Release gate checks on main passed (`CI`, `Lint`, `CodeQL Security Analysis`, `HACS Validation`).

## [0.3.7] — 2026-06-24

### Quality
- Fixed Mypy compatibility issues in `climate.py`, `light.py`, and `switch.py` that were failing the CI `Lint` workflow.
- Re-validated locally with: `ruff check`, `ruff format --check`, `mypy custom_components/sinum --ignore-missing-imports --no-site-packages`, and full test suite (`1220 passed`).

## [0.3.6] — 2026-06-24

### Quality
- Fixed CI `Lint` workflow failures by applying repository-wide `ruff format` changes.
- Verified locally after formatting: `ruff format --check`, `ruff check`, and full test suite (`1220 passed`).

## [0.3.5] — 2026-06-24

### Hardware/API Validation
- Read-only hardware smoke check refreshed in `docs/hardware_smoke_latest.md`.
- Both hubs passed login and core API endpoint checks (`/api/v1/info`, `/api/v1/devices/wtp`, `/api/v1/devices/sbus`, `/api/v1/devices/virtual`).

### Quality
- Full test suite passed (`1220 passed`).
- API-focused test suite passed (`117 passed`).
- Global coverage remains at 99% total for `custom_components/sinum`.

## [0.3.4] — 2026-06-24

### Test Coverage
- `custom_components/sinum/cover.py`: raised to 100%.
- `custom_components/sinum/sensor.py`: raised to 100%.
- Overall integration test coverage reached 100% in the CI coverage profile.

### Quality
- Added targeted restore-path and thermal schedule tests to lock in edge-case behavior and prevent regressions.

## [0.3.3] — 2026-06-24

### Test Coverage
- `custom_components/sinum/__init__.py`: raised to 100%.
- `custom_components/sinum/coordinator.py`: raised to 100%.
- `custom_components/sinum/light.py`: raised to 100%.
- `custom_components/sinum/number.py`: raised to 100%.
- `custom_components/sinum/sensor_schedule.py`: raised to 100%.
- `custom_components/sinum/sensor_virtual.py`: raised to 100%.
- `custom_components/sinum/switch.py`: raised to 100%.

### Quality
- Finalized the integration test sweep so the remaining uncovered runtime modules are now at or near full coverage.

## [0.3.2] — 2026-06-24

### Added
- Complexity quality gate enabled in Ruff (`C901`, mccabe max-complexity = 8) to prevent high-complexity regressions.

### Changed
- Release Gate behavior on push: pending required workflows are now treated as non-blocking to avoid false failures immediately after push.

### Test Coverage
- `custom_components/sinum/api.py`: raised to 100%.
- `custom_components/sinum/config_flow.py`: raised to 99%.
- `custom_components/sinum/cover.py`: raised to 98%.
- `custom_components/sinum/light.py`: raised to 95%.
- `custom_components/sinum/sensor_virtual.py`: raised to 99%.

## [0.3.1] — 2026-06-24

### Fixed
- Cover regression fix: `SinumBlindCover` now preserves last known position/tilt when coordinator snapshot is temporarily missing.
- SBUS RGB regression fix: optimistic state after HS color command now stores `led_color` and correctly reflects switch to RGB mode.
- Post-release validation: hardware smoke check refreshed in `docs/hardware_smoke_latest.md`.

## [0.3.0] — 2026-06-24

### Added
- Release stabilization policy and rollback procedure documented in `README.md` (Etap 0).
- Hardware smoke automation script (`scripts/hardware_smoke_check.py`) for WTP/SBUS API reachability and endpoint checks.
- Release gate status checker (`scripts/check_release_gate.py`) to validate required workflow outcomes before release activities.
- CI quality dashboard generator (`scripts/ci_quality_dashboard.py`) and scheduled workflow (`quality-dashboard.yml`) for pass-rate and duration tracking.
- Regression tests for critical areas:
  - API auth refresh edge case (refresh token retention)
  - Cover fallback behavior when device snapshot disappears
  - Firmware response normalization contracts (wrapper variants)

### Changed
- Neutral community branding mode (Etap 2A):
  - removed vendor-specific icon mapping from `manifest.json`
  - replaced brand assets with neutral community icon set
- Project version bumped to `0.3.0`.

## [0.2.9] — 2026-06-24

### Added
- Legal hardening in project documentation:
  - explicit non-affiliation notice in `README.md`
  - trademark and compliance clauses in `LICENSE`
  - legal/conduct rules for contributors in `CONTRIBUTING.md`

### Changed
- Clarified project status as unofficial community integration across user-facing docs.

## [0.2.8] — 2026-06-24

### Important Legal & Support Disclaimer
- This is an **unofficial** Home Assistant integration.
- This integration is **not authorized, endorsed, maintained, or supported** by TECH Sterowniki.
- The plugin does **not originate from TECH Sterowniki** and is maintained independently by the community author.
- The integration only uses data available from the Sinum hub/central unit APIs to read and control devices.
- The author/maintainer provides the code **as-is** and takes **no liability** for any direct or indirect damages, losses, or disruptions caused by use of this code.
- Using this integration is at your own risk and responsibility.

### Added
- Brand assets: icon (icon.png, icon@2x.png) displayed in Home Assistant UI and HACS marketplace.
- Code ownership: `.github/CODEOWNERS` defines review responsibilities for critical paths.
- Quality monitoring: per-module coverage tracking via `scripts/validate_coverage_gates.py` (informational only).
- Automation workflows:
  - `hardware-nightly.yml`: nightly smoke tests on real hubs (requires self-hosted runner setup).
  - `test-stability.yml`: weekly test stability report (slowest tests, pass rate, flaky test detection).
- Security setup guide: `SECURITY_SETUP.md` documents all manual GitHub configuration steps.

### Changed
- CI workflow enhanced: integrated quality gate validation step (non-blocking, informational reporting).
- `pytest.ini`: added markers (`hardware`, `quality`, `smoke`, `slow`) for test categorization.
- `README.md`: added stability badge linking to test-stability workflow.

## [0.2.7] — 2026-06-24

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
