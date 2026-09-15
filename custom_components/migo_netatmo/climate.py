"""Climate platform for MiGO integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, override

from homeassistant.components.climate import (
    PRESET_AWAY,
    PRESET_BOOST,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DEFAULT_BOOST_DURATION,
    DEFAULT_MANUAL_SETPOINT_DURATION,
    MODE_AWAY,
    MODE_FROST_GUARD,
    MODE_HOME,
    MODE_MANUAL,
    MODE_MAX,
    MODE_OFF,
    MODE_SCHEDULE,
    TEMP_MAX,
    TEMP_MIN,
    TEMP_STEP,
)
from .coordinator import MigoDataUpdateCoordinator
from .entity import MigoRoomControlEntity
from .entity_setup import register_dynamic_entities
from .helpers import generate_unique_id, get_home_id_or_raise, get_thermostat_for_room, is_home_away, safe_float

if TYPE_CHECKING:
    from . import MigoConfigEntry
    from .api import MigoApi

_LOGGER = logging.getLogger(__name__)

# Serialise write commands against the cloud API
PARALLEL_UPDATES = 1

# Custom preset mode names for MiGO-specific states
# MiGo's "Normal" boiler quick-action: the baseline state (home-level
# schedule/heating, no room override) - the third option alongside DHW
# only and Frost guard in the app's own "Actions rapides". Added so
# leaving either of those, or Away, is reachable directly from the preset
# selector, without also needing the separate HVAC mode wheel.
PRESET_NORMAL = "normal"
PRESET_FROST_GUARD = "frost_guard"
# MiGo's "DHW only" boiler quick-action: the room's therm_setpoint_mode is
# "hg" while the home's therm_mode stays "schedule" (as opposed to real
# frost guard/standby, where therm_mode itself is "hg"). Both share the same
# underlying MiGo mode value ("hg") but at different API levels - see
# async_set_preset_mode, which writes each one explicitly rather than
# through the ambiguous generic dispatcher (MigoApi.set_mode()).
PRESET_DHW_ONLY = "dhw_only"

# Map MiGO room-level modes to HVAC modes.
# MODE_HOME used to map to HEAT here, which was wrong: per community forum
# testing, "home" is the room's normal running state (both in the Normal and
# the Away boiler modes), not a heat override. The `hvac_mode` property below
# only falls back to this dict once it has ruled out the modes (manual, max,
# hg, off) and the home-level therm_mode (real frost guard/standby) that need
# special-casing first, so this dict effectively only decides between
# schedule/home/away, which are all AUTO.
MIGO_TO_HVAC_MODE: dict[str, HVACMode] = {
    MODE_SCHEDULE: HVACMode.AUTO,
    MODE_AWAY: HVACMode.AUTO,
    MODE_HOME: HVACMode.AUTO,
    MODE_FROST_GUARD: HVACMode.OFF,
    MODE_MANUAL: HVACMode.HEAT,
    MODE_OFF: HVACMode.OFF,
    MODE_MAX: HVACMode.HEAT,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MigoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MiGO climate entities."""
    data = entry.runtime_data
    coordinator = data.coordinator

    register_dynamic_entities(
        entry,
        coordinator,
        async_add_entities,
        get_current_ids=lambda: coordinator.rooms,
        create_entities=lambda room_id: [MigoClimate(coordinator=coordinator, room_id=room_id, api=data.api)],
    )


