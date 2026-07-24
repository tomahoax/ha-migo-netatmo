"""Tests for MiGo (Netatmo) entities."""

from __future__ import annotations

from unittest.mock import create_autospec

import pytest
from homeassistant.components.climate import PRESET_AWAY, PRESET_BOOST, HVACAction, HVACMode
from homeassistant.exceptions import HomeAssistantError

from custom_components.migo_netatmo.api import MigoApi, MigoApiError, MigoAuthError
from custom_components.migo_netatmo.climate import (
    HVAC_TO_MIGO_MODE,
    MIGO_TO_HVAC_MODE,
    PRESET_FROST_GUARD,
    PRESET_TO_MIGO_MODE,
    MigoClimate,
)
from custom_components.migo_netatmo.const import (
    DEFAULT_BOOST_DURATION,
    DEFAULT_MANUAL_SETPOINT_DURATION,
    MODE_AWAY,
    MODE_FROST_GUARD,
    MODE_MANUAL,
    MODE_SCHEDULE,
    TEMP_MAX,
)

# mock_coordinator fixture lives in conftest.py, shared across test modules.


class TestMigoClimate:
    """Tests for the climate entity."""

    @pytest.fixture
    def climate(self, mock_coordinator):
        """Create a climate entity for testing.

        The API mock is autospecced so kwargs unknown to the real
        MigoApi signatures raise TypeError (regression guard for #13).
        """
        api = create_autospec(MigoApi, instance=True)
        api.set_temperature.return_value = {"status": "ok"}
        api.set_mode.return_value = {"status": "ok"}
        return MigoClimate(mock_coordinator, "room_456", api)

    def test_current_temperature(self, climate):
        """Test current temperature property."""
        assert climate.current_temperature == 21.5

    def test_target_temperature(self, climate):
        """Test target temperature property."""
        assert climate.target_temperature == 20.0

    def test_hvac_mode_schedule(self, climate):
        """Test HVAC mode in schedule mode."""
        assert climate.hvac_mode == HVACMode.AUTO

    def test_hvac_mode_manual(self, climate, mock_coordinator):
        """Test HVAC mode in manual mode."""
        mock_coordinator.rooms["room_456"]["therm_setpoint_mode"] = MODE_MANUAL
        assert climate.hvac_mode == HVACMode.HEAT

    def test_hvac_mode_frost_guard(self, climate, mock_coordinator):
        """Test HVAC mode in frost guard mode."""
        mock_coordinator.rooms["room_456"]["therm_setpoint_mode"] = MODE_FROST_GUARD
        assert climate.hvac_mode == HVACMode.OFF

    def test_hvac_action_heating(self, climate, mock_coordinator):
        """Test HVAC action when heating."""
        mock_coordinator.rooms["room_456"]["therm_measured_temperature"] = 18.0
        mock_coordinator.rooms["room_456"]["therm_setpoint_temperature"] = 20.0
        assert climate.hvac_action == HVACAction.HEATING

    def test_hvac_action_idle(self, climate, mock_coordinator):
        """Test HVAC action when idle."""
        mock_coordinator.rooms["room_456"]["therm_measured_temperature"] = 20.5
        mock_coordinator.rooms["room_456"]["therm_setpoint_temperature"] = 20.0
        assert climate.hvac_action == HVACAction.IDLE

    def test_hvac_action_off(self, climate, mock_coordinator):
        """Test HVAC action when off."""
        mock_coordinator.rooms["room_456"]["therm_setpoint_mode"] = MODE_FROST_GUARD
        assert climate.hvac_action == HVACAction.OFF

    def test_preset_mode_none(self, climate):
        """Test preset mode when in schedule."""
        assert climate.preset_mode is None

    def test_preset_mode_away(self, climate, mock_coordinator):
        """Test preset mode when away."""
        mock_coordinator.rooms["room_456"]["therm_setpoint_mode"] = MODE_AWAY
        assert climate.preset_mode == "away"

    @pytest.mark.asyncio
    async def test_set_temperature(self, climate):
        """Test setting temperature."""
        await climate.async_set_temperature(temperature=22.0)

        climate._api.set_temperature.assert_called_once()
        climate.coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_hvac_mode_heat(self, climate, mock_coordinator):
        """Test setting HVAC mode to heat uses set_temperature with duration."""
        # Add home data with custom duration
        mock_coordinator.homes["home_123"]["therm_setpoint_default_duration"] = 120

        await climate.async_set_hvac_mode(HVACMode.HEAT)

        # Heat mode should call set_temperature (not set_mode)
        climate._api.set_temperature.assert_called_once()
        call_kwargs = climate._api.set_temperature.call_args.kwargs
        assert call_kwargs["temperature"] == 20.0  # Current target temperature
        assert call_kwargs["duration"] == 120  # From home settings

    @pytest.mark.asyncio
    async def test_set_hvac_mode_heat_default_duration(self, climate):
        """Test setting HVAC mode to heat uses default duration when not configured."""
        await climate.async_set_hvac_mode(HVACMode.HEAT)

        climate._api.set_temperature.assert_called_once()
        call_kwargs = climate._api.set_temperature.call_args.kwargs
        assert call_kwargs["duration"] == DEFAULT_MANUAL_SETPOINT_DURATION

    @pytest.mark.asyncio
    async def test_set_hvac_mode_auto(self, climate):
        """Test setting HVAC mode to auto uses set_mode."""
        await climate.async_set_hvac_mode(HVACMode.AUTO)

        climate._api.set_mode.assert_called_once()
        call_kwargs = climate._api.set_mode.call_args.kwargs
        assert call_kwargs["mode"] == MODE_SCHEDULE

    @pytest.mark.asyncio
    async def test_set_hvac_mode_off(self, climate):
        """Test setting HVAC mode to off uses set_mode with frost guard."""
        await climate.async_set_hvac_mode(HVACMode.OFF)

        climate._api.set_mode.assert_called_once()
        call_kwargs = climate._api.set_mode.call_args.kwargs
        assert call_kwargs["mode"] == MODE_FROST_GUARD

    @pytest.mark.asyncio
    async def test_set_preset_mode_away(self, climate):
        """Test setting preset mode to away."""
        await climate.async_set_preset_mode(PRESET_AWAY)

        climate._api.set_mode.assert_called_once()
        call_kwargs = climate._api.set_mode.call_args.kwargs
        assert call_kwargs["mode"] == MODE_AWAY

    @pytest.mark.asyncio
    async def test_set_preset_mode_frost_guard(self, climate):
        """Test setting preset mode to frost guard."""
        await climate.async_set_preset_mode(PRESET_FROST_GUARD)

        climate._api.set_mode.assert_called_once()
        call_kwargs = climate._api.set_mode.call_args.kwargs
        assert call_kwargs["mode"] == MODE_FROST_GUARD

    @pytest.mark.asyncio
    async def test_set_preset_mode_boost(self, climate):
        """Test setting preset mode to boost."""
        await climate.async_set_preset_mode(PRESET_BOOST)

        # Boost uses set_temperature with max temp and 1 hour duration
        climate._api.set_temperature.assert_called_once()
        call_kwargs = climate._api.set_temperature.call_args.kwargs
        assert call_kwargs["temperature"] == TEMP_MAX
        assert call_kwargs["duration"] == DEFAULT_BOOST_DURATION

    def test_preset_mode_boost_detected(self, climate, mock_coordinator):
        """Test that boost preset is detected when manual at max temp."""
        mock_coordinator.rooms["room_456"]["therm_setpoint_mode"] = MODE_MANUAL
        mock_coordinator.rooms["room_456"]["therm_setpoint_temperature"] = TEMP_MAX
        assert climate.preset_mode == PRESET_BOOST

    def test_preset_mode_manual_not_boost(self, climate, mock_coordinator):
        """Test that manual mode at lower temp is not detected as boost."""
        mock_coordinator.rooms["room_456"]["therm_setpoint_mode"] = MODE_MANUAL
        mock_coordinator.rooms["room_456"]["therm_setpoint_temperature"] = 22.0
        assert climate.preset_mode is None

    def test_unique_id(self, climate):
        """Test unique ID generation."""
        assert climate.unique_id == "migo_netatmo_climate_room_456"


