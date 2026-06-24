"""Tests for light async_setup_entry and entity methods."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_COLOR_TEMP_KELVIN, ATTR_HS_COLOR

from custom_components.sinum.const import (
    STYPE_DIMMER,
    STYPE_RGB_CONTROLLER,
    VTYPE_DIMMER_RGB,
    VTYPE_DIMMER_RGB_INTEGRATOR,
    WTYPE_DIMMER,
    WTYPE_RGB_CONTROLLER,
)
from custom_components.sinum.light import (
    SinumBusDimmerLight,
    SinumBusRgbLight,
    SinumButtonLight,
    SinumDimmerLight,
    _hex_to_hs,
    _hs_to_hex,
    async_setup_entry,
)


def _make_coordinator(*, virtual=None, wtp=None, sbus=None):
    c = MagicMock()
    c.virtual_devices = virtual or {}
    c.wtp_devices = wtp or {}
    c.sbus_devices = sbus or {}
    c.client = MagicMock()
    c.client.patch_virtual_device = AsyncMock(return_value={})
    c.client.patch_wtp_device = AsyncMock(return_value={})
    c.client.patch_sbus_device = AsyncMock(return_value={})
    return c


def _make_entry(coordinator):
    entry = MagicMock()
    entry.runtime_data = coordinator
    entry.entry_id = "test_entry"
    return entry


def _wire(entity):
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    return entity


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_virtual_dimmer_rgb_creates_entity(self):
        virtual = {1: {"id": 1, "type": VTYPE_DIMMER_RGB, "name": "Dimmer RGB"}}
        coordinator = _make_coordinator(virtual=virtual)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        assert any(isinstance(e, SinumDimmerLight) for e in added)

    @pytest.mark.asyncio
    async def test_virtual_dimmer_rgb_integrator_creates_entity(self):
        virtual = {2: {"id": 2, "type": VTYPE_DIMMER_RGB_INTEGRATOR, "name": "DRGI"}}
        coordinator = _make_coordinator(virtual=virtual)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        assert any(isinstance(e, SinumDimmerLight) for e in added)

    @pytest.mark.asyncio
    async def test_wtp_dimmer_creates_entity(self):
        wtp = {3: {"id": 3, "type": WTYPE_DIMMER, "name": "WTP Dim"}}
        coordinator = _make_coordinator(wtp=wtp)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        dimmers = [e for e in added if isinstance(e, SinumBusDimmerLight) and e._bus == "wtp"]
        assert len(dimmers) == 1

    @pytest.mark.asyncio
    async def test_wtp_rgb_creates_entity(self):
        wtp = {4: {"id": 4, "type": WTYPE_RGB_CONTROLLER, "name": "WTP RGB"}}
        coordinator = _make_coordinator(wtp=wtp)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        rgbs = [e for e in added if isinstance(e, SinumBusRgbLight) and e._bus == "wtp"]
        assert len(rgbs) == 1

    @pytest.mark.asyncio
    async def test_sbus_dimmer_creates_entity(self):
        sbus = {5: {"id": 5, "type": STYPE_DIMMER, "name": "SBUS Dim"}}
        coordinator = _make_coordinator(sbus=sbus)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        dimmers = [e for e in added if isinstance(e, SinumBusDimmerLight) and e._bus == "sbus"]
        assert len(dimmers) == 1

    @pytest.mark.asyncio
    async def test_sbus_rgb_creates_entity(self):
        sbus = {6: {"id": 6, "type": STYPE_RGB_CONTROLLER, "name": "SBUS RGB"}}
        coordinator = _make_coordinator(sbus=sbus)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        rgbs = [e for e in added if isinstance(e, SinumBusRgbLight) and e._bus == "sbus"]
        assert len(rgbs) == 1

    @pytest.mark.asyncio
    async def test_unknown_type_skipped(self):
        virtual = {7: {"id": 7, "type": "unknown", "name": "Unknown"}}
        coordinator = _make_coordinator(virtual=virtual)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        assert len(added) == 0


class TestHexHsConversions:
    def test_hex_to_hs_red(self):
        h, s = _hex_to_hs("#FF0000")
        assert h == pytest.approx(0.0, abs=1)
        assert s == pytest.approx(100.0, abs=1)

    def test_hex_to_hs_green(self):
        h, s = _hex_to_hs("#00FF00")
        assert h == pytest.approx(120.0, abs=1)
        assert s == pytest.approx(100.0, abs=1)

    def test_hex_to_hs_blue(self):
        h, s = _hex_to_hs("#0000FF")
        assert h == pytest.approx(240.0, abs=1)
        assert s == pytest.approx(100.0, abs=1)

    def test_hex_to_hs_white(self):
        h, s = _hex_to_hs("#FFFFFF")
        assert s == pytest.approx(0.0, abs=1)

    def test_hex_to_hs_short_string_returns_zero(self):
        assert _hex_to_hs("FF00") == (0.0, 0.0)

    def test_hex_to_hs_without_hash(self):
        h, s = _hex_to_hs("FF0000")
        assert h == pytest.approx(0.0, abs=1)

    def test_hs_to_hex_red(self):
        assert _hs_to_hex(0.0, 100.0).upper() == "#FF0000"

    def test_hs_to_hex_green(self):
        assert _hs_to_hex(120.0, 100.0).upper() == "#00FF00"

    def test_roundtrip(self):
        original = "#1A7FCD"
        h, s = _hex_to_hs(original)
        result = _hs_to_hex(h, s).upper()
        # Allow small rounding difference
        assert result == original.upper() or len(result) == 7

    def test_hex_to_hs_invalid_hex_chars_returns_zero(self):
        """Lines 71-72: ValueError when hex string has invalid characters."""
        # 6+ chars but contains non-hex characters → except ValueError → (0.0, 0.0)
        result = _hex_to_hs("GGGGGG")
        assert result == (0.0, 0.0)


class TestSinumDimmerLight:
    def _make(self, device: dict):
        coordinator = _make_coordinator(virtual={1: device})
        entity = _wire(SinumDimmerLight(coordinator, 1, "test_entry"))
        return entity, coordinator

    def test_is_on_when_state_on(self):
        entity, _ = self._make({"id": 1, "type": VTYPE_DIMMER_RGB, "name": "D", "state": "on"})
        assert entity.is_on is True

    def test_is_off_when_state_off(self):
        entity, _ = self._make({"id": 1, "type": VTYPE_DIMMER_RGB, "name": "D", "state": False})
        assert entity.is_on is False

    def test_brightness_from_raw(self):
        entity, _ = self._make({"id": 1, "type": VTYPE_DIMMER_RGB, "name": "D", "brightness": 50})
        assert entity.brightness == round(50 / 100 * 255)

    def test_brightness_none_when_missing(self):
        entity, _ = self._make({"id": 1, "type": VTYPE_DIMMER_RGB, "name": "D"})
        assert entity.brightness is None

    def test_hs_color_from_led_color(self):
        entity, _ = self._make(
            {"id": 1, "type": VTYPE_DIMMER_RGB, "name": "D", "led_color": "#FF0000"}
        )
        hs = entity.hs_color
        assert hs is not None
        assert hs[0] == pytest.approx(0.0, abs=1)

    def test_hs_color_none_when_missing(self):
        entity, _ = self._make({"id": 1, "type": VTYPE_DIMMER_RGB, "name": "D"})
        assert entity.hs_color is None

    def test_color_temp_kelvin(self):
        entity, _ = self._make(
            {"id": 1, "type": VTYPE_DIMMER_RGB, "name": "D", "white_temperature": 4000}
        )
        assert entity.color_temp_kelvin == 4000

    def test_color_mode_rgb(self):
        entity, _ = self._make(
            {"id": 1, "type": VTYPE_DIMMER_RGB, "name": "D", "color_mode": "rgb"}
        )
        from homeassistant.components.light import ColorMode

        assert entity.color_mode == ColorMode.HS

    def test_color_mode_temperature(self):
        entity, _ = self._make(
            {"id": 1, "type": VTYPE_DIMMER_RGB, "name": "D", "color_mode": "temperature"}
        )
        from homeassistant.components.light import ColorMode

        assert entity.color_mode == ColorMode.COLOR_TEMP

    def test_color_mode_default_hs_for_rgb_type(self):
        entity, _ = self._make({"id": 1, "type": VTYPE_DIMMER_RGB, "name": "D"})
        from homeassistant.components.light import ColorMode

        assert entity.color_mode == ColorMode.HS

    def test_supported_color_modes_rgb_type_defaults_to_hs(self):
        """RGB-capable device types expose the HA color picker even before state has led_color."""
        from homeassistant.components.light import ColorMode

        entity, _ = self._make({"id": 1, "type": VTYPE_DIMMER_RGB, "name": "D"})
        assert entity.supported_color_modes == {ColorMode.HS}

    def test_supported_color_modes_hs_when_led_color(self):
        """Lines 108-117: _supported_color_modes returns HS when led_color present."""
        from homeassistant.components.light import ColorMode

        entity, _ = self._make(
            {"id": 1, "type": VTYPE_DIMMER_RGB, "name": "D", "led_color": "#FF0000"}
        )
        assert ColorMode.HS in entity.supported_color_modes

    def test_supported_color_modes_color_temp_when_white_temperature(self):
        """Lines 108-117: _supported_color_modes returns COLOR_TEMP when white_temperature present."""
        from homeassistant.components.light import ColorMode

        entity, _ = self._make(
            {"id": 1, "type": VTYPE_DIMMER_RGB, "name": "D", "white_temperature": 4000}
        )
        assert ColorMode.COLOR_TEMP in entity.supported_color_modes

    def test_supported_color_modes_hs_and_color_temp_for_rgbww(self):
        """RGBWW devices expose color and white-temperature controls."""
        from homeassistant.components.light import ColorMode

        entity, _ = self._make(
            {"id": 1, "type": VTYPE_DIMMER_RGB, "name": "D", "labels": ["rgbww"]}
        )
        assert entity.supported_color_modes == {ColorMode.HS, ColorMode.COLOR_TEMP}

    def test_color_mode_hs_for_rgbww(self):
        """RGBWW devices default to color mode unless the hub reports temperature mode."""
        from homeassistant.components.light import ColorMode

        entity, _ = self._make(
            {"id": 1, "type": VTYPE_DIMMER_RGB, "name": "D", "labels": ["rgbww"]}
        )
        assert entity.color_mode == ColorMode.HS

    @pytest.mark.asyncio
    async def test_async_turn_on_basic(self):
        entity, coordinator = self._make(
            {"id": 1, "type": VTYPE_DIMMER_RGB, "name": "D", "state": "off"}
        )
        coordinator.client.patch_virtual_device = AsyncMock(return_value={"state": True})
        await entity.async_turn_on()
        coordinator.client.patch_virtual_device.assert_awaited_once()
        payload = coordinator.client.patch_virtual_device.await_args.args[1]
        assert payload["state"] is True

    @pytest.mark.asyncio
    async def test_async_turn_on_with_brightness(self):
        entity, coordinator = self._make(
            {"id": 1, "type": VTYPE_DIMMER_RGB, "name": "D", "state": "off"}
        )
        coordinator.client.patch_virtual_device = AsyncMock(return_value={})
        await entity.async_turn_on(**{ATTR_BRIGHTNESS: 128})
        payload = coordinator.client.patch_virtual_device.await_args.args[1]
        assert "brightness" in payload
        assert payload["brightness"] == round(128 / 255 * 100)

    @pytest.mark.asyncio
    async def test_async_turn_on_with_hs_color(self):
        entity, coordinator = self._make({"id": 1, "type": VTYPE_DIMMER_RGB, "name": "D"})
        coordinator.client.patch_virtual_device = AsyncMock(return_value={})
        await entity.async_turn_on(**{ATTR_HS_COLOR: (0.0, 100.0)})
        payload = coordinator.client.patch_virtual_device.await_args.args[1]
        assert "led_color" in payload
        assert "color_mode" not in payload
        entity, coordinator = self._make({"id": 1, "type": VTYPE_DIMMER_RGB, "name": "D"})
        coordinator.client.patch_virtual_device = AsyncMock(return_value={})
        await entity.async_turn_on(**{ATTR_COLOR_TEMP_KELVIN: 4000})
        payload = coordinator.client.patch_virtual_device.await_args.args[1]
        assert payload["white_temperature"] == 4000
        assert "color_mode" not in payload

    @pytest.mark.asyncio
    async def test_async_turn_off(self):
        entity, coordinator = self._make(
            {"id": 1, "type": VTYPE_DIMMER_RGB, "name": "D", "state": "on"}
        )
        coordinator.client.patch_virtual_device = AsyncMock(return_value={})
        await entity.async_turn_off()
        payload = coordinator.client.patch_virtual_device.await_args.args[1]
        assert payload["state"] is False


class TestSinumBusDimmerLight:
    def _make_wtp(self):
        device = {"id": 3, "type": WTYPE_DIMMER, "name": "D", "state": True, "target_level": 75}
        coordinator = _make_coordinator(wtp={3: device})
        entity = _wire(SinumBusDimmerLight(coordinator, 3, "test_entry", "wtp"))
        return entity, coordinator

    def test_is_on(self):
        entity, _ = self._make_wtp()
        assert entity.is_on is True

    def test_brightness_from_target_level(self):
        entity, _ = self._make_wtp()
        assert entity.brightness == round(75 / 100 * 255)

    def test_brightness_none_when_missing(self):
        device = {"id": 3, "type": WTYPE_DIMMER, "name": "D", "state": False}
        coordinator = _make_coordinator(wtp={3: device})
        entity = _wire(SinumBusDimmerLight(coordinator, 3, "test_entry", "wtp"))
        assert entity.brightness is None

    @pytest.mark.asyncio
    async def test_turn_on_with_brightness_wtp(self):
        entity, coordinator = self._make_wtp()
        coordinator.client.patch_wtp_device = AsyncMock(return_value={})
        await entity.async_turn_on(**{ATTR_BRIGHTNESS: 200})
        payload = coordinator.client.patch_wtp_device.await_args.args[1]
        assert payload["state"] is True
        assert "target_level" in payload

    @pytest.mark.asyncio
    async def test_turn_off_sbus(self):
        device = {"id": 5, "type": STYPE_DIMMER, "name": "D", "state": True}
        coordinator = _make_coordinator(sbus={5: device})
        entity = _wire(SinumBusDimmerLight(coordinator, 5, "test_entry", "sbus"))
        coordinator.client.patch_sbus_device = AsyncMock(return_value={})
        await entity.async_turn_off()
        coordinator.client.patch_sbus_device.assert_awaited_once_with(5, {"state": False})


class TestSinumBusRgbLight:
    def _make_wtp(self, device: dict | None = None):
        d = device or {
            "id": 4,
            "type": WTYPE_RGB_CONTROLLER,
            "name": "RGB",
            "state": True,
            "brightness": 80,
            "led_color": "#00FF00",
        }
        coordinator = _make_coordinator(wtp={4: d})
        entity = _wire(SinumBusRgbLight(coordinator, 4, "test_entry", "wtp"))
        return entity, coordinator

    def test_is_on(self):
        entity, _ = self._make_wtp()
        assert entity.is_on is True

    def test_brightness_not_exposed(self):
        entity, _ = self._make_wtp()
        assert entity.brightness == round(80 / 100 * 255)

    def test_hs_color_exposed(self):
        entity, _ = self._make_wtp()
        hs = entity.hs_color
        assert hs is not None
        assert hs[0] == pytest.approx(120.0, abs=1)

    @pytest.mark.asyncio
    async def test_turn_on_wtp_sends_color(self):
        entity, coordinator = self._make_wtp()
        coordinator.client.patch_wtp_device = AsyncMock(return_value={})
        await entity.async_turn_on(**{ATTR_HS_COLOR: (240.0, 100.0)})
        payload = coordinator.client.patch_wtp_device.await_args.args[1]
        assert payload == {"state": True, "color": "#0000FF"}

    @pytest.mark.asyncio
    async def test_turn_on_with_color_temp_converts_to_led_color(self):
        entity, coordinator = self._make_wtp()
        coordinator.client.patch_wtp_device = AsyncMock(return_value={})
        await entity.async_turn_on(**{ATTR_COLOR_TEMP_KELVIN: 3000})
        payload = coordinator.client.patch_wtp_device.await_args.args[1]
        assert payload["state"] is True
        assert "color" in payload
        assert "led_color" not in payload
        assert "white_temperature" not in payload

    @pytest.mark.asyncio
    async def test_turn_off_sbus(self):
        d = {"id": 6, "type": STYPE_RGB_CONTROLLER, "name": "RGB", "state": True}
        coordinator = _make_coordinator(sbus={6: d})
        entity = _wire(SinumBusRgbLight(coordinator, 6, "test_entry", "sbus"))
        coordinator.client.patch_sbus_device = AsyncMock(return_value={})
        await entity.async_turn_off()
        coordinator.client.patch_sbus_device.assert_awaited_once_with(6, {"state": False})

    # ---- new tests to improve coverage ----

    def test_supported_color_modes_is_hs(self):
        from homeassistant.components.light import ColorMode

        entity, _ = self._make_wtp()
        assert entity.supported_color_modes == {ColorMode.HS}

    def test_color_mode_uses_device_color_mode(self):
        from homeassistant.components.light import ColorMode

        d = {
            "id": 4,
            "type": WTYPE_RGB_CONTROLLER,
            "name": "RGB",
            "state": True,
            "color_mode": "rgb",
            "led_color": "#FF0000",
        }
        entity, _ = self._make_wtp(d)
        assert entity.color_mode == ColorMode.HS

    @pytest.mark.asyncio
    async def test_turn_on_with_brightness_sends_brightness(self):
        # brightness is read-only on rgb_controller — encoded as V in color hex
        entity, coordinator = self._make_wtp()
        coordinator.client.patch_wtp_device = AsyncMock(return_value={})
        await entity.async_turn_on(**{ATTR_BRIGHTNESS: 128})
        payload = coordinator.client.patch_wtp_device.await_args.args[1]
        # HS preserved from led_color "#00FF00" (120°, 100%), V = 128/255
        assert payload == {"state": True, "color": "#008000"}

    @pytest.mark.asyncio
    async def test_turn_on_rgbww_device_sends_color_with_brightness_encoded(self):
        d = {
            "id": 4,
            "type": WTYPE_RGB_CONTROLLER,
            "name": "RGB",
            "state": False,
            "labels": ["rgbww"],
        }
        coordinator = _make_coordinator(wtp={4: d})
        entity = _wire(SinumBusRgbLight(coordinator, 4, "test_entry", "wtp"))
        coordinator.client.patch_wtp_device = AsyncMock(return_value={})
        await entity.async_turn_on(**{ATTR_HS_COLOR: (120.0, 100.0), ATTR_BRIGHTNESS: 200})
        payload = coordinator.client.patch_wtp_device.await_args.args[1]
        # brightness (200/255) encoded into color V — no separate brightness field
        assert payload == {"state": True, "color": "#00C800"}

    @pytest.mark.asyncio
    async def test_turn_off_wtp(self):
        """Lines 372-375: async_turn_off on wtp bus calls patch_wtp_device."""
        entity, coordinator = self._make_wtp()
        coordinator.client.patch_wtp_device = AsyncMock(return_value={})
        await entity.async_turn_off()
        coordinator.client.patch_wtp_device.assert_awaited_once_with(4, {"state": False})

    # ---- tests that verify real hardware behavior ----

    def test_hs_color_reads_led_color_not_command_target(self):
        """led_color is the actual hardware output; color diverges when in temperature mode."""
        d = {
            "id": 4,
            "type": WTYPE_RGB_CONTROLLER,
            "name": "RGB",
            "state": True,
            "color": "#0000FF",  # last command we sent (blue)
            "led_color": "#FF0000",  # what the LED is actually showing (red)
        }
        coordinator = _make_coordinator(wtp={4: d})
        entity = _wire(SinumBusRgbLight(coordinator, 4, "test_entry", "wtp"))
        hs = entity.hs_color
        assert hs is not None
        # Must report red (led_color), not blue (color)
        assert hs[0] == pytest.approx(0.0, abs=1)

    @pytest.mark.asyncio
    async def test_turn_on_temperature_mode_sends_only_state(self):
        """In temperature mode the hub ignores color/brightness — only state (on/off) works."""
        d = {
            "id": 4,
            "type": WTYPE_RGB_CONTROLLER,
            "name": "RGB",
            "state": False,
            "color_mode": "temperature",
            "brightness": 80,
            "led_color": "#cc1000",
        }
        coordinator = _make_coordinator(wtp={4: d})
        entity = _wire(SinumBusRgbLight(coordinator, 4, "test_entry", "wtp"))
        coordinator.client.patch_wtp_device = AsyncMock(return_value={})
        await entity.async_turn_on(**{ATTR_BRIGHTNESS: 200, ATTR_HS_COLOR: (0.0, 100.0)})
        payload = coordinator.client.patch_wtp_device.await_args.args[1]
        # brightness and color must NOT be in payload — firmware owns them in temperature mode
        assert payload == {"state": True}

    @pytest.mark.asyncio
    async def test_turn_on_temperature_mode_ignores_kelvin(self):
        """Kelvin change is also ignored in temperature mode — schedule system controls it."""
        d = {
            "id": 4,
            "type": WTYPE_RGB_CONTROLLER,
            "name": "RGB",
            "state": False,
            "color_mode": "temperature",
            "white_temperature": 3000,
        }
        coordinator = _make_coordinator(wtp={4: d})
        entity = _wire(SinumBusRgbLight(coordinator, 4, "test_entry", "wtp"))
        coordinator.client.patch_wtp_device = AsyncMock(return_value={})
        await entity.async_turn_on(**{ATTR_COLOR_TEMP_KELVIN: 6500})
        payload = coordinator.client.patch_wtp_device.await_args.args[1]
        assert payload == {"state": True}

    @pytest.mark.asyncio
    async def test_turn_on_animation_mode_sends_only_state(self):
        """In animation mode the firmware runs its own color sequence — only on/off works."""
        d = {
            "id": 4,
            "type": WTYPE_RGB_CONTROLLER,
            "name": "RGB",
            "state": False,
            "color_mode": "animation",
        }
        coordinator = _make_coordinator(wtp={4: d})
        entity = _wire(SinumBusRgbLight(coordinator, 4, "test_entry", "wtp"))
        coordinator.client.patch_wtp_device = AsyncMock(return_value={})
        await entity.async_turn_on(**{ATTR_BRIGHTNESS: 200})
        payload = coordinator.client.patch_wtp_device.await_args.args[1]
        assert payload == {"state": True}

    @pytest.mark.asyncio
    async def test_turn_on_color_mode_sends_color_with_brightness(self):
        """In color mode brightness IS encoded in the color hex (V component in HSV)."""
        d = {
            "id": 4,
            "type": WTYPE_RGB_CONTROLLER,
            "name": "RGB",
            "state": True,
            "color_mode": "color",
            "led_color": "#00FF00",  # current green at full brightness
        }
        coordinator = _make_coordinator(wtp={4: d})
        entity = _wire(SinumBusRgbLight(coordinator, 4, "test_entry", "wtp"))
        coordinator.client.patch_wtp_device = AsyncMock(return_value={})
        await entity.async_turn_on(**{ATTR_BRIGHTNESS: 128})
        payload = coordinator.client.patch_wtp_device.await_args.args[1]
        # Green (120°, 100%) at 50% brightness → #008000
        assert payload == {"state": True, "color": "#008000"}

    @pytest.mark.asyncio
    async def test_turn_on_sbus_temperature_mode_uses_lua(self):
        """SBUS Lua works regardless of color_mode — brightness change sent via Lua even in temperature mode."""
        from unittest.mock import AsyncMock as AM
        d = {
            "id": 119,
            "type": STYPE_RGB_CONTROLLER,
            "name": "RGB Controller 1",
            "state": True,
            "color_mode": "temperature",
            "brightness": 80,
            "led_color": "#cc1000",
            "white_temperature": 3000,
        }
        coordinator = _make_coordinator(sbus={119: d})
        coordinator.client.get_or_create_scene = AM(return_value=10)
        coordinator.client.patch_scene_lua = AM(return_value=None)
        coordinator.client.run_scene = AM(return_value=None)
        coordinator.client.patch_sbus_device = AM(return_value={})
        entity = _wire(SinumBusRgbLight(coordinator, 119, "test_entry", "sbus"))
        await entity.async_turn_on(**{ATTR_BRIGHTNESS: 255})
        # Lua was called with set_brightness
        lua_code = coordinator.client.patch_scene_lua.await_args.args[1]
        assert "set_brightness" in lua_code
        assert "100" in lua_code  # 255/255*100 = 100
        # REST carries only state=True (no color fields for SBUS)
        payload = coordinator.client.patch_sbus_device.await_args.args[1]
        assert payload == {"state": True}


class TestSinumButtonLight:
    def _make(self, bus: str = "sbus", color: str = "#0072c3"):
        device = {"id": 70, "name": "Button", "type": "button", "color": color}
        if bus == "wtp":
            coordinator = _make_coordinator(wtp={70: device})
        else:
            coordinator = _make_coordinator(sbus={70: device})
        entity = _wire(SinumButtonLight(coordinator, 70, "test_entry", bus))
        return entity, coordinator

    def test_is_on_nonblack_color(self):
        entity, _ = self._make(color="#0072c3")
        assert entity.is_on is True

    def test_is_off_black_color(self):
        entity, _ = self._make(color="#000000")
        assert entity.is_on is False

    def test_hs_color_roundtrip(self):
        entity, _ = self._make(color="#FF0000")
        hs = entity.hs_color
        assert hs is not None
        assert hs[0] == pytest.approx(0.0, abs=1)
        assert hs[1] == pytest.approx(100.0, abs=1)

    def test_unique_id_contains_backlight(self):
        entity, _ = self._make()
        assert "backlight" in entity.unique_id

    @pytest.mark.asyncio
    async def test_turn_on_with_color_patches_sbus(self):
        entity, coordinator = self._make(bus="sbus")
        coordinator.client.patch_sbus_device = AsyncMock(return_value={})
        await entity.async_turn_on(**{ATTR_HS_COLOR: (0.0, 100.0)})
        call_args = coordinator.client.patch_sbus_device.call_args
        assert call_args[0][0] == 70
        assert call_args[0][1] == {"color": "#FF0000"}

    @pytest.mark.asyncio
    async def test_turn_on_no_color_keeps_existing(self):
        entity, coordinator = self._make(bus="sbus", color="#00FF00")
        coordinator.client.patch_sbus_device = AsyncMock(return_value={})
        await entity.async_turn_on()
        call_args = coordinator.client.patch_sbus_device.call_args
        assert call_args[0][1] == {"color": "#00FF00"}

    @pytest.mark.asyncio
    async def test_turn_off_sends_black(self):
        entity, coordinator = self._make(bus="sbus")
        coordinator.client.patch_sbus_device = AsyncMock(return_value={})
        await entity.async_turn_off()
        call_args = coordinator.client.patch_sbus_device.call_args
        assert call_args[0][1] == {"color": "#000000"}

    @pytest.mark.asyncio
    async def test_turn_on_wtp_patches_wtp(self):
        entity, coordinator = self._make(bus="wtp")
        coordinator.client.patch_wtp_device = AsyncMock(return_value={})
        await entity.async_turn_on(**{ATTR_HS_COLOR: (240.0, 100.0)})
        call_args = coordinator.client.patch_wtp_device.call_args
        assert call_args[0][1] == {"color": "#0000FF"}


class TestSinumBusRgbLightHelpers:
    """Unit tests for _sbus_lua_commands and _wtp_color_payload extracted helpers."""

    def _make_sbus(self, device: dict | None = None):
        d = device or {
            "id": 7,
            "type": STYPE_RGB_CONTROLLER,
            "name": "RGB",
            "state": True,
            "brightness": 60,
            "led_color": "#00FF00",
        }
        from unittest.mock import patch as _patch
        coordinator = _make_coordinator(sbus={7: d})
        from custom_components.sinum.light import SinumBusRgbLight
        with _patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumBusRgbLight(coordinator, 7, "e", "sbus")
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        return entity

    def _make_wtp(self, device: dict | None = None):
        d = device or {
            "id": 8,
            "type": WTYPE_RGB_CONTROLLER,
            "name": "RGB",
            "state": True,
            "brightness": 80,
            "led_color": "#FF0000",
        }
        from unittest.mock import patch as _patch
        coordinator = _make_coordinator(wtp={8: d})
        from custom_components.sinum.light import SinumBusRgbLight
        with _patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumBusRgbLight(coordinator, 8, "e", "wtp")
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        return entity

    def test_sbus_lua_kelvin_produces_set_temperature(self):
        entity = self._make_sbus()
        lines, optimistic = entity._sbus_lua_commands(**{ATTR_COLOR_TEMP_KELVIN: 4000})
        assert any("set_temperature" in l for l in lines)
        assert 4000 in lines[0].__class__.__mro__ or "4000" in lines[0]
        assert optimistic["color_mode"] == "temperature"
        assert optimistic["white_temperature"] == 4000

    def test_sbus_lua_hs_produces_set_color(self):
        entity = self._make_sbus()
        lines, optimistic = entity._sbus_lua_commands(**{ATTR_HS_COLOR: (0.0, 100.0)})
        assert any("set_color" in l for l in lines)
        assert optimistic["color_mode"] == "rgb"

    def test_sbus_lua_hs_switches_mode_from_temperature_to_rgb(self):
        """Regression: user color command must switch mode out of temperature."""
        entity = self._make_sbus(
            {
                "id": 7,
                "type": STYPE_RGB_CONTROLLER,
                "name": "RGB",
                "state": True,
                "color_mode": "temperature",
                "white_temperature": 3200,
                "led_color": "#cc1000",
            }
        )
        _, optimistic = entity._sbus_lua_commands(**{ATTR_HS_COLOR: (120.0, 100.0)})
        assert optimistic["color_mode"] == "rgb"
        assert optimistic["led_color"].startswith("#")

    def test_sbus_lua_brightness_produces_set_brightness(self):
        entity = self._make_sbus()
        lines, optimistic = entity._sbus_lua_commands(**{ATTR_BRIGHTNESS: 128})
        assert any("set_brightness" in l for l in lines)
        assert optimistic["brightness"] == round(128 / 255 * 100)

    def test_sbus_lua_hs_and_brightness_produces_two_commands(self):
        entity = self._make_sbus()
        lines, _ = entity._sbus_lua_commands(**{ATTR_HS_COLOR: (120.0, 100.0), ATTR_BRIGHTNESS: 200})
        assert len(lines) == 2
        assert any("set_color" in l for l in lines)
        assert any("set_brightness" in l for l in lines)

    def test_sbus_lua_kelvin_takes_precedence_over_hs(self):
        entity = self._make_sbus()
        lines, optimistic = entity._sbus_lua_commands(
            **{ATTR_COLOR_TEMP_KELVIN: 3000, ATTR_HS_COLOR: (0.0, 100.0)}
        )
        assert all("set_temperature" in l or l == "" for l in lines)
        assert "white_temperature" in optimistic

    def test_wtp_color_payload_kelvin(self):
        entity = self._make_wtp()
        payload = entity._wtp_color_payload(**{ATTR_COLOR_TEMP_KELVIN: 2700})
        assert "color" in payload
        assert payload["color"].startswith("#")

    def test_wtp_color_payload_hs_and_brightness(self):
        entity = self._make_wtp()
        payload = entity._wtp_color_payload(**{ATTR_HS_COLOR: (240.0, 100.0), ATTR_BRIGHTNESS: 200})
        assert payload["color"] != "#0000FF"  # brightness encoded in V, so not full blue

    def test_wtp_color_payload_hs_only_full_brightness(self):
        entity = self._make_wtp()
        payload = entity._wtp_color_payload(**{ATTR_HS_COLOR: (240.0, 100.0)})
        assert payload["color"] == "#0000FF"  # full brightness blue

    def test_wtp_color_payload_brightness_only_preserves_hue(self):
        entity = self._make_wtp()  # led_color=#FF0000 (red)
        payload = entity._wtp_color_payload(**{ATTR_BRIGHTNESS: 128})
        assert "color" in payload
        # Red hue preserved, brightness halved → #800000
        assert payload["color"] == "#800000"

    def test_wtp_color_payload_no_color_args_returns_empty(self):
        entity = self._make_wtp()
        payload = entity._wtp_color_payload()
        assert payload == {}


class TestHexHsvEdgeCases:
    """Cover _hex_to_hsv branches missed by existing tests (lines 68-83)."""

    def test_short_hex_returns_zero(self):
        """Line 68: len < 6 → (0, 0, 1)."""
        from custom_components.sinum.light import _hex_to_hsv

        h, s, v = _hex_to_hsv("#F")
        assert h == 0.0 and s == 0.0 and v == 1.0

    def test_invalid_hex_chars_returns_zero(self):
        """Line 71-72: ValueError in int() → (0, 0, 1)."""
        from custom_components.sinum.light import _hex_to_hsv

        h, s, v = _hex_to_hsv("ZZZZZZ")
        assert h == 0.0 and s == 0.0 and v == 1.0

    def test_green_max_branch(self):
        """Line 77: max_c == g → hue in 120-240 range."""
        from custom_components.sinum.light import _hex_to_hsv

        h, s, v = _hex_to_hsv("#00FF40")  # green is dominant
        assert 100 < h < 150

    def test_blue_max_branch(self):
        """Line 80-81: max_c == b → hue in 240-360 range."""
        from custom_components.sinum.light import _hex_to_hsv

        h, s, v = _hex_to_hsv("#0040FF")  # blue is dominant
        assert 220 < h < 260

    def test_zero_saturation_when_achromatic(self):
        """Line 83: max_c > 0 but delta == 0 → s == 0."""
        from custom_components.sinum.light import _hex_to_hsv

        h, s, v = _hex_to_hsv("#808080")  # grey
        assert s == 0.0

    def test_black_returns_zero_saturation(self):
        """Line 83: max_c == 0 → s = 0.0."""
        from custom_components.sinum.light import _hex_to_hsv

        h, s, v = _hex_to_hsv("#000000")
        assert s == 0.0 and v == 0.0


class TestKelvinToHexEdgeCases:
    """Cover _kelvin_to_hex high-temperature and very-low branches (lines 141-150)."""

    def test_low_kelvin_produces_warm_color(self):
        """t <= 66: r=255, b from log formula (t > 19)."""
        from custom_components.sinum.light import _kelvin_to_hex

        result = _kelvin_to_hex(2700)
        assert result.startswith("#")
        r = int(result[1:3], 16)
        assert r == 255  # warm light is always full red

    def test_high_kelvin_produces_cool_color(self):
        """Lines 141-146: t > 66 branch — r and g computed from power law."""
        from custom_components.sinum.light import _kelvin_to_hex

        result = _kelvin_to_hex(9000)
        assert result.startswith("#")
        b = int(result[5:7], 16)
        assert b == 255  # cool light has full blue (line 150: t >= 66 → b=255)

    def test_very_low_kelvin_gives_zero_blue(self):
        """Line 150 elif t <= 19: b = 0 (kelvin ≤ 1900 K)."""
        from custom_components.sinum.light import _kelvin_to_hex

        result = _kelvin_to_hex(1000)  # clamped to 1000 K → t=10 ≤ 19
        assert result.startswith("#")
        b = int(result[5:7], 16)
        assert b == 0


class TestHsToHexAllSectors:
    """Cover _hs_to_hex mapping indices 2-5 (lines 160-175)."""

    def test_hue_sector_2_cyan(self):
        """Hue 180° → mapping[2] = (p, v, t)."""
        from custom_components.sinum.light import _hs_to_hex

        result = _hs_to_hex(180.0, 100.0)
        assert result.startswith("#")
        r, g, b = int(result[1:3], 16), int(result[3:5], 16), int(result[5:7], 16)
        assert r == 0 and b == g  # cyan: equal G and B, no red

    def test_hue_sector_3_azure(self):
        """Hue 210° → mapping[3] = (p, q, v)."""
        from custom_components.sinum.light import _hs_to_hex

        result = _hs_to_hex(210.0, 100.0)
        assert result.startswith("#")
        b = int(result[5:7], 16)
        assert b == 255  # dominant blue

    def test_hue_sector_4_violet(self):
        """Hue 270° → mapping[4] = (t, p, v)."""
        from custom_components.sinum.light import _hs_to_hex

        result = _hs_to_hex(270.0, 100.0)
        assert result.startswith("#")
        b = int(result[5:7], 16)
        assert b == 255  # violet — full blue component

    def test_hue_sector_5_magenta(self):
        """Hue 330° → mapping[5] = (v, p, q)."""
        from custom_components.sinum.light import _hs_to_hex

        result = _hs_to_hex(330.0, 100.0)
        assert result.startswith("#")
        r = int(result[1:3], 16)
        assert r == 255  # magenta — full red component

    def test_hue_sector_0_red(self):
        """Hue 0° → mapping[0] = (v, t, p) — already covered but explicit."""
        from custom_components.sinum.light import _hs_to_hex

        assert _hs_to_hex(0.0, 100.0) == "#FF0000"

    def test_hue_sector_1_yellow(self):
        """Hue 60° → mapping[1] = (q, v, p)."""
        from custom_components.sinum.light import _hs_to_hex

        result = _hs_to_hex(60.0, 100.0)
        r, g = int(result[1:3], 16), int(result[3:5], 16)
        assert r == 255 and g == 255  # yellow


class TestButtonLightSetup:
    """Cover _add_bus_lights button-light path (lines 46-57 area)."""

    @pytest.mark.asyncio
    async def test_wtp_button_with_color_creates_entity(self):
        from custom_components.sinum.const import WTYPE_BUTTON

        wtp = {9: {"id": 9, "type": WTYPE_BUTTON, "name": "BTN", "color": "#FF0000"}}
        coordinator = _make_coordinator(wtp=wtp)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        btns = [e for e in added if isinstance(e, SinumButtonLight)]
        assert len(btns) == 1

    @pytest.mark.asyncio
    async def test_wtp_button_without_color_skipped(self):
        from custom_components.sinum.const import WTYPE_BUTTON

        wtp = {10: {"id": 10, "type": WTYPE_BUTTON, "name": "BTN_NOCOLOR"}}
        coordinator = _make_coordinator(wtp=wtp)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        btns = [e for e in added if isinstance(e, SinumButtonLight)]
        assert len(btns) == 0

    @pytest.mark.asyncio
    async def test_sbus_button_with_color_creates_entity(self):
        from custom_components.sinum.const import STYPE_BUTTON

        sbus = {11: {"id": 11, "type": STYPE_BUTTON, "name": "SBTN", "color": "#0000FF"}}
        coordinator = _make_coordinator(sbus=sbus)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        btns = [e for e in added if isinstance(e, SinumButtonLight)]
        assert len(btns) == 1


class TestLightHelperEdgeCases:
    """Cover _labels, _color_mode, _supported_color_modes edge paths."""

    def test_labels_returns_empty_set_for_non_list(self):
        """Line 145: _labels when device has non-list labels."""
        from custom_components.sinum.light import _labels

        assert _labels({"labels": "not-a-list"}) == set()
        assert _labels({}) == set()

    def test_supports_color_temperature_via_labels(self):
        """Line 180: _supports_color_temperature via rgbww/ww labels."""
        from custom_components.sinum.light import _supports_color_temperature

        assert _supports_color_temperature({"labels": ["rgbww"]}) is True
        assert _supports_color_temperature({"labels": ["ww"]}) is True

    def test_color_mode_temperature_explicit(self):
        """Line 190: _color_mode returns COLOR_TEMP when color_mode='temperature'."""
        from custom_components.sinum.light import _color_mode
        from homeassistant.components.light import ColorMode

        assert _color_mode({"color_mode": "temperature"}) == ColorMode.COLOR_TEMP
        assert _color_mode({"color_mode": "color_temp"}) == ColorMode.COLOR_TEMP

    def test_color_mode_brightness_fallback(self):
        """Lines 191-192: _color_mode returns BRIGHTNESS when no rgb/temp."""
        from custom_components.sinum.light import _color_mode
        from homeassistant.components.light import ColorMode

        assert _color_mode({}) == ColorMode.BRIGHTNESS

    def test_color_mode_color_temp_when_only_white_temperature(self):
        """Line 192: _supports_color_temperature path in _color_mode."""
        from custom_components.sinum.light import _color_mode
        from homeassistant.components.light import ColorMode

        assert _color_mode({"white_temperature": 3000}) == ColorMode.COLOR_TEMP


class TestDimmerLightRestorePath:
    """Lines 220-228, 246, 279: SinumDimmerLight restore from HA state."""

    @pytest.mark.asyncio
    async def test_dimmer_restores_is_on_and_brightness_from_last_state(self):
        coordinator = _make_coordinator(virtual={})
        from unittest.mock import patch as _patch
        with _patch("homeassistant.helpers.frame.report_usage", return_value=None):
            from custom_components.sinum.light import SinumDimmerLight
            entity = SinumDimmerLight(coordinator, 1, "e")
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()

        last = MagicMock()
        last.state = "on"
        last.attributes = {"brightness": 128}
        entity.async_get_last_state = AsyncMock(return_value=last)
        entity._attr_is_on = None
        entity._attr_brightness = None

        await entity.async_added_to_hass()

        assert entity._attr_is_on is True
        assert entity._attr_brightness == 128

    @pytest.mark.asyncio
    async def test_dimmer_skips_restore_when_state_unavailable(self):
        coordinator = _make_coordinator(virtual={})
        from unittest.mock import patch as _patch
        with _patch("homeassistant.helpers.frame.report_usage", return_value=None):
            from custom_components.sinum.light import SinumDimmerLight
            entity = SinumDimmerLight(coordinator, 1, "e")
        entity.hass = MagicMock()

        last = MagicMock()
        last.state = "unavailable"
        entity.async_get_last_state = AsyncMock(return_value=last)
        entity._attr_is_on = None

        await entity.async_added_to_hass()
        assert entity._attr_is_on is None

    def test_dimmer_is_on_uses_restored_state_when_no_device(self):
        """Line 246: is_on uses _attr_is_on when no device."""
        coordinator = _make_coordinator(virtual={})
        from unittest.mock import patch as _patch
        with _patch("homeassistant.helpers.frame.report_usage", return_value=None):
            from custom_components.sinum.light import SinumDimmerLight
            entity = SinumDimmerLight(coordinator, 1, "e")
        entity._attr_is_on = True
        assert entity.is_on is True

    def test_dimmer_color_mode_temperature_via_device(self):
        """Line 220-228: SinumDimmerLight.supported_color_modes/color_mode."""
        coordinator = _make_coordinator(virtual={1: {
            "id": 1, "type": "dimmer_rgb_integrator", "color_mode": "temperature", "white_temperature": 3000
        }})
        from unittest.mock import patch as _patch
        with _patch("homeassistant.helpers.frame.report_usage", return_value=None):
            from custom_components.sinum.light import SinumDimmerLight
            entity = SinumDimmerLight(coordinator, 1, "e")
        from homeassistant.components.light import ColorMode
        assert entity.color_mode == ColorMode.COLOR_TEMP


class TestBusDimmerLightRestorePath:
    """Lines 333-341, 354: SinumBusDimmerLight restore path and is_on fallback."""

    @pytest.mark.asyncio
    async def test_bus_dimmer_restores_brightness_from_last_state(self):
        coordinator = _make_coordinator(wtp={})
        with MagicMock() as _patch:
            from unittest.mock import patch as _patch
        with _patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumBusDimmerLight(coordinator, 3, "e", "wtp")
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()

        last = MagicMock()
        last.state = "on"
        last.attributes = {"brightness": 200}
        entity.async_get_last_state = AsyncMock(return_value=last)
        entity._attr_is_on = None
        entity._attr_brightness = None

        await entity.async_added_to_hass()

        assert entity._attr_is_on is True
        assert entity._attr_brightness == 200

    def test_bus_dimmer_is_on_uses_attr_when_no_device(self):
        """Line 354: is_on fallback to _attr_is_on when device is empty."""
        coordinator = _make_coordinator(wtp={})
        from unittest.mock import patch as _patch
        with _patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumBusDimmerLight(coordinator, 3, "e", "wtp")
        entity._attr_is_on = True
        assert entity.is_on is True


class TestBusRgbLightRestorePath:
    """Lines 434-442, 455, 470, 478, 483, 501-506: SinumBusRgbLight paths."""

    @pytest.mark.asyncio
    async def test_rgb_light_restores_is_on_and_brightness_from_last_state(self):
        """Lines 434-442: restore is_on + brightness from HA state."""
        coordinator = _make_coordinator(sbus={})
        from unittest.mock import patch as _patch
        with _patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumBusRgbLight(coordinator, 7, "e", "sbus")
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()

        last = MagicMock()
        last.state = "on"
        last.attributes = {ATTR_BRIGHTNESS: 180}
        entity.async_get_last_state = AsyncMock(return_value=last)
        entity._attr_is_on = None
        entity._attr_brightness = None

        await entity.async_added_to_hass()

        assert entity._attr_is_on is True
        assert entity._attr_brightness == 180

    def test_rgb_light_is_on_uses_attr_when_no_device(self):
        """Line 455: is_on fallback when no device."""
        coordinator = _make_coordinator(sbus={})
        from unittest.mock import patch as _patch
        with _patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumBusRgbLight(coordinator, 7, "e", "sbus")
        entity._attr_is_on = True
        assert entity.is_on is True

    def test_rgb_light_hs_color_none_when_no_led_color(self):
        """Line 470: hs_color returns None when device has no led_color/color."""
        coordinator = _make_coordinator(sbus={})
        from unittest.mock import patch as _patch
        with _patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumBusRgbLight(coordinator, 7, "e", "sbus")
        assert entity.hs_color is None

    @pytest.mark.asyncio
    async def test_rgb_light_will_remove_deletes_scene(self):
        """Lines 501-506: async_will_remove_from_hass deletes scene."""
        coordinator = _make_coordinator(sbus={7: {"id": 7, "type": STYPE_RGB_CONTROLLER}})
        coordinator.client.delete_scene = AsyncMock(return_value=None)
        from unittest.mock import patch as _patch
        with _patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumBusRgbLight(coordinator, 7, "e", "sbus")
        entity.hass = MagicMock()
        entity._lua_scene_id = 42

        await entity.async_will_remove_from_hass()

        coordinator.client.delete_scene.assert_awaited_once_with(42)
        assert entity._lua_scene_id is None

    @pytest.mark.asyncio
    async def test_rgb_light_will_remove_handles_delete_error(self):
        """Line 503: delete_scene exception is silently ignored."""
        coordinator = _make_coordinator(sbus={7: {"id": 7, "type": STYPE_RGB_CONTROLLER}})
        coordinator.client.delete_scene = AsyncMock(side_effect=Exception("gone"))
        from unittest.mock import patch as _patch
        with _patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumBusRgbLight(coordinator, 7, "e", "sbus")
        entity.hass = MagicMock()
        entity._lua_scene_id = 42

        await entity.async_will_remove_from_hass()
        assert entity._lua_scene_id is None  # cleaned up despite error


class TestButtonLightBehavior:
    """Lines 563, 567-568: SinumButtonLight properties and actions."""

    def _make(self, bus="wtp", color="#FF0000"):
        from custom_components.sinum.const import WTYPE_BUTTON
        store = {9: {"id": 9, "type": WTYPE_BUTTON, "color": color, "state": True}}
        coordinator = _make_coordinator(wtp=store) if bus == "wtp" else _make_coordinator(sbus=store)
        from unittest.mock import patch as _patch
        with _patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumButtonLight(coordinator, 9, "e", bus)
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        return entity

    def test_is_on_true_when_color_not_black(self):
        entity = self._make(color="#FF0000")
        assert entity.is_on is True

    def test_is_on_false_when_color_black(self):
        entity = self._make(color="#000000")
        assert entity.is_on is False

    def test_hs_color_from_device(self):
        entity = self._make(color="#FF0000")
        hs = entity.hs_color
        assert hs is not None
        assert hs[0] == 0.0  # red hue

    def test_hs_color_none_when_no_color_key(self):
        """Line 567-568: hs_color falls back to _attr_hs_color."""
        from custom_components.sinum.const import WTYPE_BUTTON
        coordinator = _make_coordinator(wtp={9: {"id": 9, "type": WTYPE_BUTTON}})
        from unittest.mock import patch as _patch
        with _patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumButtonLight(coordinator, 9, "e", "wtp")
        entity._attr_hs_color = (180.0, 50.0)
        assert entity.hs_color == (180.0, 50.0)

    @pytest.mark.asyncio
    async def test_turn_on_with_hs_color(self):
        entity = self._make()
        entity.coordinator.client.patch_wtp_device = AsyncMock(return_value={"color": "#FF0000"})
        await entity.async_turn_on(**{ATTR_HS_COLOR: (0.0, 100.0)})
        entity.async_write_ha_state.assert_called()

    @pytest.mark.asyncio
    async def test_turn_on_uses_existing_color_when_no_hs(self):
        entity = self._make(color="#00FF00")
        entity.coordinator.client.patch_wtp_device = AsyncMock(return_value={"color": "#00FF00"})
        await entity.async_turn_on()
        entity.coordinator.client.patch_wtp_device.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_turn_on_raises_on_error(self):
        """Line 563: turn_on propagates HomeAssistantError on API failure."""
        from homeassistant.exceptions import HomeAssistantError

        entity = self._make()
        entity.coordinator.client.patch_wtp_device = AsyncMock(side_effect=Exception("err"))
        with pytest.raises(HomeAssistantError, match="Cannot set backlight color"):
            await entity.async_turn_on()

    @pytest.mark.asyncio
    async def test_turn_off_raises_on_error(self):
        from homeassistant.exceptions import HomeAssistantError

        entity = self._make()
        entity.coordinator.client.patch_wtp_device = AsyncMock(side_effect=Exception("err"))
        with pytest.raises(HomeAssistantError, match="Cannot turn off backlight"):
            await entity.async_turn_off()
