"""Tests for MiGo (Netatmo) entities."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.climate import HVACAction, HVACMode

from custom_components.migo_netatmo.climate import (
    HVAC_TO_MIGO_MODE,
    MIGO_TO_HVAC_MODE,
    PRESET_TO_MIGO_MODE,
    MigoClimate,
)
from custom_components.migo_netatmo.const import (
    MODE_AWAY,
    MODE_FROST_GUARD,
    MODE_MANUAL,
    MODE_SCHEDULE,
)


@pytest.fixture
def mock_coordinator(homes_data_response, home_status_response):
    """Create a mock coordinator with data."""
    coordinator = MagicMock()
    coordinator.rooms = {
        "room_456": {
            "id": "room_456",
            "name": "Living Room",
            "home_id": "home_123",
            "home_name": "My Home",
            "therm_measured_temperature": 21.5,
            "therm_setpoint_temperature": 20.0,
            "therm_setpoint_mode": "schedule",
            "reachable": True,
            "anticipating": False,
        }
    }
    coordinator.devices = {
        "gateway_001": {
            "id": "gateway_001",
            "type": "NAVaillant",
            "home_id": "home_123",
            "wifi_strength": 70,
            "dhw_enabled": True,
        },
        "module_789": {
            "id": "module_789",
            "type": "NAThermVaillant",
            "home_id": "home_123",
            "battery_percent": 85,
            "boiler_status": True,
        },
    }
    coordinator.homes = {
        "home_123": {
            "id": "home_123",
            "name": "My Home",
            "therm_mode": "schedule",
        }
    }
    coordinator.get_cached_value = MagicMock(return_value=None)
    coordinator.set_cached_value = MagicMock()
    coordinator.async_request_refresh = AsyncMock()
    return coordinator


class TestMigoClimate:
    """Tests for the climate entity."""

    @pytest.fixture
    def climate(self, mock_coordinator):
        """Create a climate entity for testing."""
        api = MagicMock()
        api.set_temperature = AsyncMock(return_value={"status": "ok"})
        api.set_mode = AsyncMock(return_value={"status": "ok"})
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
    async def test_set_hvac_mode(self, climate):
        """Test setting HVAC mode."""
        await climate.async_set_hvac_mode(HVACMode.HEAT)

        climate._api.set_mode.assert_called_once()
        call_kwargs = climate._api.set_mode.call_args.kwargs
        assert call_kwargs["mode"] == MODE_MANUAL

    @pytest.mark.asyncio
    async def test_set_preset_mode(self, climate):
        """Test setting preset mode."""
        await climate.async_set_preset_mode("away")

        climate._api.set_mode.assert_called_once()
        call_kwargs = climate._api.set_mode.call_args.kwargs
        assert call_kwargs["mode"] == MODE_AWAY

    def test_unique_id(self, climate):
        """Test unique ID generation."""
        assert climate.unique_id == "migo_netatmo_climate_room_456"

    def test_translation_placeholders(self, climate):
        """Test translation placeholders."""
        placeholders = climate.translation_placeholders
        assert placeholders["room_name"] == "Living Room"


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
        assert PRESET_TO_MIGO_MODE["away"] == MODE_AWAY
        assert PRESET_TO_MIGO_MODE["frost_guard"] == MODE_FROST_GUARD
