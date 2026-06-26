"""Tests for v0.4.0 improvements:
- target_temperature=0 → None (thermostat without sensor)
- SBUS rgb_controller supported_color_modes always includes HS
- Anti-bruteforce cooldown in config_flow reauth
- entity_category DIAGNOSTIC on PWM sensors
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _make_thermostat(device_data: dict[str, Any]):
    from custom_components.sinum.climate import SinumThermostat

    coordinator = MagicMock()
    coordinator.client.decode_temperature = lambda raw: raw / 10
    coordinator.client.encode_temperature = lambda c: round(c * 10)
    coordinator.virtual_devices = {10: device_data}
    entity = SinumThermostat(coordinator, 10, "entry")
    entity.hass = MagicMock()
    return entity


def _make_bus_climate(device_data: dict[str, Any], bus: str = "sbus"):
    from custom_components.sinum.climate import SinumTemperatureRegulatorClimate

    coordinator = MagicMock()
    store = {"sbus": "sbus_devices", "wtp": "wtp_devices"}[bus]
    setattr(coordinator, store, {5: device_data})
    setattr(coordinator, "wtp_devices" if bus == "sbus" else "sbus_devices", {})
    entity = SinumTemperatureRegulatorClimate(coordinator, 5, "entry", bus)
    entity.hass = MagicMock()
    return entity


def _make_rgb_light(device_data: dict[str, Any], bus: str = "sbus"):
    from custom_components.sinum.light import SinumBusRgbLight

    coordinator = MagicMock()
    store = "sbus_devices" if bus == "sbus" else "wtp_devices"
    setattr(coordinator, store, {7: device_data})
    setattr(coordinator, "wtp_devices" if bus == "sbus" else "sbus_devices", {})
    entity = SinumBusRgbLight(coordinator, 7, "entry", bus)
    entity.hass = MagicMock()
    return entity


# ──────────────────────────────────────────────────────────────────────────────
# target_temperature = 0 → None
# ──────────────────────────────────────────────────────────────────────────────


class TestTargetTemperatureZero:
    def test_virtual_thermostat_zero_returns_none(self):
        """target_temperature=0 means no sensor assigned — must return None."""
        entity = _make_thermostat(
            {"id": 10, "type": "thermostat", "name": "T", "target_temperature": 0, "temperature": 0}
        )
        assert entity.target_temperature is None

    def test_virtual_thermostat_none_returns_none(self):
        entity = _make_thermostat(
            {"id": 10, "type": "thermostat", "name": "T", "target_temperature": None, "temperature": 200}
        )
        assert entity.target_temperature is None

    def test_virtual_thermostat_valid_value(self):
        entity = _make_thermostat(
            {"id": 10, "type": "thermostat", "name": "T", "target_temperature": 220, "temperature": 215}
        )
        assert entity.target_temperature == 22.0

    def test_virtual_thermostat_current_temp_zero_returns_none(self):
        """current_temperature=0 (no physical sensor) must return None."""
        entity = _make_thermostat(
            {"id": 10, "type": "thermostat", "name": "T", "target_temperature": 220, "temperature": 0}
        )
        assert entity.current_temperature is None

    def test_bus_climate_target_zero_returns_none(self):
        entity = _make_bus_climate(
            {"id": 5, "type": "temperature_regulator", "name": "R",
             "target_temperature": 0, "temperature": 200}
        )
        assert entity.target_temperature is None

    def test_bus_climate_target_valid(self):
        entity = _make_bus_climate(
            {"id": 5, "type": "temperature_regulator", "name": "R",
             "target_temperature": 195, "temperature": 200}
        )
        assert entity.target_temperature == pytest.approx(19.5, abs=0.01)

    def test_bus_climate_current_zero_returns_none(self):
        entity = _make_bus_climate(
            {"id": 5, "type": "temperature_regulator", "name": "R",
             "target_temperature": 200, "temperature": 0}
        )
        assert entity.current_temperature is None


# ──────────────────────────────────────────────────────────────────────────────
# SBUS rgb_controller supported_color_modes
# ──────────────────────────────────────────────────────────────────────────────


class TestSbusRgbColorModes:
    def test_sbus_rgb_without_led_color_supports_hs(self):
        """SBUS rgb_controller with no led_color still exposes HS mode (Lua control)."""
        from homeassistant.components.light import ColorMode

        entity = _make_rgb_light({"id": 7, "type": "rgb_controller", "name": "RGB", "state": False})
        assert ColorMode.HS in entity.supported_color_modes

    def test_sbus_rgb_with_led_color_supports_hs(self):
        from homeassistant.components.light import ColorMode

        entity = _make_rgb_light(
            {"id": 7, "type": "rgb_controller", "name": "RGB", "state": True,
             "led_color": "#FF0000", "color_mode": "rgb"}
        )
        assert ColorMode.HS in entity.supported_color_modes

    def test_sbus_rgb_color_mode_defaults_to_hs(self):
        from homeassistant.components.light import ColorMode

        entity = _make_rgb_light({"id": 7, "type": "rgb_controller", "name": "RGB", "state": False})
        assert entity.color_mode == ColorMode.HS

    def test_sbus_rgb_color_mode_temperature_when_hub_reports_it(self):
        from homeassistant.components.light import ColorMode

        entity = _make_rgb_light(
            {"id": 7, "type": "rgb_controller", "name": "RGB", "state": True,
             "color_mode": "temperature", "white_temperature": 4000}
        )
        assert entity.color_mode == ColorMode.COLOR_TEMP

    def test_wtp_rgb_without_led_color_reports_hs_from_type(self):
        """WTP rgb_controller with type=rgb_controller declares HS via device-type check,
        even if led_color is absent. (REST color PATCH is attempted but may 422 on hardware.)"""
        from homeassistant.components.light import ColorMode

        entity = _make_rgb_light(
            {"id": 7, "type": "rgb_controller", "name": "RGB", "state": False},
            bus="wtp",
        )
        assert ColorMode.HS in entity.supported_color_modes

    def test_wtp_rgb_with_led_color_supports_hs(self):
        from homeassistant.components.light import ColorMode

        entity = _make_rgb_light(
            {"id": 7, "type": "rgb_controller", "name": "RGB", "state": True,
             "led_color": "#00FF00", "color_mode": "rgb"},
            bus="wtp",
        )
        assert ColorMode.HS in entity.supported_color_modes

    def test_sbus_rgb_hs_color_from_led_color(self):
        entity = _make_rgb_light(
            {"id": 7, "type": "rgb_controller", "name": "RGB", "state": True,
             "led_color": "#FF0000"}
        )
        hs = entity.hs_color
        assert hs is not None
        assert abs(hs[0] - 0.0) < 2  # red hue ≈ 0°

    def test_sbus_rgb_no_led_color_hs_returns_none(self):
        entity = _make_rgb_light({"id": 7, "type": "rgb_controller", "name": "RGB", "state": False})
        assert entity.hs_color is None


# ──────────────────────────────────────────────────────────────────────────────
# Anti-bruteforce reauth cooldown
# ──────────────────────────────────────────────────────────────────────────────


class TestReauthCooldown:
    def _make_hass(self) -> MagicMock:
        hass = MagicMock()
        hass.data = {}
        return hass

    def test_no_failures_no_cooldown(self):
        from custom_components.sinum.config_flow import _reauth_cooldown_remaining

        hass = self._make_hass()
        assert _reauth_cooldown_remaining(hass, "entry1") == 0.0

    def test_below_threshold_no_cooldown(self):
        from custom_components.sinum.config_flow import (
            _REAUTH_MAX_FAILS,
            _reauth_cooldown_remaining,
            _reauth_record_failure,
        )

        hass = self._make_hass()
        for _ in range(_REAUTH_MAX_FAILS - 1):
            _reauth_record_failure(hass, "entry1")
        assert _reauth_cooldown_remaining(hass, "entry1") == 0.0

    def test_at_threshold_blocks(self):
        from custom_components.sinum.config_flow import (
            _REAUTH_MAX_FAILS,
            _reauth_cooldown_remaining,
            _reauth_record_failure,
        )

        hass = self._make_hass()
        for _ in range(_REAUTH_MAX_FAILS):
            _reauth_record_failure(hass, "entry1")
        assert _reauth_cooldown_remaining(hass, "entry1") > 0

    def test_cooldown_duration(self):
        from custom_components.sinum.config_flow import (
            _REAUTH_COOLDOWN_SEC,
            _REAUTH_MAX_FAILS,
            _reauth_cooldown_remaining,
            _reauth_record_failure,
        )

        hass = self._make_hass()
        for _ in range(_REAUTH_MAX_FAILS):
            _reauth_record_failure(hass, "entry1")
        remaining = _reauth_cooldown_remaining(hass, "entry1")
        assert remaining > _REAUTH_COOLDOWN_SEC - 2
        assert remaining <= _REAUTH_COOLDOWN_SEC

    def test_reset_clears_cooldown(self):
        from custom_components.sinum.config_flow import (
            _REAUTH_MAX_FAILS,
            _reauth_cooldown_remaining,
            _reauth_record_failure,
            _reauth_reset,
        )

        hass = self._make_hass()
        for _ in range(_REAUTH_MAX_FAILS):
            _reauth_record_failure(hass, "entry1")
        assert _reauth_cooldown_remaining(hass, "entry1") > 0
        _reauth_reset(hass, "entry1")
        assert _reauth_cooldown_remaining(hass, "entry1") == 0.0

    def test_independent_entries(self):
        from custom_components.sinum.config_flow import (
            _REAUTH_MAX_FAILS,
            _reauth_cooldown_remaining,
            _reauth_record_failure,
        )

        hass = self._make_hass()
        for _ in range(_REAUTH_MAX_FAILS):
            _reauth_record_failure(hass, "entry_a")
        assert _reauth_cooldown_remaining(hass, "entry_a") > 0
        assert _reauth_cooldown_remaining(hass, "entry_b") == 0.0

    @pytest.mark.asyncio
    async def test_reauth_confirm_shows_error_when_blocked(self, hass):
        from custom_components.sinum.config_flow import (
            _REAUTH_MAX_FAILS,
            SinumConfigFlow,
            _reauth_record_failure,
        )

        fake_entry = MagicMock()
        fake_entry.entry_id = "e1"
        fake_entry.data = {"host": "10.0.0.1", "auth_mode": "token"}

        for _ in range(_REAUTH_MAX_FAILS):
            _reauth_record_failure(hass, "e1")

        flow = SinumConfigFlow()
        flow.hass = hass
        flow.context = {"entry_id": "e1", "source": "reauth"}
        flow._get_reauth_entry = MagicMock(return_value=fake_entry)

        result = await flow.async_step_reauth_confirm(user_input=None)
        assert result["type"] == "form"
        assert result["errors"].get("base") == "too_many_attempts"


# ──────────────────────────────────────────────────────────────────────────────
# PWM entity_category DIAGNOSTIC
# ──────────────────────────────────────────────────────────────────────────────


class TestPwmEntityCategory:
    def test_pwm_duty_cycle_is_diagnostic(self):
        from homeassistant.const import EntityCategory

        from custom_components.sinum.sensor_bus_descriptions import SBUS_SENSORS

        pwm_duty = next((d for d in SBUS_SENSORS if d.key == "pwm_duty_cycle"), None)
        assert pwm_duty is not None
        assert pwm_duty.entity_category == EntityCategory.DIAGNOSTIC

    def test_pwm_frequency_is_diagnostic(self):
        from homeassistant.const import EntityCategory

        from custom_components.sinum.sensor_bus_descriptions import SBUS_SENSORS

        pwm_freq = next((d for d in SBUS_SENSORS if d.key == "pwm_frequency"), None)
        assert pwm_freq is not None
        assert pwm_freq.entity_category == EntityCategory.DIAGNOSTIC

    def test_pwm_sensors_disabled_by_default(self):
        from custom_components.sinum.sensor_bus_descriptions import SBUS_SENSORS

        for desc in SBUS_SENSORS:
            if desc.key in {"pwm_duty_cycle", "pwm_frequency"}:
                assert desc.entity_registry_enabled_default is False
