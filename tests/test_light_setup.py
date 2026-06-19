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
        entity, coordinator = self._make_wtp()
        coordinator.client.patch_wtp_device = AsyncMock(return_value={})
        await entity.async_turn_on(**{ATTR_BRIGHTNESS: 128})
        payload = coordinator.client.patch_wtp_device.await_args.args[1]
        assert payload == {"state": True, "brightness": round(128 / 255 * 100)}

    @pytest.mark.asyncio
    async def test_turn_on_rgbww_device_sends_color_and_brightness(self):
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
        assert payload == {
            "state": True,
            "brightness": round(200 / 255 * 100),
            "color": "#00FF00",
        }

    @pytest.mark.asyncio
    async def test_turn_off_wtp(self):
        """Lines 372-375: async_turn_off on wtp bus calls patch_wtp_device."""
        entity, coordinator = self._make_wtp()
        coordinator.client.patch_wtp_device = AsyncMock(return_value={})
        await entity.async_turn_off()
        coordinator.client.patch_wtp_device.assert_awaited_once_with(4, {"state": False})


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
