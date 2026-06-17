# Contributing to Sinum (Sinapse) HA Integration

Thank you for your interest in contributing!

## How to Report a Bug

1. Check [existing issues](https://github.com/zaba848/Sinum_HomeAsistant_connector/issues) first
2. Include: Home Assistant version, integration version, hub firmware version, and relevant log output
3. Enable debug logging:
   ```yaml
   logger:
     logs:
       custom_components.sinum: debug
   ```

## How to Add Support for a New Device Type

1. Identify the device type string from the hub API (`/api/v1/devices/virtual|wtp|sbus`)
2. Add the constant to `const.py` (e.g., `WTYPE_NEW_DEVICE = "new_device"`)
3. Add the entity to the appropriate platform file (`sensor.py`, `switch.py`, etc.)
4. Add a fixture entry to `tests/fixtures/sinum_devices.json`
5. Write at least 3 tests in the relevant test file
6. Update `OPTIONAL_FIELDS` in `lua_scripts/mqtt_bridge.lua` with any new device-specific fields

## Code Style

- Python 3.12+, full type annotations
- Follow existing patterns: `CoordinatorEntity` base, `_attr_*` class attributes, defensive `dict.get()` calls
- No magic strings — add constants to `const.py`
- No comments unless the WHY is non-obvious

## Running Tests

```bash
python3 -m pytest tests/ -q
python3 -m pytest tests/ --cov=custom_components/sinum --cov-fail-under=80 -q
```

## Pull Request Guidelines

- One feature or fix per PR
- All tests must pass
- Coverage must not drop below 80%
- Update `CHANGELOG.md` under `## [Unreleased]`
