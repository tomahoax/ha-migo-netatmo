"""Number platform for MiGO integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    MANUAL_SETPOINT_DURATION_MAX,
    MANUAL_SETPOINT_DURATION_MIN,
    MANUAL_SETPOINT_DURATION_STEP,
    TEMP_OFFSET_MAX,
    TEMP_OFFSET_MIN,
    TEMP_OFFSET_STEP,
)
from .entity import MigoHomeEntity, MigoRoomEntity
from .helpers import generate_unique_id

if TYPE_CHECKING:
    from . import MigoConfigEntry
    from .api import MigoApi
    from .coordinator import MigoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MigoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MiGO number entities."""
    data = entry.runtime_data
    coordinator = data.coordinator

    entities: list[NumberEntity] = []

    # Create manual setpoint duration entity for each home
    for home_id in coordinator.homes:
        entities.append(
            MigoManualSetpointDurationNumber(
                coordinator=coordinator,
                home_id=home_id,
                api=data.api,
            )
        )

    # Create temperature offset entities for each room
    for room_id in coordinator.rooms:
        room_data = coordinator.rooms[room_id]
        home_id = room_data.get("home_id")
        if home_id:
            entities.append(
                MigoTemperatureOffsetNumber(
                    coordinator=coordinator,
                    room_id=room_id,
                    home_id=home_id,
                    api=data.api,
                )
            )

    async_add_entities(entities)


class MigoManualSetpointDurationNumber(MigoHomeEntity, NumberEntity):
    """MiGO Manual setpoint default duration number entity."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "manual_setpoint_duration"
    _attr_native_min_value = MANUAL_SETPOINT_DURATION_MIN // 60  # 5 minutes
    _attr_native_max_value = MANUAL_SETPOINT_DURATION_MAX // 60  # 720 minutes (12h)
    _attr_native_step = MANUAL_SETPOINT_DURATION_STEP // 60  # 5 minutes
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:timer-cog-outline"

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        home_id: str,
        api: MigoApi,
    ) -> None:
        """Initialize the manual setpoint duration number entity."""
        super().__init__(coordinator, home_id)
        self._api = api
        self._attr_unique_id = generate_unique_id("manual_setpoint_duration", home_id)

    @property
    def _cache_key(self) -> str:
        """Return the cache key for this entity."""
        return f"manual_setpoint_duration_{self._home_id}"

    @property
    def native_value(self) -> int | None:
        """Return the current manual setpoint duration in minutes."""
        # Check optimistic cache first
        cached = self.coordinator.get_cached_value(self._cache_key)
        if cached is not None:
            return cached
        # Fallback to API data (therm_setpoint_default_duration is in seconds)
        home_data = self.coordinator.homes.get(self._home_id, {})
        duration_seconds = home_data.get("therm_setpoint_default_duration")
        if duration_seconds is not None:
            return duration_seconds // 60
        # Default to 3 hours (180 minutes) as shown in the app
        return 180

    async def async_set_native_value(self, value: float) -> None:
        """Set the manual setpoint duration."""
        minutes = int(value)
        seconds = minutes * 60

        _LOGGER.debug(
            "Setting manual setpoint duration to %s minutes (%s seconds) for home %s",
            minutes,
            seconds,
            self._home_id,
        )
        await self._api.set_manual_setpoint_duration(
            home_id=self._home_id,
            duration=seconds,
        )
        # Store in optimistic cache (in minutes for display)
        self.coordinator.set_cached_value(self._cache_key, minutes)
        _LOGGER.debug("Manual setpoint duration set for home %s", self._home_id)
        await self.coordinator.async_request_refresh()


class MigoTemperatureOffsetNumber(MigoRoomEntity, NumberEntity):
    """MiGO Temperature offset number entity for rooms."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "temperature_offset"
    _attr_native_min_value = TEMP_OFFSET_MIN  # -5.0
    _attr_native_max_value = TEMP_OFFSET_MAX  # 5.0
    _attr_native_step = TEMP_OFFSET_STEP  # 0.5
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:thermometer-plus"

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        room_id: str,
        home_id: str,
        api: MigoApi,
    ) -> None:
        """Initialize the temperature offset number entity."""
        super().__init__(coordinator, room_id)
        self._home_id = home_id
        self._api = api
        self._attr_unique_id = generate_unique_id("temp_offset", room_id)

    @property
    def _cache_key(self) -> str:
        """Return the cache key for this entity."""
        return f"temp_offset_{self._room_id}"

    @property
    def native_value(self) -> float | None:
        """Return the current temperature offset."""
        # Check optimistic cache first (API doesn't return this value)
        cached = self.coordinator.get_cached_value(self._cache_key)
        if cached is not None:
            return cached
        # Fallback to API data (if ever returned)
        # Key can be "measure_offset_NAVaillant_temperature" or "therm_setpoint_offset"
        offset = self._room_data.get("measure_offset_NAVaillant_temperature")
        if offset is None:
            offset = self._room_data.get("therm_setpoint_offset")
        if offset is not None:
            return float(offset)
        return 0.0

    async def async_set_native_value(self, value: float) -> None:
        """Set the temperature offset."""
        _LOGGER.debug("Setting temperature offset to %s°C for room %s", value, self._room_id)
        await self._api.set_temperature_offset(
            home_id=self._home_id,
            room_id=self._room_id,
            offset=value,
        )
        # Store in optimistic cache (API doesn't return this value)
        self.coordinator.set_cached_value(self._cache_key, value)
        _LOGGER.debug("Temperature offset set for room %s", self._room_id)
        await self.coordinator.async_request_refresh()
