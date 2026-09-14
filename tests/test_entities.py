"""Tests for MiGo (Netatmo) entities."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

import pytest
from homeassistant.components.climate import PRESET_AWAY, PRESET_BOOST, HVACAction, HVACMode
from homeassistant.const import EntityCategory
from homeassistant.exceptions import ServiceValidationError

from custom_components.migo_netatmo.api import MigoApi
from custom_components.migo_netatmo.binary_sensor import (
    MigoAwayModeBinarySensor,
    MigoDHWScheduleBinarySensor,
)
from custom_components.migo_netatmo.button import MigoResetHeatingCurveButton
from custom_components.migo_netatmo.climate import (
    HVAC_TO_MIGO_MODE,
    MIGO_TO_HVAC_MODE,
    PRESET_DHW_ONLY,
    PRESET_FROST_GUARD,
    MigoClimate,
)
from custom_components.migo_netatmo.const import (
    BOILER_MODE_DHW_ONLY,
    BOILER_MODE_FROST_GUARD,
    BOILER_MODE_NORMAL,
    DEFAULT_BOOST_DURATION,
    DEFAULT_HEATING_CURVE,
    DEFAULT_MANUAL_SETPOINT_DURATION,
    MODE_AWAY,
    MODE_FROST_GUARD,
    MODE_HOME,
    MODE_MANUAL,
    MODE_MAX,
    MODE_SCHEDULE,
    TEMP_MAX,
)
from custom_components.migo_netatmo.datetime import MigoAwayReturnDateTime
from custom_components.migo_netatmo.entity import MigoThermostatEntity, _entity_config_entry_id, _resolve_via_device_id
from custom_components.migo_netatmo.number import (
    MigoDHWTemperatureNumber,
    MigoHeatingCurveNumber,
    MigoTemperatureOffsetNumber,
)
from custom_components.migo_netatmo.sensor import MigoBoilerModeSensor
from custom_components.migo_netatmo.switch import (
    MigoAnticipationSwitch,
    MigoAwayModeSwitch,
    MigoDHWAlwaysOnSwitch,
    MigoDHWSwitch,
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

    def test_preset_mode_reads_away_switch_cache_via_resolved_gateway(self, climate, mock_coordinator):
        """`_home_is_away` must not disagree with switch.migo_{home}_away_mode right after a toggle.

        Regression guard: preset_mode used to compare raw
        coordinator.homes data directly, so it could show the pre-toggle
        state for a few seconds while the switch/binary_sensor/datetime
        entities (already cache-aware) had already updated.
        """
        mock_coordinator.rooms["room_456"]["module_ids"] = ["module_789"]
        mock_coordinator.devices["module_789"]["bridge"] = "gateway_001"
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_SCHEDULE
        mock_coordinator.get_cached_value = MagicMock(
            side_effect=lambda key, default=None: True if key == "away_mode_gateway_001" else default
        )

        assert climate.preset_mode == PRESET_AWAY

    def test_preset_mode_not_away_when_switch_cache_says_off_despite_stale_home_data(self, climate, mock_coordinator):
        """Same mechanism, the other direction: cache wins over stale raw data too."""
        mock_coordinator.rooms["room_456"]["module_ids"] = ["module_789"]
        mock_coordinator.devices["module_789"]["bridge"] = "gateway_001"
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_AWAY
        mock_coordinator.get_cached_value = MagicMock(
            side_effect=lambda key, default=None: False if key == "away_mode_gateway_001" else default
        )

        assert climate.preset_mode != PRESET_AWAY

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
        """Away writes home-level Away via set_home_therm_mode directly.

        Regression guard: it used to go through the generic set_mode()
        dispatcher (via setthermmode, with no endtime parameter), so it
        could never clear a return time left over from a previous Away
        period - unlike switch.migo_{home}_away_mode and
        button.migo_{home}_reset_away_until, which already clear it via an
        explicit endtime=None.
        """
        await climate.async_set_preset_mode(PRESET_AWAY)

        climate._api.set_mode.assert_not_called()
        climate._api.set_home_therm_mode.assert_called_once_with(home_id="home_123", mode=MODE_AWAY, endtime=None)

    @pytest.mark.asyncio
    async def test_set_preset_mode_frost_guard(self, climate):
        """Frost guard (Veille) writes home-level hg via set_therm_mode directly.

        Regression guard: it used to go through the generic set_mode()
        dispatcher, which always routes "hg" to the room, silently producing
        the DHW-only effect instead of real standby.
        """
        await climate.async_set_preset_mode(PRESET_FROST_GUARD)

        climate._api.set_mode.assert_not_called()
        climate._api.set_therm_mode.assert_called_once_with(home_id="home_123", mode=MODE_FROST_GUARD)

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

    def test_preset_mode_away_not_hidden_by_manual_override(self, climate, mock_coordinator):
        """Away must surface even while the room has a manual/boost override active.

        Regression guard: the MODE_MANUAL/MODE_MAX branches used to `return`
        before the code ever reached the Away check, contradicting the
        adjacent comment's own claim that Away "is checked first".
        """
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_AWAY
        mock_coordinator.rooms["room_456"]["therm_setpoint_mode"] = MODE_MANUAL
        mock_coordinator.rooms["room_456"]["therm_setpoint_temperature"] = TEMP_MAX

        assert climate.preset_mode == PRESET_AWAY

    def test_preset_mode_away_not_hidden_by_boost(self, climate, mock_coordinator):
        """Same as above, for the MODE_MAX (forced boost) branch."""
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_AWAY
        mock_coordinator.rooms["room_456"]["therm_setpoint_mode"] = MODE_MAX

        assert climate.preset_mode == PRESET_AWAY

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
    async def test_set_preset_mode_dhw_only_writes_room_level_hg(self, climate):
        """DHW only (Eau chaude seulement) writes room-level hg via set_room_state directly.

        The same call HVACMode.OFF already makes - previously misdiagnosed
        as "no known write path" and rejected outright.
        """
        await climate.async_set_preset_mode(PRESET_DHW_ONLY)

        climate._api.set_mode.assert_not_called()
        climate._api.set_room_state.assert_called_once_with(
            home_id="home_123", room_id="room_456", mode=MODE_FROST_GUARD
        )

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


class TestMigoAwayModeSwitch:
    """Tests for the home-wide away mode switch."""

    @pytest.fixture
    def switch(self, mock_coordinator):
        """Create an away mode switch, with async_write_ha_state stubbed (no hass)."""
        api = create_autospec(MigoApi, instance=True)
        api.set_home_therm_mode.return_value = {"status": "ok"}
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
    async def test_turn_on_calls_set_home_therm_mode_away(self, switch, mock_coordinator):
        """Turning on writes therm_mode=away at the home level, clearing any endtime."""
        await switch.async_turn_on()

        switch._api.set_home_therm_mode.assert_called_once_with(home_id="home_123", mode=MODE_AWAY, endtime=None)
        mock_coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_turn_off_calls_set_home_therm_mode_schedule(self, switch, mock_coordinator):
        """Turning off returns to schedule mode (the app's "I'm back" button), clearing any endtime."""
        await switch.async_turn_off()

        switch._api.set_home_therm_mode.assert_called_once_with(home_id="home_123", mode=MODE_SCHEDULE, endtime=None)

    @pytest.mark.asyncio
    async def test_turn_on_writes_optimistic_cache_before_api_call(self, switch, mock_coordinator):
        """Regression guard: immediate UI feedback, unlike the forum-reported DHW switch bug."""
        await switch.async_turn_on()

        mock_coordinator.set_cached_value.assert_any_call("away_mode_gateway_001", True)

    @pytest.mark.asyncio
    async def test_turn_on_clears_away_until(self, switch, mock_coordinator):
        """A plain toggle specifies no return time, so any stale one is cleared.

        Reported as "can't reset Away until": the datetime entity has no
        clear affordance of its own, so toggling this switch (either
        direction) is the only deliberate way to reset it.
        """
        await switch.async_turn_on()

        mock_coordinator.clear_cached_value.assert_any_call("away_until_gateway_001")

    @pytest.mark.asyncio
    async def test_turn_off_clears_away_until(self, switch, mock_coordinator):
        """Same as turn_on: coming back should not leave a stale return time displayed."""
        await switch.async_turn_off()

        mock_coordinator.clear_cached_value.assert_any_call("away_until_gateway_001")

    @pytest.mark.asyncio
    async def test_turn_off_notifies_listeners_for_away_until(self, switch, mock_coordinator):
        """Regression guard: clearing the cache alone doesn't push any entity's state.

        Reported live: the Away until value wasn't clearing when Away mode
        was turned off. Clearing the coordinator cache dict is invisible to
        Home Assistant on its own - MigoAwayReturnDateTime needs its
        listener actually invoked to re-render.
        """
        await switch.async_turn_off()

        mock_coordinator.async_update_listeners.assert_called_once()

    @pytest.mark.asyncio
    async def test_turn_on_notifies_listeners_for_away_until(self, switch, mock_coordinator):
        """Same as turn_off, for symmetry."""
        await switch.async_turn_on()

        mock_coordinator.async_update_listeners.assert_called_once()

    @pytest.mark.asyncio
    async def test_away_until_notified_before_api_call(self, mock_coordinator):
        """The push must happen before the API call, not after.

        That's the whole point of the on_optimistic hook: is_home_away()
        (which MigoAwayReturnDateTime.native_value now uses) needs to see
        this switch's fresh optimistic cache value, not risk reading
        coordinator.homes data that a debounced refresh hasn't updated yet.
        """
        events: list[str] = []
        mock_coordinator.async_update_listeners = MagicMock(side_effect=lambda: events.append("notify"))
        api = create_autospec(MigoApi, instance=True)

        async def fake_set_home_therm_mode(**kwargs):
            events.append("api_call")
            return {"status": "ok"}

        api.set_home_therm_mode.side_effect = fake_set_home_therm_mode
        entity = MigoAwayModeSwitch(mock_coordinator, "gateway_001", api)
        entity.async_write_ha_state = MagicMock()

        await entity.async_turn_off()

        assert events == ["notify", "api_call"]

    def test_is_on_reads_optimistic_cache_first(self, switch, mock_coordinator):
        """The cache MigoAwayModeSwitch itself writes takes priority over API data."""
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_SCHEDULE
        mock_coordinator.get_cached_value = MagicMock(return_value=True)

        assert switch.is_on is True

    @pytest.mark.asyncio
    async def test_turn_on_while_frost_guard_replaces_it(self, switch, mock_coordinator):
        """therm_mode is a single shared field: Away and real Frost guard are
        mutually exclusive by construction, same as in the MiGo app itself -
        confirmed not a bug (see class docstring), not something to guard
        against here.
        """
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_FROST_GUARD

        await switch.async_turn_on()

        switch._api.set_home_therm_mode.assert_called_once_with(home_id="home_123", mode=MODE_AWAY, endtime=None)


class TestMigoDHWAlwaysOnSwitch:
    """Tests for the DHW "always on" switch (the MiGo app's "Toujours activée").

    Same shape as MigoDHWSwitch: `MigoGatewayControlEntity` base,
    cache-then-API-fallback `is_on`, `_call_api_optimistically` on write.
    Read/write via `dhw_always_on` (getconfigs/setconfigs), confirmed via a
    live debug-log capture.
    """

    @pytest.fixture
    def switch(self, mock_coordinator):
        """Create a DHW always-on switch, with async_write_ha_state stubbed (no hass)."""
        api = create_autospec(MigoApi, instance=True)
        api.set_dhw_always_on.return_value = {"status": "ok"}
        entity = MigoDHWAlwaysOnSwitch(mock_coordinator, "gateway_001", api)
        entity.async_write_ha_state = MagicMock()
        return entity

    def test_is_on_none_by_default(self, switch):
        """No dhw_always_on field in the default device fixture data."""
        assert switch.is_on is None

    def test_is_on_reads_from_api(self, switch, mock_coordinator):
        """Falls back to the API-echoed dhw_always_on device field."""
        mock_coordinator.devices["gateway_001"]["dhw_always_on"] = True
        assert switch.is_on is True

    @pytest.mark.asyncio
    async def test_turn_on_calls_set_dhw_always_on(self, switch, mock_coordinator):
        """Turning on writes dhw_always_on=True for this gateway."""
        await switch.async_turn_on()

        switch._api.set_dhw_always_on.assert_called_once_with(home_id="home_123", module_id="gateway_001", enabled=True)
        mock_coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_turn_off_calls_set_dhw_always_on(self, switch, mock_coordinator):
        """Turning off writes dhw_always_on=False for this gateway."""
        await switch.async_turn_off()

        switch._api.set_dhw_always_on.assert_called_once_with(
            home_id="home_123", module_id="gateway_001", enabled=False
        )

    @pytest.mark.asyncio
    async def test_turn_on_writes_optimistic_cache_before_api_call(self, switch, mock_coordinator):
        """Immediate UI feedback, same regression guard as the other switches."""
        await switch.async_turn_on()

        mock_coordinator.set_cached_value.assert_any_call("dhw_always_on_gateway_001", True)


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

    def test_is_on_reads_optimistic_cache_first(self, binary_sensor, mock_coordinator):
        """Reflects a MigoAwayModeSwitch toggle immediately, not one refresh behind.

        Regression guard: this read-only companion used to read
        coordinator.homes directly, so it visibly disagreed with the switch
        (which does check its own cache) until the next coordinator refresh.
        """
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_SCHEDULE
        mock_coordinator.get_cached_value = MagicMock(return_value=True)

        assert binary_sensor.is_on is True


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

    def test_ignores_rooms_from_other_homes(self, sensor, mock_coordinator):
        """A DHW-only room in a different home must not leak into this gateway's mode.

        Regression guard: native_value used to scan every room in every
        home before filtering by home_id inline, rather than through a
        home-scoped lookup - same result today, but this pins the scoping
        so a future change to that lookup can't silently regress it.
        """
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_SCHEDULE
        mock_coordinator.rooms["room_456"]["therm_setpoint_mode"] = MODE_HOME
        mock_coordinator.rooms["other_room"] = {
            "id": "other_room",
            "home_id": "other_home",
            "therm_setpoint_mode": MODE_FROST_GUARD,
        }

        assert sensor.native_value == BOILER_MODE_NORMAL


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

    def test_forced_off_when_away_without_event_schedule(self, mock_coordinator, freezer):
        """Away still forces off even when the schedule itself can't be resolved.

        Regression guard: the away override used to be applied only on the
        fully-resolved path, so an unresolvable schedule during Away
        reported unknown (None) instead of the documented unconditional off.
        """
        mock_coordinator.homes["home_123"]["schedules"] = []
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_AWAY
        sensor = MigoDHWScheduleBinarySensor(mock_coordinator, "gateway_001")

        freezer.move_to("2026-01-05 10:00:00")
        assert sensor.is_on is False
        assert sensor.extra_state_attributes["overridden_by_away"] is True

    def test_forced_off_when_away_with_unresolvable_zone(self, mock_coordinator, freezer):
        """Same as above, for a schedule whose timetable resolves to no matching zone."""
        schedule = {**self.EVENT_SCHEDULE, "zones": []}
        mock_coordinator.homes["home_123"]["schedules"] = [schedule]
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_AWAY
        sensor = MigoDHWScheduleBinarySensor(mock_coordinator, "gateway_001")

        freezer.move_to("2026-01-05 10:00:00")
        assert sensor.is_on is False
        assert sensor.extra_state_attributes["overridden_by_away"] is True

    def test_resolve_cached_per_coordinator_update(self, binary_sensor, freezer):
        """is_on and extra_state_attributes share one resolution per update cycle.

        Regression guard: _resolve() used to fully recompute (including a
        timetable sort) on every property access - once from is_on, once
        from extra_state_attributes.
        """
        freezer.move_to("2026-01-05 08:00:00")

        first = binary_sensor.is_on
        attrs = binary_sensor.extra_state_attributes
        assert first is False
        assert attrs["zone_id"] == 7
        # extra_state_attributes must not have mutated the cached dict that
        # is_on's own result came from (an aliasing hazard the cache adds).
        assert binary_sensor.is_on is False

        binary_sensor.async_write_ha_state = MagicMock()
        binary_sensor._handle_coordinator_update()
        assert binary_sensor._resolved_cache is None


class TestDevicePageOrganization:
    """Regression guard for the Controls/Configuration/Diagnostic reorganization.

    See docs/entities.md's "Device Page Organization" section: operational
    toggles and quick actions (including Refresh) land in Controls (no
    entity_category), setpoints/tuning values and the buttons acting on them
    stay in Configuration, and read-only companions to a Controls entity
    move to Diagnostic. These assertions exist so the grouping can't
    silently drift.
    """

    # Note: entity_category must be read from an instance's `.entity_category`
    # property, not `_attr_entity_category` on the class - Home Assistant's
    # CachedProperty machinery turns the latter into a descriptor at class
    # definition time, so accessing it unbound (on the class, no instance)
    # returns the descriptor object rather than the configured value.

    def test_dhw_boost_switch_is_primary_control(self, mock_coordinator):
        """DHW boost is an operational toggle, not a configuration value."""
        api = create_autospec(MigoApi, instance=True)
        entity = MigoDHWSwitch(mock_coordinator, "gateway_001", api)
        assert entity.entity_category is None

    def test_anticipation_switch_is_primary_control(self, mock_coordinator):
        """Heating anticipation is an operational toggle, not a configuration value."""
        api = create_autospec(MigoApi, instance=True)
        entity = MigoAnticipationSwitch(mock_coordinator, "home_123", api)
        assert entity.entity_category is None

    def test_away_mode_switch_is_primary_control(self, mock_coordinator):
        """Away mode switch stays a primary control (unchanged by this reorganization)."""
        api = create_autospec(MigoApi, instance=True)
        entity = MigoAwayModeSwitch(mock_coordinator, "gateway_001", api)
        assert entity.entity_category is None

    def test_dhw_always_on_switch_is_primary_control(self, mock_coordinator):
        """DHW always-on is an operational override, same reasoning as DHW boost."""
        api = create_autospec(MigoApi, instance=True)
        entity = MigoDHWAlwaysOnSwitch(mock_coordinator, "gateway_001", api)
        assert entity.entity_category is None

    def test_away_mode_binary_sensor_is_diagnostic(self, mock_coordinator):
        """Read-only companion to the switch: moved out of Sensors to avoid duplicating it."""
        entity = MigoAwayModeBinarySensor(mock_coordinator, "gateway_001")
        assert entity.entity_category == EntityCategory.DIAGNOSTIC


class TestNumberOptimisticCacheClearing:
    """Regression guard: number entities must clear their optimistic cache
    after a successful write.

    A user reported that a DHW temperature change made from the MiGo mobile
    app didn't show up in Home Assistant after pressing Refresh. Root cause
    investigation (see CHANGELOG) found the real bug wasn't that report
    itself (a backend propagation delay, outside our control) but a related
    latent one: these entities set an optimistic cache on write and never
    cleared it, so touching a slider from Home Assistant even once would
    permanently mask all future out-of-band changes until the next restart.
    All five `number` entities plus `MigoResetHeatingCurveButton` were
    switched to `_call_api_optimistically`, whose clearing behavior is
    covered generically in test_entity_mixin.py - these two tests just
    confirm each entity is actually wired up to use it, with the right API
    call and cache key.
    """

    @pytest.fixture
    def cache(self, mock_coordinator):
        """Give mock_coordinator a real dict-backed cache instead of a bare MagicMock."""
        store: dict = {}
        mock_coordinator.get_cached_value = MagicMock(side_effect=lambda k, default=None: store.get(k, default))
        mock_coordinator.set_cached_value = MagicMock(side_effect=store.__setitem__)
        mock_coordinator.clear_cached_value = MagicMock(side_effect=lambda k: store.pop(k, None))
        return store

    @pytest.mark.asyncio
    async def test_dhw_temperature_clears_cache_after_refresh(self, mock_coordinator, cache):
        """This is the exact entity from the bug report."""
        api = create_autospec(MigoApi, instance=True)
        api.set_dhw_temperature.return_value = {"status": "ok"}
        entity = MigoDHWTemperatureNumber(mock_coordinator, "gateway_001", api)
        entity.async_write_ha_state = MagicMock()

        await entity.async_set_native_value(52)

        api.set_dhw_temperature.assert_called_once_with(home_id="home_123", module_id="gateway_001", temperature=52)
        assert cache == {}

    @pytest.mark.asyncio
    async def test_temperature_offset_clears_cache_after_refresh(self, mock_coordinator, cache):
        """Also verifies the MigoRoomControlEntity base class swap (it had no mixin before)."""
        api = create_autospec(MigoApi, instance=True)
        api.set_temperature_offset.return_value = {"status": "ok"}
        entity = MigoTemperatureOffsetNumber(mock_coordinator, "room_456", "home_123", api)
        entity.async_write_ha_state = MagicMock()

        await entity.async_set_native_value(1.5)

        api.set_temperature_offset.assert_called_once_with(home_id="home_123", room_id="room_456", offset=1.5)
        assert cache == {}


class TestHeatingCurveDefault:
    """Tests for MigoHeatingCurveNumber/MigoResetHeatingCurveButton and DEFAULT_HEATING_CURVE.

    Reported live: "Reset heating curve" set the value to 1.5, not the 2.6
    shown in the MiGo app. Root cause investigated via a live debug-log
    capture: `heating_curve` is never present in homesdata/homestatus/
    getconfigs, so there is no API-discoverable "true default" to reset to
    at all - it's an installation-specific calibration value. The user
    chose to just update the constant to match their own installation
    (2.6) rather than remove the button; these tests pin that constant's
    current value and confirm both entities are wired to use it, not that
    2.6 is itself "correct" in any universal sense.
    """

    def test_default_heating_curve_is_2_6(self):
        """Pins the constant so a future edit doesn't silently drift again."""
        assert DEFAULT_HEATING_CURVE == 2.6

    @pytest.mark.asyncio
    async def test_reset_button_writes_default_heating_curve(self, mock_coordinator):
        api = create_autospec(MigoApi, instance=True)
        api.set_heating_curve.return_value = {"status": "ok"}
        entity = MigoResetHeatingCurveButton(mock_coordinator, "home_123", "gateway_001", api)
        entity.async_write_ha_state = MagicMock()

        await entity.async_press()

        api.set_heating_curve.assert_called_once_with(device_id="gateway_001", slope=DEFAULT_HEATING_CURVE)

    def test_number_native_value_falls_back_to_default(self, mock_coordinator):
        """No cache, no API data (heating_curve is write-only) - falls back to the constant."""
        entity = MigoHeatingCurveNumber(
            mock_coordinator, "home_123", "gateway_001", create_autospec(MigoApi, instance=True)
        )

        assert entity.native_value == DEFAULT_HEATING_CURVE


class TestMigoAwayReturnDateTime:
    """Tests for the Away return date/time entity.

    `therm_mode_endtime` is confirmed to round-trip via the API (a live
    debug-log capture, cross-checked against the user's own MiGo app
    screenshot), so this uses the standard `_call_api_optimistically`
    pattern like every other read/write entity: the cache is cleared after
    a successful call, and `native_value` falls back to the API-echoed
    value (gated on `therm_mode == MODE_AWAY`, so a lingering endtime from
    a past Away period isn't shown once the mode has moved on).
    """

    @pytest.fixture
    def cache(self, mock_coordinator):
        """Give mock_coordinator a real dict-backed cache instead of a bare MagicMock."""
        store: dict = {}
        mock_coordinator.get_cached_value = MagicMock(side_effect=lambda k, default=None: store.get(k, default))
        mock_coordinator.set_cached_value = MagicMock(side_effect=store.__setitem__)
        mock_coordinator.clear_cached_value = MagicMock(side_effect=lambda k: store.pop(k, None))
        return store

    @pytest.fixture
    def entity(self, mock_coordinator):
        api = create_autospec(MigoApi, instance=True)
        api.set_home_therm_mode.return_value = {"status": "ok"}
        ent = MigoAwayReturnDateTime(mock_coordinator, "gateway_001", api)
        ent.async_write_ha_state = MagicMock()
        return ent

    @pytest.mark.asyncio
    async def test_set_value_activates_away_with_endtime(self, entity, cache):
        """Converts the datetime to a Unix timestamp and activates Away."""
        value = datetime(2026, 12, 24, 18, 0, tzinfo=UTC)

        await entity.async_set_value(value)

        entity._api.set_home_therm_mode.assert_called_once_with(
            home_id="home_123", mode=MODE_AWAY, endtime=int(value.timestamp())
        )

    @pytest.mark.asyncio
    async def test_cache_cleared_after_successful_set(self, entity, cache):
        """Unlike the earlier hand-rolled implementation, the cache IS cleared on success."""
        value = datetime(2026, 12, 24, 18, 0, tzinfo=UTC)

        await entity.async_set_value(value)

        assert cache == {}

    @pytest.mark.asyncio
    async def test_set_value_rejects_past_datetime(self, entity, cache):
        """Regression guard: the real API rejects a past endtime with a 400
        ("endtime in past"), reported live - `_call_api_optimistically`'s
        rollback then silently cleared the value, looking exactly like
        "no way to confirm the value" rather than a validation failure.
        Caught here instead, before any API call or optimistic write.
        """
        past_value = datetime(2020, 1, 1, tzinfo=UTC)

        with pytest.raises(ServiceValidationError):
            await entity.async_set_value(past_value)

        entity._api.set_home_therm_mode.assert_not_called()
        assert cache == {}

    @pytest.mark.asyncio
    async def test_native_value_falls_back_to_api_after_successful_set(self, entity, mock_coordinator, cache):
        """Once the optimistic cache is cleared, native_value re-derives from the API-echoed home data."""
        value = datetime(2026, 12, 24, 18, 0, tzinfo=UTC)
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_AWAY
        mock_coordinator.homes["home_123"]["therm_mode_endtime"] = int(value.timestamp())

        await entity.async_set_value(value)

        assert entity.native_value == value

    def test_native_value_none_by_default(self, entity):
        """No return time has been set yet, and therm_mode is not away by default."""
        assert entity.native_value is None

    def test_native_value_from_api_when_away(self, entity, mock_coordinator):
        """Falls back to the API-echoed therm_mode_endtime while actually Away."""
        value = datetime(2026, 12, 24, 18, 0, tzinfo=UTC)
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_AWAY
        mock_coordinator.homes["home_123"]["therm_mode_endtime"] = int(value.timestamp())

        assert entity.native_value == value

    def test_native_value_none_when_switch_cache_says_away_but_raw_data_not_refreshed_yet(
        self, entity, mock_coordinator
    ):
        """Regression guard for the reported "old date flashes on reactivation" complaint.

        Reactivating switch.migo_{home}_away_mode sets its own cache to
        True (via _call_api_optimistically) *before* the API call, and its
        on_optimistic hook pushes this entity's listener right then - so
        is_home_away() already reads True while coordinator.homes hasn't
        been refreshed yet and still carries therm_mode="schedule" plus
        whatever therm_mode_endtime a *previous* Away period left behind.
        native_value must not show that stale value in this window.
        """
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_SCHEDULE
        mock_coordinator.homes["home_123"]["therm_mode_endtime"] = 1234567890
        mock_coordinator.get_cached_value = MagicMock(
            side_effect=lambda key, default=None: True if key == "away_mode_gateway_001" else default
        )

        assert entity.native_value is None

    def test_native_value_shows_once_raw_data_agrees_too(self, entity, mock_coordinator):
        """Once coordinator.homes itself catches up (raw therm_mode == away), the value shows - no over-correction."""
        value = datetime(2026, 12, 24, 18, 0, tzinfo=UTC)
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_AWAY
        mock_coordinator.homes["home_123"]["therm_mode_endtime"] = int(value.timestamp())
        mock_coordinator.get_cached_value = MagicMock(
            side_effect=lambda key, default=None: True if key == "away_mode_gateway_001" else default
        )

        assert entity.native_value == value

    def test_native_value_none_when_not_away_even_with_stale_endtime(self, entity, mock_coordinator):
        """A lingering endtime from a past Away period isn't shown once therm_mode has moved on."""
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_SCHEDULE
        mock_coordinator.homes["home_123"]["therm_mode_endtime"] = 1234567890

        assert entity.native_value is None

    def test_native_value_none_when_home_unresolved(self, entity, mock_coordinator):
        """Unavailable (None) if the device has no home_id."""
        mock_coordinator.devices["gateway_001"] = {"id": "gateway_001"}
        assert entity.native_value is None

    def test_native_value_none_when_switch_cache_says_not_away_even_if_home_data_stale(self, entity, mock_coordinator):
        """Reads MigoAwayModeSwitch's own cache, not just raw coordinator.homes data.

        Regression guard for the reported "turning off Away doesn't clear
        Away until" complaint: the switch's own async_request_refresh() can
        be coalesced by the coordinator's debouncer, leaving
        coordinator.homes stale (still showing therm_mode="away") for
        several more seconds. native_value must still show cleared
        immediately once the switch's away_mode cache says otherwise,
        rather than waiting on that stale raw data.
        """
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_AWAY
        mock_coordinator.homes["home_123"]["therm_mode_endtime"] = 1234567890
        # Simulate MigoAwayModeSwitch having just set its own cache to False
        # (as _call_api_optimistically does, synchronously, before the API
        # call even returns) while coordinator.homes above is still stale.
        mock_coordinator.get_cached_value = MagicMock(
            side_effect=lambda key, default=None: False if key == "away_mode_gateway_001" else default
        )

        assert entity.native_value is None

    @pytest.mark.asyncio
    async def test_set_value_restores_previous_on_failure(self, entity, cache):
        """A failed call restores whatever return time was cached before it."""
        previous = datetime(2026, 12, 20, 9, 0, tzinfo=UTC)
        cache["away_until_gateway_001"] = previous
        entity._api.set_home_therm_mode.side_effect = RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await entity.async_set_value(datetime(2026, 12, 24, 18, 0, tzinfo=UTC))

        assert entity.native_value == previous


class TestResolveViaDeviceId:
    """Tests for _resolve_via_device_id.

    Regression guard: `via_device` (the identifiers-tuple form) is
    deprecated and, unlike most Home Assistant deprecation warnings, a
    caller Home Assistant attributes to a *core* integration (which can
    happen for entities added outside their platform's normal initial
    setup, e.g. as a side effect of an entity registry edit) makes it raise
    instead of just log - this broke entity setup live once already. All
    four `device_info` properties that link to a parent gateway now resolve
    `via_device_id` through this function instead.

    Uses `async_get_device_by_identifier` (config-entry-scoped), not
    `async_get_device` - that one is deprecated too (a live warning caught
    after the first fix shipped), and the exact same "raises instead of
    warns under some caller attributions" risk applies to it as well.
    """

    def test_none_when_hass_not_set(self):
        """No hass yet (as in every device_info test in this file, none of which set it)."""
        assert _resolve_via_device_id(None, "entry_1", "gateway_001") is None

    def test_none_when_config_entry_id_not_set(self):
        """No platform/config entry yet either - same "not fully added" case."""
        hass = MagicMock()
        assert _resolve_via_device_id(hass, None, "gateway_001") is None

    def test_none_when_gateway_not_registered(self):
        """The gateway device hasn't been registered yet - omit rather than raise."""
        hass = MagicMock()
        with patch("custom_components.migo_netatmo.entity.dr.async_get") as mock_async_get:
            mock_async_get.return_value.async_get_device_by_identifier.return_value = None
            assert _resolve_via_device_id(hass, "entry_1", "gateway_001") is None

    def test_returns_registry_device_id_when_found(self):
        """Resolves to the registry's own internal device_id, not the identifiers tuple."""
        hass = MagicMock()
        with patch("custom_components.migo_netatmo.entity.dr.async_get") as mock_async_get:
            mock_async_get.return_value.async_get_device_by_identifier.return_value = MagicMock(
                id="internal_device_id_123"
            )
            result = _resolve_via_device_id(hass, "entry_1", "gateway_001")

        assert result == "internal_device_id_123"
        mock_async_get.return_value.async_get_device_by_identifier.assert_called_once_with(
            ("migo_netatmo", "gateway_001"), "entry_1"
        )


class TestEntityConfigEntryId:
    """Tests for _entity_config_entry_id."""

    def test_none_when_platform_not_set(self):
        """Matches every other test's entity construction - no platform, no crash."""
        entity = MagicMock(spec=[])
        assert _entity_config_entry_id(entity) is None

    def test_none_when_platform_has_no_config_entry(self):
        entity = MagicMock()
        entity.platform.config_entry = None
        assert _entity_config_entry_id(entity) is None

    def test_returns_platform_config_entry_id(self):
        entity = MagicMock()
        entity.platform.config_entry.entry_id = "entry_123"
        assert _entity_config_entry_id(entity) == "entry_123"


class TestThermostatEntityDeviceInfo:
    """Tests for MigoThermostatEntity.device_info's via_device_id linkage."""

    def test_omits_via_device_id_without_hass(self, mock_coordinator):
        """No hass set (matches every other test's entity construction) - no crash, just omitted."""
        mock_coordinator.devices["module_789"]["bridge"] = "gateway_001"
        entity = MigoThermostatEntity(mock_coordinator, "module_789")
        info = entity.device_info
        assert "via_device_id" not in info

    def test_sets_via_device_id_when_gateway_registered(self, mock_coordinator):
        """Links to the parent gateway's registry device_id when it can be resolved."""
        mock_coordinator.devices["module_789"]["bridge"] = "gateway_001"
        entity = MigoThermostatEntity(mock_coordinator, "module_789")
        entity.hass = MagicMock()
        entity.platform = MagicMock()
        entity.platform.config_entry.entry_id = "entry_1"

        with patch("custom_components.migo_netatmo.entity.dr.async_get") as mock_async_get:
            mock_async_get.return_value.async_get_device_by_identifier.return_value = MagicMock(
                id="internal_gateway_id"
            )
            info = entity.device_info

        assert info["via_device_id"] == "internal_gateway_id"
