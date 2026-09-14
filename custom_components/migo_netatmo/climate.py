"""Climate platform for MiGO integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

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
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DEFAULT_BOOST_DURATION,
    DEFAULT_MANUAL_SETPOINT_DURATION,
    DEVICE_TYPE_THERMOSTAT,
    DOMAIN,
    MANUFACTURER,
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
from .helpers import get_home_id_or_log_error, get_thermostat_for_room, safe_float

if TYPE_CHECKING:
    from . import MigoConfigEntry
    from .api import MigoApi

_LOGGER = logging.getLogger(__name__)

# Custom preset mode names for MiGO-specific states
PRESET_FROST_GUARD = "frost_guard"
# Read-only: MiGo's "DHW only" boiler quick-action shows up as the room's
# therm_setpoint_mode being "hg" while the home's therm_mode stays "schedule"
# (as opposed to real frost guard/standby, where therm_mode itself is "hg").
# There is no known write path for it distinct from PRESET_FROST_GUARD.
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

HVAC_TO_MIGO_MODE: dict[HVACMode, str] = {
    HVACMode.AUTO: MODE_SCHEDULE,
    HVACMode.HEAT: MODE_MANUAL,
    HVACMode.OFF: MODE_FROST_GUARD,
}

# Map preset names to MiGO modes (boost is handled separately)
PRESET_TO_MIGO_MODE: dict[str, str] = {
    PRESET_AWAY: MODE_AWAY,
    PRESET_FROST_GUARD: MODE_FROST_GUARD,
}

# Map MiGO modes to preset names (None means no preset active)
MIGO_MODE_TO_PRESET: dict[str, str | None] = {
    MODE_AWAY: PRESET_AWAY,
    MODE_FROST_GUARD: PRESET_FROST_GUARD,
    MODE_SCHEDULE: None,
    MODE_MANUAL: None,  # Could be boost, checked separately
    MODE_HOME: None,
    MODE_MAX: None,
    MODE_OFF: None,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MigoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MiGO climate entities."""
    data = entry.runtime_data
    coordinator = data.coordinator

    entities: list[MigoClimate] = []

    for room_id in coordinator.rooms:
        entities.append(
            MigoClimate(
                coordinator=coordinator,
                room_id=room_id,
                api=data.api,
            )
        )

    async_add_entities(entities)


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
    _attr_preset_modes = [PRESET_AWAY, PRESET_FROST_GUARD, PRESET_DHW_ONLY, PRESET_BOOST]
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
        self._attr_unique_id = f"migo_netatmo_climate_{room_id}"
        self._attr_translation_key = "thermostat"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info - climate belongs to thermostat device."""
        thermostat_id = get_thermostat_for_room(self.coordinator, self._room_id)
        if thermostat_id:
            thermostat_data = self.coordinator.devices.get(thermostat_id, {})
            home_id = self._room_data.get("home_id", "")
            home_data = self.coordinator.homes.get(home_id, {})
            home_name = home_data.get("name", "MiGO")

            # Get the gateway ID for via_device
            gateway_id = thermostat_data.get("bridge")

            info = DeviceInfo(
                identifiers={(DOMAIN, thermostat_id)},
                name=f"{home_name} Thermostat",
                manufacturer=MANUFACTURER,
                model=DEVICE_TYPE_THERMOSTAT,
            )

            if gateway_id:
                info["via_device"] = (DOMAIN, gateway_id)

            if firmware := thermostat_data.get("firmware_revision"):
                info["sw_version"] = str(firmware)

            return info

        # Fallback to parent implementation
        return super().device_info

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return safe_float(self._room_data.get("therm_measured_temperature"))

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
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
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode."""
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

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        home_id = get_home_id_or_log_error(self._room_data, "room", self._room_id)
        if not home_id:
            return

        _LOGGER.debug("Setting room %s temperature to %s°C", self._room_id, temperature)
        await self._call_api_and_refresh(
            self._api.set_temperature,
            home_id=home_id,
            room_id=self._room_id,
            temperature=temperature,
        )
        _LOGGER.debug("Room %s temperature set successfully", self._room_id)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode."""
        home_id = get_home_id_or_log_error(self._room_data, "room", self._room_id)
        if not home_id:
            return

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
            await self._call_api_and_refresh(
                self._api.set_temperature,
                home_id=home_id,
                room_id=self._room_id,
                temperature=temperature,
                duration=duration,
            )
        else:
            # Auto or Off
            migo_mode = HVAC_TO_MIGO_MODE.get(hvac_mode, MODE_SCHEDULE)
            _LOGGER.debug(
                "Setting room %s HVAC mode to %s (migo: %s)",
                self._room_id,
                hvac_mode,
                migo_mode,
            )
            await self._call_api_and_refresh(
                self._api.set_mode,
                home_id=home_id,
                room_id=self._room_id,
                mode=migo_mode,
            )

        _LOGGER.debug("Room %s HVAC mode set successfully", self._room_id)

    async def async_turn_on(self) -> None:
        """Turn on the thermostat."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        """Turn off the thermostat."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode."""
        room_mode = self._room_data.get("therm_setpoint_mode", MODE_SCHEDULE)

        # Check if it's a boost (manual mode at max temperature)
        if room_mode == MODE_MANUAL:
            target = self.target_temperature
            if target is not None and target >= TEMP_MAX - 0.5:
                return PRESET_BOOST
            return None

        if room_mode == MODE_MAX:
            return PRESET_BOOST

        home_therm_mode = self._home_therm_mode

        # Away is a home-level flag: `therm_mode == "away"` is the reliable
        # source (room-level "away" is documented by Netatmo but was never
        # observed in community testing). Checked first because it is
        # independent of the boiler quick-action mode below - the app lets
        # you combine Away with any of Normal/DHW only/Frost guard.
        if MODE_AWAY in (home_therm_mode, room_mode):
            return PRESET_AWAY

        # Real frost guard/standby: therm_mode itself is "hg".
        if home_therm_mode == MODE_FROST_GUARD:
            return PRESET_FROST_GUARD

        # MiGo's "DHW only" quick-action: only the room is in "hg", read-only
        # here (see PRESET_DHW_ONLY docstring).
        if room_mode == MODE_FROST_GUARD:
            return PRESET_DHW_ONLY

        return MIGO_MODE_TO_PRESET.get(room_mode)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode."""
        home_id = get_home_id_or_log_error(self._room_data, "room", self._room_id)
        if not home_id:
            return

        if preset_mode == PRESET_BOOST:
            # Boost = force heating at max temperature for 1 hour
            _LOGGER.debug(
                "Setting boost mode for room %s: temp=%s°C, duration=%s min",
                self._room_id,
                TEMP_MAX,
                DEFAULT_BOOST_DURATION,
            )
            await self._call_api_and_refresh(
                self._api.set_temperature,
                home_id=home_id,
                room_id=self._room_id,
                temperature=TEMP_MAX,
                duration=DEFAULT_BOOST_DURATION,
            )
        elif preset_mode == PRESET_DHW_ONLY:
            # Read-only: no known API call sets "DHW only" independently of
            # the boiler quick-action mode. See PRESET_DHW_ONLY's docstring.
            _LOGGER.error(
                "Preset '%s' is read-only and cannot be set from Home Assistant (no known MiGo API call for it)",
                PRESET_DHW_ONLY,
            )
            return
        else:
            migo_mode = PRESET_TO_MIGO_MODE.get(preset_mode)
            if not migo_mode:
                _LOGGER.error("Unknown preset mode: %s", preset_mode)
                return

            _LOGGER.debug(
                "Setting room %s preset to %s (migo: %s)",
                self._room_id,
                preset_mode,
                migo_mode,
            )
            await self._call_api_and_refresh(
                self._api.set_mode,
                home_id=home_id,
                room_id=self._room_id,
                mode=migo_mode,
            )

        _LOGGER.debug("Room %s preset set successfully", self._room_id)
