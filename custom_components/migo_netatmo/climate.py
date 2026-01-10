"""Climate platform for MiGO integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.climate import (
    PRESET_AWAY,
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

# Custom preset mode names
PRESET_HOT_WATER_ONLY = "hot_water_only"
PRESET_FROST_GUARD = "frost_guard"

# Map preset names to MiGO modes
PRESET_TO_MIGO_MODE: dict[str, str] = {
    PRESET_AWAY: MODE_AWAY,
    PRESET_HOT_WATER_ONLY: MODE_OFF,
    PRESET_FROST_GUARD: MODE_FROST_GUARD,
}

# Map MiGO modes to preset names (None means no preset active)
MIGO_MODE_TO_PRESET: dict[str, str | None] = {
    MODE_AWAY: PRESET_AWAY,
    MODE_OFF: PRESET_HOT_WATER_ONLY,
    MODE_FROST_GUARD: PRESET_FROST_GUARD,
    MODE_SCHEDULE: None,
    MODE_MANUAL: None,
    MODE_HOME: None,
    MODE_MAX: None,
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
    _attr_preset_modes = [PRESET_AWAY, PRESET_HOT_WATER_ONLY, PRESET_FROST_GUARD]
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
        return MIGO_MODE_TO_PRESET.get(mode)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode."""
        home_id = get_home_id_or_log_error(self._room_data, "room", self._room_id)
        if not home_id:
            return

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
