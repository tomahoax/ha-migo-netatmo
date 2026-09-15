"""Tests for the climate platform."""

from __future__ import annotations

from unittest.mock import MagicMock, create_autospec

import pytest
from homeassistant.components.climate import PRESET_AWAY, PRESET_BOOST, HVACAction, HVACMode
from homeassistant.exceptions import HomeAssistantError

from custom_components.migo_netatmo.api import MigoApi, MigoApiError, MigoAuthError
from custom_components.migo_netatmo.climate import (
    MIGO_TO_HVAC_MODE,
    PRESET_DHW_ONLY,
    PRESET_FROST_GUARD,
    PRESET_NORMAL,
    MigoClimate,
)
from custom_components.migo_netatmo.const import (
    DEFAULT_BOOST_DURATION,
    DEFAULT_MANUAL_SETPOINT_DURATION,
    MODE_AWAY,
    MODE_FROST_GUARD,
    MODE_HOME,
    MODE_MANUAL,
    MODE_MAX,
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
        api.set_room_state.return_value = {"status": "ok"}
        api.set_therm_mode.return_value = {"status": "ok"}
        api.set_home_therm_mode.return_value = {"status": "ok"}
        api.set_temperature_control_mode.return_value = {"status": "ok"}
        entity = MigoClimate(mock_coordinator, "room_456", api)
        entity.async_write_ha_state = MagicMock()
        return entity

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

    def test_preset_mode_normal(self, climate):
        """Test preset mode when in schedule - the baseline Normal state."""
        assert climate.preset_mode == PRESET_NORMAL

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
        """Auto writes home-level schedule via set_home_therm_mode directly.

        Regression guard: it used to go through the generic set_mode()
        dispatcher (via the bare setthermmode endpoint), which doesn't
        reset temperature_control_mode - so a value left over from
        DHW-only would keep producing the same "cooling" 403 Away's write
        used to hit (see MigoApi.set_home_therm_mode's docstring).
        """
        await climate.async_set_hvac_mode(HVACMode.AUTO)

        climate._api.set_mode.assert_not_called()
        climate._api.set_home_therm_mode.assert_called_once_with(home_id="home_123", mode=MODE_SCHEDULE)

    @pytest.mark.asyncio
    async def test_set_hvac_mode_auto_clears_stuck_room_level_hg(self, climate, mock_coordinator):
        """Auto clears a leftover room-level "hg" left by a previous Off/DHW-only selection.

        Regression guard: the home-level write never touches this room's
        own therm_setpoint_mode - and hvac_mode's own derivation checks the
        room-level mode before the home-level one, so a stuck "hg" kept
        hvac_mode reporting Off no matter how many times Auto was selected.
        Reported live and confirmed against a debug-log capture:
        therm_setpoint_mode stayed "hg" through repeated Auto clicks, only
        clearing once a room-level (Heat) write was tried.
        """
        mock_coordinator.rooms["room_456"]["therm_setpoint_mode"] = MODE_FROST_GUARD

        await climate.async_set_hvac_mode(HVACMode.AUTO)

        climate._api.set_room_state.assert_called_once_with(home_id="home_123", room_id="room_456", mode=MODE_HOME)
        climate._api.set_home_therm_mode.assert_called_once_with(home_id="home_123", mode=MODE_SCHEDULE)

    @pytest.mark.asyncio
    async def test_set_hvac_mode_auto_does_not_clear_room_when_not_overridden(self, climate):
        """No extra call when the room isn't in a leftover override to begin with."""
        await climate.async_set_hvac_mode(HVACMode.AUTO)

        climate._api.set_room_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_hvac_mode_off(self, climate):
        """Off writes the same DHW-only state the preset does.

        Regression guard: writing only the room's "hg" (via the generic
        set_mode() dispatcher) never flipped temperature_control_mode to
        "cooling", so the MiGo app itself never showed it as active even
        though it structurally matched what this integration reads back as
        DHW-only. Confirmed via a live capture of the app's own "Eau chaude
        seulement" action (see MigoApi.set_temperature_control_mode's
        docstring). temperature_control_mode is set via its own dedicated
        call, not combined with a therm_mode change in the same request -
        a first fix attempt tried that and got a live-confirmed 403.
        """
        await climate.async_set_hvac_mode(HVACMode.OFF)

        climate._api.set_mode.assert_not_called()
        climate._api.set_home_therm_mode.assert_not_called()
        climate._api.set_temperature_control_mode.assert_called_once_with(home_id="home_123", mode="cooling")
        climate._api.set_room_state.assert_called_once_with(
            home_id="home_123", room_id="room_456", mode=MODE_FROST_GUARD
        )

    @pytest.mark.asyncio
    async def test_set_preset_mode_normal(self, climate):
        """Normal clears the room to "home" and the home to schedule, unconditionally.

        Unlike Auto (HVACMode.AUTO), which only clears the room when it
        detects a specific leftover override, Normal always writes both -
        selecting it is a deliberate reset, not a mode switch that happens
        to need cleanup as a side effect.
        """
        await climate.async_set_preset_mode(PRESET_NORMAL)

        climate._api.set_room_state.assert_called_once_with(home_id="home_123", room_id="room_456", mode=MODE_HOME)
        climate._api.set_home_therm_mode.assert_called_once_with(home_id="home_123", mode=MODE_SCHEDULE)

    @pytest.mark.asyncio
    async def test_set_preset_mode_normal_clears_active_away(self, climate, mock_coordinator):
        """Normal clears an active Away, unlike DHW-only which preserves it.

        Normal is meant as a full reset to the baseline state - matching
        HVACMode.AUTO's existing behavior of unconditionally forcing
        therm_mode back to "schedule".
        """
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_AWAY

        await climate.async_set_preset_mode(PRESET_NORMAL)

        climate._api.set_home_therm_mode.assert_called_once_with(home_id="home_123", mode=MODE_SCHEDULE)

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
        """Frost guard (Veille) writes home-level hg via set_home_therm_mode.

        Regression guard: it used to go through the generic set_mode()
        dispatcher, which always routes "hg" to the room, silently producing
        the DHW-only effect instead of real standby. It then used the bare
        setthermmode endpoint directly instead of sethomedata, which
        doesn't reset temperature_control_mode - a value left over from
        DHW-only would keep producing the same "cooling" 403 Away's write
        used to hit (see MigoApi.set_home_therm_mode's docstring).
        """
        await climate.async_set_preset_mode(PRESET_FROST_GUARD)

        climate._api.set_mode.assert_not_called()
        climate._api.set_therm_mode.assert_not_called()
        climate._api.set_home_therm_mode.assert_called_once_with(home_id="home_123", mode=MODE_FROST_GUARD)
        climate._api.set_room_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_preset_mode_frost_guard_clears_stuck_room_level_manual(self, climate, mock_coordinator):
        """Frost guard clears a leftover room-level Manual/Boost override.

        Regression guard: the home-level write never touches this room's
        own therm_setpoint_mode, and preset_mode's own derivation checks a
        room-level Manual/Boost override before the home-level mode - so a
        leftover Manual/Boost would otherwise keep preset_mode stuck
        reporting Boost/None no matter what was selected here. Same class
        of bug as async_set_hvac_mode's Auto branch.
        """
        mock_coordinator.rooms["room_456"]["therm_setpoint_mode"] = MODE_MANUAL

        await climate.async_set_preset_mode(PRESET_FROST_GUARD)

        climate._api.set_room_state.assert_called_once_with(home_id="home_123", room_id="room_456", mode=MODE_HOME)
        climate._api.set_home_therm_mode.assert_called_once_with(home_id="home_123", mode=MODE_FROST_GUARD)

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
        assert climate.preset_mode == PRESET_NORMAL

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
        """DHW only writes room-level hg plus home-wide cooling, as two separate calls.

        Reported live: DHW only used to only write the room's "hg" (the
        same call HVACMode.OFF already makes), so the MiGo app itself
        never showed it as active. Confirmed via a live capture of the
        app's own "Eau chaude seulement" action: temperature_control_mode
        flips to "cooling" home-wide too (see
        MigoApi.set_temperature_control_mode's docstring). Sent as its own
        request, not combined with a therm_mode change - a first fix
        attempt tried that and got a live-confirmed 403.
        """
        await climate.async_set_preset_mode(PRESET_DHW_ONLY)

        climate._api.set_mode.assert_not_called()
        climate._api.set_therm_mode.assert_not_called()
        climate._api.set_home_therm_mode.assert_not_called()
        climate._api.set_temperature_control_mode.assert_called_once_with(home_id="home_123", mode="cooling")
        climate._api.set_room_state.assert_called_once_with(
            home_id="home_123", room_id="room_456", mode=MODE_FROST_GUARD
        )

    @pytest.mark.asyncio
    async def test_set_preset_mode_dhw_only_clears_stale_home_level_frost_guard(self, climate, mock_coordinator):
        """DHW only clears a leftover home-level real Frost guard first, as its own call.

        Regression guard: DHW-only and real Frost guard are mutually
        exclusive quick actions, so if the home was already in real Frost
        guard from an earlier selection, preset_mode's own derivation
        (which checks the home-level mode before the room-level one) kept
        reading DHW-only back as Frost guard. Reported live and confirmed
        against a debug-log capture. The clearing call uses
        set_home_therm_mode (the confirmed-safe "heating" + therm_mode
        combination) as its own separate request - never combined with the
        temperature_control_mode="cooling" call that follows it, which is
        the pairing confirmed to 403.
        """
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_FROST_GUARD

        await climate.async_set_preset_mode(PRESET_DHW_ONLY)

        climate._api.set_home_therm_mode.assert_called_once_with(home_id="home_123", mode=MODE_SCHEDULE)
        climate._api.set_temperature_control_mode.assert_called_once_with(home_id="home_123", mode="cooling")
        climate._api.set_room_state.assert_called_once_with(
            home_id="home_123", room_id="room_456", mode=MODE_FROST_GUARD
        )

    @pytest.mark.asyncio
    async def test_set_preset_mode_dhw_only_does_not_clear_home_when_away(self, climate, mock_coordinator):
        """DHW only doesn't touch therm_mode at all when the home isn't in real Frost guard.

        In particular, an active Away is left alone: since therm_mode is
        never sent unless clearing a stale real Frost guard, there's
        nothing here that could accidentally overwrite it - sidesteps
        needing to know what the real DHW-only quick action does to Away,
        which no live capture has confirmed either way.
        """
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_AWAY

        await climate.async_set_preset_mode(PRESET_DHW_ONLY)

        climate._api.set_home_therm_mode.assert_not_called()
        climate._api.set_temperature_control_mode.assert_called_once_with(home_id="home_123", mode="cooling")
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


class TestClimateErrorSurfacing:
    """Tests for API errors surfacing as UI-visible exceptions."""

    @pytest.fixture
    def climate(self, mock_coordinator):
        """Create a climate entity with an autospecced API mock."""
        api = create_autospec(MigoApi, instance=True)
        api.set_temperature.return_value = {"status": "ok"}
        api.set_mode.return_value = {"status": "ok"}
        entity = MigoClimate(mock_coordinator, "room_456", api)
        entity.async_write_ha_state = MagicMock()
        return entity

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
        climate._api.set_home_therm_mode.side_effect = MigoAuthError("expired")

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