class MigoClimate(MigoRoomControlEntity, ClimateEntity):
    """MiGO Climate entity."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.AUTO]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.PRESET_MODE
    )
    _attr_preset_modes = [PRESET_NORMAL, PRESET_AWAY, PRESET_FROST_GUARD, PRESET_DHW_ONLY, PRESET_BOOST]
    _attr_min_temp = TEMP_MIN
    _attr_max_temp = TEMP_MAX
    _attr_target_temperature_step = TEMP_STEP
    _enable_turn_on_off_backwards_compat = False

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        room_id: str,
        api: MigoApi,
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator, room_id, api)
        self._attr_unique_id = generate_unique_id("climate", room_id)
        self._attr_translation_key = "thermostat"

    @property
    def _hvac_mode_cache_key(self) -> str:
        """Return the optimistic-cache key for this room's HVAC mode."""
        return f"climate_hvac_mode_{self._room_id}"

    @property
    def _preset_mode_cache_key(self) -> str:
        """Return the optimistic-cache key for this room's preset mode."""
        return f"climate_preset_mode_{self._room_id}"

    @property
    def _target_temperature_cache_key(self) -> str:
        """Return the optimistic-cache key for this room's target temperature."""
        return f"climate_target_temperature_{self._room_id}"

    @property
    @override
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return safe_float(self._room_data.get("therm_measured_temperature"))

    @property
    @override
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        cached = self.coordinator.get_cached_value(self._target_temperature_cache_key)
        if cached is not None:
            return float(cached)
        return safe_float(self._room_data.get("therm_setpoint_temperature"))

    @property
    def _home_therm_mode(self) -> str | None:
        """Return the home-level therm_mode (schedule/away/hg).

        This is independent of the room's therm_setpoint_mode: MiGo stacks
        three notions (boiler quick-action mode, home-level Away, and the
        room's own setpoint mode) that a single room field cannot represent.
        See the module docstring in CHANGELOG.md for the forum analysis this
        two-level derivation is based on.
        """
        home_id = self._room_data.get("home_id", "")
        home_data = self.coordinator.homes.get(home_id, {})
        return home_data.get("therm_mode")

    @property
    def _home_is_away(self) -> bool:
        """Return whether Away is active for this room's home.

        Mirrors `helpers.is_home_away()`, used by the Away switch,
        binary_sensor and datetime entities, so this entity doesn't briefly
        disagree with them right after the switch is toggled and before the
        coordinator's next refresh lands (see `MigoApiControlMixin`'s
        optimistic cache). Falls back to the raw home-level `therm_mode` if
        this room's gateway device can't be resolved.
        """
        thermostat_id = get_thermostat_for_room(self.coordinator, self._room_id)
        gateway_id = self.coordinator.devices.get(thermostat_id, {}).get("bridge") if thermostat_id else None
        if not gateway_id:
            return self._home_therm_mode == MODE_AWAY

        gateway_data = self.coordinator.devices.get(gateway_id, {})
        return bool(is_home_away(self.coordinator, gateway_id, gateway_data))

    @property
    @override
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode.

        Checks the optimistic cache first: writes go through
        `_call_api_optimistically` (see `async_set_hvac_mode`), unlike most
        of the rest of this entity, so the mode button reacts immediately
        instead of waiting for the coordinator's next (possibly debounced,
        possibly several-second) refresh - reported live as a long, and
        sometimes total, delay before the card visibly updated after a mode
        change, even though the underlying API call always succeeded.
        """
        cached = self.coordinator.get_cached_value(self._hvac_mode_cache_key)
        if cached is not None:
            return HVACMode(cached)

        room_mode = self._room_data.get("therm_setpoint_mode", MODE_SCHEDULE)

        # An explicit manual/boost override always wins over both mode layers.
        if room_mode in (MODE_MANUAL, MODE_MAX):
            return HVACMode.HEAT

        # Room-level "hg" is MiGo's "DHW only" quick-action, not real frost
        # guard, but it still means the room itself is not being heated.
        if room_mode in (MODE_FROST_GUARD, MODE_OFF):
            return HVACMode.OFF

        # Real frost guard/standby only shows up at the home level.
        if self._home_therm_mode == MODE_FROST_GUARD:
            return HVACMode.OFF

        return MIGO_TO_HVAC_MODE.get(room_mode, HVACMode.AUTO)

    @property
    @override
    def hvac_action(self) -> HVACAction | None:
        """Return the current HVAC action."""
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF

        boiler_status = self._boiler_status
        if boiler_status is not None:
            return HVACAction.HEATING if boiler_status else HVACAction.IDLE

        # Fallback for when the thermostat device data isn't available yet:
        # infer from the temperature delta, as before.
        current = self.current_temperature
        target = self.target_temperature

        if current is not None and target is not None:
            if current < target - 0.5:
                return HVACAction.HEATING
            return HVACAction.IDLE

        return None

    @property
    def _boiler_status(self) -> bool | None:
        """Return the real boiler running state from the thermostat device."""
        thermostat_id = get_thermostat_for_room(self.coordinator, self._room_id)
        if not thermostat_id:
            return None
        return self.coordinator.devices.get(thermostat_id, {}).get("boiler_status")

    async def _write_dhw_only(self, home_id: str, *, cache_key: str, optimistic_value: Any) -> None:
        """Write MiGo's DHW-only quick action: cooling home-wide, plus this room's hg.

        Reported live: after selecting DHW-only from Home Assistant, the
        MiGo app itself didn't show it as active. Confirmed via a live
        capture of the app's own "Eau chaude seulement" action:
        `temperature_control_mode` flips to `"cooling"` home-wide (see
        `MigoApi.set_temperature_control_mode`'s docstring - despite the
        name, not a literal cooling mode) alongside this room's
        `therm_setpoint_mode` going to `"hg"`. Writing the room alone,
        which is all this used to do, never touched that flag, so the app
        never showed it - even though this integration's own optimistic UI
        did, since it only ever checked the room-level value. Shared by
        `async_set_hvac_mode`'s Off branch and the DHW-only preset, which
        write the identical underlying state today, just reached through
        two different controls.

        Deliberately calls `set_temperature_control_mode` (no `therm_mode`
        field at all) as its own separate request, not `set_home_therm_mode`
        with `temperature_control_mode="cooling"` added to it. An earlier
        version of this method paired them in one `sethomedata` call, which
        is exactly the combination reported live (and confirmed against a
        real attempt from this integration, not just theorized) to 403 -
        see `MigoApi.set_temperature_control_mode`'s docstring. Leaving
        `therm_mode` out of this call also sidesteps ever having to guess
        what DHW-only does to an active Away: nothing here can accidentally
        overwrite it either way.

        A stale home-level real Frost guard ("hg") is still cleared first,
        same as before - but now as its own separate `set_home_therm_mode`
        call (the confirmed-safe "heating" + therm_mode combination), never
        combined with the "cooling" call that follows it. Without this,
        `preset_mode`'s own derivation (which checks the home-level mode
        before the room-level one) would go back to reading DHW-only as
        Frost guard whenever this was left over - the same bug already
        fixed once on this exact path.
        """
        if self._home_therm_mode == MODE_FROST_GUARD:
            await self._call_api(
                self._api.set_home_therm_mode,
                home_id=home_id,
                mode=MODE_SCHEDULE,
            )
        await self._call_api(
            self._api.set_temperature_control_mode,
            home_id=home_id,
            mode="cooling",
        )
        await self._call_api_optimistically(
            self._api.set_room_state,
            cache_key=cache_key,
            optimistic_value=optimistic_value,
            home_id=home_id,
            room_id=self._room_id,
            mode=MODE_FROST_GUARD,
        )

    @override
    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        home_id = get_home_id_or_raise(self._room_data, "room", self._room_id)

        _LOGGER.debug("Setting room %s temperature to %s°C", self._room_id, temperature)
        await self._call_api_optimistically(
            self._api.set_temperature,
            cache_key=self._target_temperature_cache_key,
            optimistic_value=temperature,
            home_id=home_id,
            room_id=self._room_id,
            temperature=temperature,
        )
        _LOGGER.debug("Room %s temperature set successfully", self._room_id)

    @override
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode."""
        home_id = get_home_id_or_raise(self._room_data, "room", self._room_id)

        if hvac_mode == HVACMode.HEAT:
            # Heat mode = manual override with configurable duration
            # Get duration from home settings or use default
            home_data = self.coordinator.homes.get(home_id, {})
            duration = home_data.get("therm_setpoint_default_duration", DEFAULT_MANUAL_SETPOINT_DURATION)

            # Keep current target temperature or use a sensible default
            temperature = self.target_temperature or 20.0

            _LOGGER.debug(
                "Setting manual mode for room %s: temp=%s°C, duration=%s min",
                self._room_id,
                temperature,
                duration,
            )
            await self._call_api_optimistically(
                self._api.set_temperature,
                cache_key=self._hvac_mode_cache_key,
                optimistic_value=HVACMode.HEAT.value,
                home_id=home_id,
                room_id=self._room_id,
                temperature=temperature,
                duration=duration,
            )
        elif hvac_mode == HVACMode.AUTO:
            room_mode = self._room_data.get("therm_setpoint_mode")
            if room_mode in (MODE_MANUAL, MODE_MAX, MODE_FROST_GUARD, MODE_OFF):
                # A room-level override left over from a previous Off/
                # DHW-only/Heat/Boost selection (stuck at "hg"/"manual"/
                # "max") is never cleared by the home-level call below -
                # and `hvac_mode`'s own derivation checks the room-level
                # mode before the home-level one, so it kept reporting Off
                # no matter how many times Auto was selected afterward.
                # Reported live and confirmed against a debug-log capture:
                # therm_setpoint_mode stayed "hg" through repeated Auto
                # clicks, only clearing once Heat (a room-level write) was
                # tried instead. Explicitly clear the room back to "home"
                # (not overridden - the API's own term for this, confirmed
                # to be what a cleared override settles back to on its own)
                # before the home-level call below.
                await self._call_api(
                    self._api.set_room_state,
                    home_id=home_id,
                    room_id=self._room_id,
                    mode=MODE_HOME,
                )
            _LOGGER.debug("Setting room %s HVAC mode to auto (migo: schedule)", self._room_id)
            # set_home_therm_mode (sethomedata) directly, not the generic
            # set_mode() dispatcher (which routes "schedule" to the bare
            # setthermmode endpoint) - sethomedata also resets
            # temperature_control_mode back to "heating", clearing a value
            # left over from DHW-only. setthermmode alone doesn't touch
            # that field, which would otherwise keep producing the same
            # "cooling" 403 Away's write used to hit (see
            # MigoApi.set_home_therm_mode's docstring).
            await self._call_api_optimistically(
                self._api.set_home_therm_mode,
                cache_key=self._hvac_mode_cache_key,
                optimistic_value=HVACMode.AUTO.value,
                home_id=home_id,
                mode=MODE_SCHEDULE,
            )
        else:
            # Off: MiGo's DHW-only quick action at the room level (see
            # PRESET_DHW_ONLY's docstring and _write_dhw_only) - the same
            # underlying state, just reached via the HVAC mode wheel
            # instead of the preset dropdown.
            _LOGGER.debug("Setting room %s HVAC mode to off (DHW-only)", self._room_id)
            await self._write_dhw_only(
                home_id,
                cache_key=self._hvac_mode_cache_key,
                optimistic_value=HVACMode.OFF.value,
            )

        _LOGGER.debug("Room %s HVAC mode set successfully", self._room_id)

    @override
    async def async_turn_on(self) -> None:
        """Turn on the thermostat."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    @override
    async def async_turn_off(self) -> None:
        """Turn off the thermostat."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    @property
    @override
    def preset_mode(self) -> str | None:
        """Return the current preset mode.

        Checks the optimistic cache first, same reasoning as `hvac_mode`
        above: writes go through `_call_api_optimistically` (see
        `async_set_preset_mode`) so the preset button reacts immediately.
        """
        cached = self.coordinator.get_cached_value(self._preset_mode_cache_key)
        if cached is not None:
            return str(cached)

        room_mode = self._room_data.get("therm_setpoint_mode", MODE_SCHEDULE)
        home_therm_mode = self._home_therm_mode

        # Away is a home-level flag: `therm_mode == "away"` is the reliable
        # source (room-level "away" is documented by Netatmo but was never
        # observed in community testing). Checked first, before any
        # room-level override (manual, boost, boiler quick-action mode): the
        # app lets you combine Away with Normal/DHW only/manual/boost, and
        # it is the more actionable state when combined with any of them -
        # this must run before the manual/boost checks below, or an active
        # Away never surfaces while either override is also in effect.
        # `_home_is_away` (cache-aware) is used rather than a plain
        # `home_therm_mode == MODE_AWAY` comparison so this doesn't briefly
        # disagree with switch.migo_{home}_away_mode right after it's toggled.
        if self._home_is_away or room_mode == MODE_AWAY:
            return PRESET_AWAY

        # Check if it's a boost (manual mode at max temperature)
        if room_mode == MODE_MANUAL:
            target = self.target_temperature
            if target is not None and target >= TEMP_MAX - 0.5:
                return PRESET_BOOST
            return None

        if room_mode == MODE_MAX:
            return PRESET_BOOST

        # Real frost guard/standby: therm_mode itself is "hg".
        if home_therm_mode == MODE_FROST_GUARD:
            return PRESET_FROST_GUARD

        # MiGo's "DHW only" quick-action: only the room is in "hg", read-only
        # here (see PRESET_DHW_ONLY docstring).
        if room_mode == MODE_FROST_GUARD:
            return PRESET_DHW_ONLY

        # Nothing else applies: no Away, no room-level override, no active
        # boiler quick-action (Frost guard, DHW-only) - the baseline state,
        # the third option in the app's own "Actions rapides" alongside
        # those two.
        return PRESET_NORMAL

    @override
    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode."""
        home_id = get_home_id_or_raise(self._room_data, "room", self._room_id)

        if preset_mode == PRESET_NORMAL:
            # Clears any active boiler quick-action (Frost guard, DHW-only,
            # which also clears a stale "cooling" temperature_control_mode
            # - see MigoApi.set_home_therm_mode) and this room's own
            # override back to the baseline state. Unlike Auto (HVACMode.
            # AUTO), which only clears the room when it detects a specific
            # leftover override, this always clears both explicitly:
            # selecting Normal is a deliberate "reset everything" action,
            # not a mode switch that happens to need cleanup as a side
            # effect. Also clears Away, unlike DHW-only above - Normal is
            # meant as a full reset, matching Auto's existing behavior.
            _LOGGER.debug("Setting room %s to Normal (home schedule, room home)", self._room_id)
            await self._call_api(
                self._api.set_room_state,
                home_id=home_id,
                room_id=self._room_id,
                mode=MODE_HOME,
            )
            await self._call_api_optimistically(
                self._api.set_home_therm_mode,
                cache_key=self._preset_mode_cache_key,
                optimistic_value=preset_mode,
                home_id=home_id,
                mode=MODE_SCHEDULE,
            )
        elif preset_mode == PRESET_BOOST:
            # Boost = force heating at max temperature for 1 hour
            _LOGGER.debug(
                "Setting boost mode for room %s: temp=%s°C, duration=%s min",
                self._room_id,
                TEMP_MAX,
                DEFAULT_BOOST_DURATION,
            )
            await self._call_api_optimistically(
                self._api.set_temperature,
                cache_key=self._preset_mode_cache_key,
                optimistic_value=preset_mode,
                home_id=home_id,
                room_id=self._room_id,
                temperature=TEMP_MAX,
                duration=DEFAULT_BOOST_DURATION,
            )
        elif preset_mode == PRESET_DHW_ONLY:
            # The same underlying state HVACMode.OFF already writes - see
            # PRESET_DHW_ONLY's docstring and _write_dhw_only.
            _LOGGER.debug("Setting room %s to DHW-only", self._room_id)
            await self._write_dhw_only(
                home_id,
                cache_key=self._preset_mode_cache_key,
                optimistic_value=preset_mode,
            )
        elif preset_mode == PRESET_FROST_GUARD:
            # Home-level "hg" via sethomedata (set_home_therm_mode) - not
            # the generic set_mode() dispatcher, which routes "hg" to the
            # room unconditionally, and not the bare setthermmode endpoint
            # either: unlike sethomedata, it doesn't reset
            # temperature_control_mode back to "heating", so a value left
            # over from DHW-only would keep producing the same "cooling"
            # 403 Away's write used to hit (see
            # MigoApi.set_home_therm_mode's docstring).
            if self._room_data.get("therm_setpoint_mode") in (MODE_MANUAL, MODE_MAX):
                # preset_mode's own derivation checks a room-level Manual/
                # Boost override before the home-level mode (an active
                # override shouldn't be silently hidden by an unrelated
                # preset) - same gap as async_set_hvac_mode's Auto branch:
                # a leftover Manual/Boost override would otherwise keep
                # preset_mode stuck reporting Boost/None no matter what was
                # selected here. Clear it first.
                await self._call_api(
                    self._api.set_room_state,
                    home_id=home_id,
                    room_id=self._room_id,
                    mode=MODE_HOME,
                )
            _LOGGER.debug("Setting home %s to Frost guard (home-level hg)", home_id)
            await self._call_api_optimistically(
                self._api.set_home_therm_mode,
                cache_key=self._preset_mode_cache_key,
                optimistic_value=preset_mode,
                home_id=home_id,
                mode=MODE_FROST_GUARD,
            )
        elif preset_mode == PRESET_AWAY:
            # Home-level Away via sethomedata, the same call
            # switch.migo_{home}_away_mode uses, rather than the generic
            # set_mode() dispatcher (which routes through setthermmode, with
            # no endtime parameter, so it can't clear a return time left
            # over from a previous Away period).
            _LOGGER.debug("Setting home %s to Away", home_id)
            await self._call_api_optimistically(
                self._api.set_home_therm_mode,
                cache_key=self._preset_mode_cache_key,
                optimistic_value=preset_mode,
                home_id=home_id,
                mode=MODE_AWAY,
                endtime=None,
            )
        else:
            # Every entry in _attr_preset_modes (Normal, Away, Frost guard,
            # DHW only, Boost) is handled by an explicit branch above, so
            # this is only reached for a preset Home Assistant shouldn't
            # ever pass.
            _LOGGER.error("Unknown preset mode: %s", preset_mode)
            return

        _LOGGER.debug("Room %s preset set successfully", self._room_id)