class TestModeMapping:
    """Tests for mode mapping."""

    def test_migo_to_hvac_mode(self):
        """Test MiGO to HVAC mode mapping."""
        assert MIGO_TO_HVAC_MODE[MODE_SCHEDULE] == HVACMode.AUTO
        assert MIGO_TO_HVAC_MODE[MODE_MANUAL] == HVACMode.HEAT
        assert MIGO_TO_HVAC_MODE[MODE_FROST_GUARD] == HVACMode.OFF
        assert MIGO_TO_HVAC_MODE[MODE_AWAY] == HVACMode.AUTO

    def test_hvac_to_migo_mode(self):
        """Test HVAC to MiGO mode mapping."""
        assert HVAC_TO_MIGO_MODE[HVACMode.AUTO] == MODE_SCHEDULE
        assert HVAC_TO_MIGO_MODE[HVACMode.HEAT] == MODE_MANUAL
        assert HVAC_TO_MIGO_MODE[HVACMode.OFF] == MODE_FROST_GUARD

    def test_preset_to_migo_mode(self):
        """Test preset to MiGO mode mapping."""
        assert PRESET_TO_MIGO_MODE[PRESET_AWAY] == MODE_AWAY
        assert PRESET_TO_MIGO_MODE[PRESET_FROST_GUARD] == MODE_FROST_GUARD
        # Note: PRESET_BOOST is handled separately (not in mapping)


class TestClimateErrorSurfacing:
    """Tests for API errors surfacing as UI-visible exceptions."""

    @pytest.fixture
    def climate(self, mock_coordinator):
        """Create a climate entity with an autospecced API mock."""
        api = create_autospec(MigoApi, instance=True)
        api.set_temperature.return_value = {"status": "ok"}
        api.set_mode.return_value = {"status": "ok"}
        return MigoClimate(mock_coordinator, "room_456", api)

    @pytest.mark.asyncio
    async def test_api_error_raises_home_assistant_error(self, climate):
        """Test a generic API failure raises a translated HomeAssistantError."""
        climate._api.set_temperature.side_effect = MigoApiError("boom")

        with pytest.raises(HomeAssistantError) as exc_info:
            await climate.async_set_temperature(temperature=21.0)

        assert exc_info.value.translation_key == "api_error"
        # No refresh on failure
        climate.coordinator.async_request_refresh.assert_not_called()

    @pytest.mark.asyncio
    async def test_auth_error_raises_home_assistant_error(self, climate):
        """Test an auth failure raises a translated HomeAssistantError."""
        climate._api.set_mode.side_effect = MigoAuthError("expired")

        with pytest.raises(HomeAssistantError) as exc_info:
            await climate.async_set_hvac_mode(HVACMode.AUTO)

        assert exc_info.value.translation_key == "auth_failed"

    @pytest.mark.asyncio
    async def test_missing_home_id_raises(self, climate, mock_coordinator):
        """Test a room without home_id raises instead of silently returning."""
        del mock_coordinator.rooms["room_456"]["home_id"]

        with pytest.raises(HomeAssistantError) as exc_info:
            await climate.async_set_temperature(temperature=21.0)

        assert exc_info.value.translation_key == "missing_home_id"
        climate._api.set_temperature.assert_not_called()
