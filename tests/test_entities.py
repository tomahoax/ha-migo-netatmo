"""Tests for MiGo (Netatmo) entities."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, create_autospec

import pytest
from homeassistant.components.climate import PRESET_AWAY, PRESET_BOOST, HVACAction, HVACMode

from custom_components.migo_netatmo.api import MigoApi
from custom_components.migo_netatmo.binary_sensor import (
    MigoAwayModeBinarySensor,
    MigoDHWScheduleBinarySensor,
)
from custom_components.migo_netatmo.climate import (
    HVAC_TO_MIGO_MODE,
    MIGO_TO_HVAC_MODE,
    PRESET_DHW_ONLY,
    PRESET_FROST_GUARD,
    PRESET_TO_MIGO_MODE,
    MigoClimate,
)
from custom_components.migo_netatmo.const import (
    BOILER_MODE_DHW_ONLY,
    BOILER_MODE_FROST_GUARD,
    BOILER_MODE_NORMAL,
    DEFAULT_BOOST_DURATION,
    DEFAULT_MANUAL_SETPOINT_DURATION,
    MODE_AWAY,
    MODE_FROST_GUARD,
    MODE_HOME,
    MODE_MANUAL,
    MODE_SCHEDULE,
    TEMP_MAX,
)
from custom_components.migo_netatmo.sensor import MigoBoilerModeSensor
from custom_components.migo_netatmo.switch import MigoAwayModeSwitch


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

    # -------------------------------------------------------------------
    # Forum feedback regression tests: MiGo stacks a home-level therm_mode
    # (boiler quick-action / Away) on top of the room's therm_setpoint_mode.
    # These mirror the 5 real-world states dumped on the forum.
    # -------------------------------------------------------------------

    def test_state_normal(self, climate, mock_coordinator):
        """State 1 - Normal: room mode 'home', home therm_mode 'schedule'."""
        mock_coordinator.rooms["room_456"]["therm_setpoint_mode"] = MODE_HOME
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_SCHEDULE
        assert climate.hvac_mode == HVACMode.AUTO
        assert climate.preset_mode is None

    def test_state_away(self, climate, mock_coordinator):
        """State 2 - Away: room mode 'home', home therm_mode 'away'.

        This is the originally reported bug: the Away preset never showed up
        anywhere because only the room's therm_setpoint_mode was read.
        """
        mock_coordinator.rooms["room_456"]["therm_setpoint_mode"] = MODE_HOME
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_AWAY
        assert climate.hvac_mode == HVACMode.AUTO
        assert climate.preset_mode == PRESET_AWAY

    def test_state_dhw_only(self, climate, mock_coordinator):
        """State 3 - DHW only: room mode 'hg', home therm_mode 'schedule'."""
        mock_coordinator.rooms["room_456"]["therm_setpoint_mode"] = MODE_FROST_GUARD
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_SCHEDULE
        assert climate.hvac_mode == HVACMode.OFF
        assert climate.preset_mode == PRESET_DHW_ONLY

    def test_state_dhw_only_plus_away(self, climate, mock_coordinator):
        """State 4 - DHW only + Away: therm_mode becomes 'away' (per the forum's own correction).

        Away wins in the single-value climate preset; the orthogonal DHW-only
        boiler mode is still visible separately via MigoBoilerModeSensor.
        """
        mock_coordinator.rooms["room_456"]["therm_setpoint_mode"] = MODE_FROST_GUARD
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_AWAY
        assert climate.hvac_mode == HVACMode.OFF
        assert climate.preset_mode == PRESET_AWAY

    def test_state_frost_guard_standby(self, climate, mock_coordinator):
        """State 5 - Veille (standby): room mode 'home', home therm_mode 'hg'.

        This is the display bug: room mode 'home' used to map to HVACMode.HEAT,
        showing "Heating" while the boiler was actually stopped.
        """
        mock_coordinator.rooms["room_456"]["therm_setpoint_mode"] = MODE_HOME
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_FROST_GUARD
        assert climate.hvac_mode == HVACMode.OFF
        assert climate.preset_mode == PRESET_FROST_GUARD
        assert climate.hvac_action == HVACAction.OFF

    @pytest.mark.asyncio
    async def test_set_preset_mode_dhw_only_is_rejected(self, climate):
        """DHW only is read-only: setting it must not call any API method."""
        await climate.async_set_preset_mode(PRESET_DHW_ONLY)

        climate._api.set_mode.assert_not_called()
        climate._api.set_temperature.assert_not_called()

    def test_hvac_action_uses_real_boiler_status_when_available(self, climate, mock_coordinator):
        """boiler_status from the thermostat device takes priority over the temperature heuristic."""
        mock_coordinator.rooms["room_456"]["module_ids"] = ["module_789"]
        mock_coordinator.devices["module_789"]["boiler_status"] = True
        # Temperatures alone would read as idle (current > target).
        mock_coordinator.rooms["room_456"]["therm_measured_temperature"] = 22.0
        mock_coordinator.rooms["room_456"]["therm_setpoint_temperature"] = 20.0
        assert climate.hvac_action == HVACAction.HEATING

    def test_hvac_action_boiler_status_idle(self, climate, mock_coordinator):
        """boiler_status=False reports idle even if temperatures would suggest heating."""
        mock_coordinator.rooms["room_456"]["module_ids"] = ["module_789"]
        mock_coordinator.devices["module_789"]["boiler_status"] = False
        mock_coordinator.rooms["room_456"]["therm_measured_temperature"] = 15.0
        mock_coordinator.rooms["room_456"]["therm_setpoint_temperature"] = 20.0
        assert climate.hvac_action == HVACAction.IDLE

    def test_hvac_action_falls_back_when_boiler_status_unknown(self, climate, mock_coordinator):
        """Without a resolvable boiler_status, falls back to the temperature heuristic."""
        mock_coordinator.rooms["room_456"]["module_ids"] = ["module_789"]
        mock_coordinator.devices["module_789"]["boiler_status"] = None
        mock_coordinator.rooms["room_456"]["therm_measured_temperature"] = 18.0
        mock_coordinator.rooms["room_456"]["therm_setpoint_temperature"] = 20.0
        assert climate.hvac_action == HVACAction.HEATING


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


class TestMigoAwayModeSwitch:
    """Tests for the home-wide away mode switch."""

    @pytest.fixture
    def switch(self, mock_coordinator):
        """Create an away mode switch, with async_write_ha_state stubbed (no hass)."""
        api = create_autospec(MigoApi, instance=True)
        api.set_therm_mode.return_value = {"status": "ok"}
        entity = MigoAwayModeSwitch(mock_coordinator, "gateway_001", api)
        entity.async_write_ha_state = MagicMock()
        return entity

    def test_is_on_false_when_schedule(self, switch, mock_coordinator):
        """Away mode reads as off when therm_mode is schedule."""
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_SCHEDULE
        assert switch.is_on is False

    def test_is_on_true_when_away(self, switch, mock_coordinator):
        """Away mode reads as on when therm_mode is away."""
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_AWAY
        assert switch.is_on is True

    @pytest.mark.asyncio
    async def test_turn_on_calls_set_therm_mode_away(self, switch, mock_coordinator):
        """Turning on writes therm_mode=away at the home level."""
        await switch.async_turn_on()

        switch._api.set_therm_mode.assert_called_once_with(home_id="home_123", mode=MODE_AWAY)
        mock_coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_turn_off_calls_set_therm_mode_schedule(self, switch, mock_coordinator):
        """Turning off returns to schedule mode (the app's "I'm back" button)."""
        await switch.async_turn_off()

        switch._api.set_therm_mode.assert_called_once_with(home_id="home_123", mode=MODE_SCHEDULE)

    @pytest.mark.asyncio
    async def test_turn_on_writes_optimistic_cache_before_api_call(self, switch, mock_coordinator):
        """Regression guard: immediate UI feedback, unlike the forum-reported DHW switch bug."""
        await switch.async_turn_on()

        mock_coordinator.set_cached_value.assert_any_call("away_mode_gateway_001", True)


class TestMigoAwayModeBinarySensor:
    """Tests for the read-only away mode binary sensor."""

    @pytest.fixture
    def binary_sensor(self, mock_coordinator):
        """Create the away mode binary sensor."""
        return MigoAwayModeBinarySensor(mock_coordinator, "gateway_001")

    def test_is_on_false_when_schedule(self, binary_sensor, mock_coordinator):
        """Off when therm_mode is schedule."""
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_SCHEDULE
        assert binary_sensor.is_on is False

    def test_is_on_true_when_away(self, binary_sensor, mock_coordinator):
        """On when therm_mode is away."""
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_AWAY
        assert binary_sensor.is_on is True

    def test_is_on_none_when_home_unresolved(self, binary_sensor, mock_coordinator):
        """Unavailable (None) if the device has no home_id."""
        mock_coordinator.devices["gateway_001"] = {"id": "gateway_001"}
        assert binary_sensor.is_on is None


class TestMigoBoilerModeSensor:
    """Tests for the derived boiler quick-action mode sensor."""

    @pytest.fixture
    def sensor(self, mock_coordinator):
        """Create the boiler mode sensor."""
        return MigoBoilerModeSensor(mock_coordinator, "gateway_001")

    def test_normal(self, sensor, mock_coordinator):
        """Normal: home therm_mode schedule, room mode home."""
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_SCHEDULE
        mock_coordinator.rooms["room_456"]["therm_setpoint_mode"] = MODE_HOME
        assert sensor.native_value == BOILER_MODE_NORMAL

    def test_dhw_only(self, sensor, mock_coordinator):
        """DHW only: a room is hg while home therm_mode stays schedule."""
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_SCHEDULE
        mock_coordinator.rooms["room_456"]["therm_setpoint_mode"] = MODE_FROST_GUARD
        assert sensor.native_value == BOILER_MODE_DHW_ONLY

    def test_frost_guard(self, sensor, mock_coordinator):
        """Frost guard: home therm_mode itself is hg."""
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_FROST_GUARD
        assert sensor.native_value == BOILER_MODE_FROST_GUARD

    def test_none_when_home_unresolved(self, sensor, mock_coordinator):
        """Unavailable (None) if the device has no home_id."""
        mock_coordinator.devices["gateway_001"] = {"id": "gateway_001"}
        assert sensor.native_value is None


class TestMigoDHWScheduleBinarySensor:
    """Tests for the scheduled DHW state binary sensor.

    Uses the forum's real timetable example: zone 1 (Night, dhw off) @00:00,
    zone 7 (Matin, dhw off) @465 (Monday 07:45), zone 0 (dhw on) @555
    (Monday 09:15).
    """

    EVENT_SCHEDULE = {
        "id": "event_1",
        "name": "Vacances int Light",
        "type": "event",
        "selected": True,
        "timetable": [
            {"zone_id": 1, "m_offset": 0},
            {"zone_id": 7, "m_offset": 465},
            {"zone_id": 0, "m_offset": 555},
        ],
        "zones": [
            {"id": 1, "name": "Nuit", "modules": [{"id": "gateway_001", "dhw_enabled": False}]},
            {"id": 7, "name": "Matin", "modules": [{"id": "gateway_001", "dhw_enabled": False}]},
            {"id": 0, "name": "Comfort", "modules": [{"id": "gateway_001", "dhw_enabled": True}]},
        ],
    }

    @pytest.fixture
    def binary_sensor(self, mock_coordinator):
        """Create the DHW schedule binary sensor with an event schedule wired in."""
        mock_coordinator.homes["home_123"]["schedules"] = [self.EVENT_SCHEDULE]
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_SCHEDULE
        return MigoDHWScheduleBinarySensor(mock_coordinator, "gateway_001")

    def test_resolves_off_slot(self, binary_sensor, freezer):
        """Monday 08:00 is within the 'Matin' slot (dhw off)."""
        freezer.move_to("2026-01-05 08:00:00")  # a Monday
        assert binary_sensor.is_on is False
        assert binary_sensor.extra_state_attributes["zone_id"] == 7
        assert binary_sensor.extra_state_attributes["zone_name"] == "Matin"
        assert binary_sensor.extra_state_attributes["overridden_by_away"] is False

    def test_resolves_on_slot(self, binary_sensor, freezer):
        """Monday 10:00 is within the last slot (dhw on)."""
        freezer.move_to("2026-01-05 10:00:00")  # a Monday
        assert binary_sensor.is_on is True
        assert binary_sensor.extra_state_attributes["zone_id"] == 0

    def test_forced_off_when_away(self, binary_sensor, mock_coordinator, freezer):
        """Away mode forces the sensor off even if the resolved slot has DHW on."""
        freezer.move_to("2026-01-05 10:00:00")  # resolves to the "on" slot
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_AWAY

        assert binary_sensor.is_on is False
        assert binary_sensor.extra_state_attributes["overridden_by_away"] is True

    def test_unavailable_without_event_schedule(self, mock_coordinator, freezer):
        """No event schedule at all resolves to unavailable (None), never a guessed value."""
        mock_coordinator.homes["home_123"]["schedules"] = []
        sensor = MigoDHWScheduleBinarySensor(mock_coordinator, "gateway_001")

        freezer.move_to("2026-01-05 10:00:00")
        assert sensor.is_on is None

    def test_uses_single_module_when_id_absent(self, mock_coordinator, freezer):
        """Falls back to a zone's single module even without a matching id (forum's real payload)."""
        schedule = {
            **self.EVENT_SCHEDULE,
            "zones": [
                {"id": 1, "modules": [{"dhw_enabled": False}]},
                {"id": 7, "name": "Matin", "modules": [{"dhw_enabled": False}]},
                {"id": 0, "modules": [{"dhw_enabled": True}]},
            ],
        }
        mock_coordinator.homes["home_123"]["schedules"] = [schedule]
        sensor = MigoDHWScheduleBinarySensor(mock_coordinator, "gateway_001")

        freezer.move_to("2026-01-05 10:00:00")
        assert sensor.is_on is True
