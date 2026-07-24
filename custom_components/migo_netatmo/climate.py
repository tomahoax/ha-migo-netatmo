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
from .entity import MigoRoomControlEntity, register_dynamic_entities
from .helpers import generate_unique_id, get_home_id_or_raise, safe_float

if TYPE_CHECKING:
    from . import MigoConfigEntry
    from .api import MigoApi

_LOGGER = logging.getLogger(__name__)

# Serialise write commands against the cloud API
PARALLEL_UPDATES = 1

# Custom preset mode name for frost guard
PRESET_FROST_GUARD = "frost_guard"

# Map MiGO modes to HVAC modes
MIGO_TO_HVAC_MODE: dict[str, HVACMode] = {
    MODE_SCHEDULE: HVACMode.AUTO,
    MODE_AWAY: HVACMode.AUTO,
    MODE_FROST_GUARD: HVACMode.OFF,
    MODE_MANUAL: HVACMode.HEAT,
    MODE_OFF: HVACMode.OFF,
    MODE_MAX: HVACMode.HEAT,
    MODE_HOME: HVACMode.HEAT,
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
    _attr_preset_modes = [PRESET_AWAY, PRESET_FROST_GUARD, PRESET_BOOST]
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
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return safe_float(self._room_data.get("therm_measured_temperature"))

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        return safe_float(self._room_data.get("therm_setpoint_temperature"))

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode."""
        mode = self._room_data.get("therm_setpoint_mode", MODE_SCHEDULE)
        return MIGO_TO_HVAC_MODE.get(mode, HVACMode.AUTO)

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current HVAC action."""
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF

        current = self.current_temperature
        target = self.target_temperature

        if current is not None and target is not None:
            if current < target - 0.5:
                return HVACAction.HEATING
            return HVACAction.IDLE

        return None

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        home_id = get_home_id_or_raise(self._room_data, "room", self._room_id)

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
        mode = self._room_data.get("therm_setpoint_mode", MODE_SCHEDULE)

        # Check if it's a boost (manual mode at max temperature)
        if mode == MODE_MANUAL:
            target = self.target_temperature
            if target is not None and target >= TEMP_MAX - 0.5:
                return PRESET_BOOST

        return MIGO_MODE_TO_PRESET.get(mode)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode."""
        home_id = get_home_id_or_raise(self._room_data, "room", self._room_id)

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
