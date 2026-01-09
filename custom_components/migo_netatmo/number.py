"""Number platform for MiGO integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DEVICE_TYPE_GATEWAY,
    DHW_TEMP_MAX,
    DHW_TEMP_MIN,
    DHW_TEMP_STEP,
    HEATING_CURVE_DEFAULT,
    HEATING_CURVE_MAX,
    HEATING_CURVE_MIN,
    HEATING_CURVE_STEP,
    TEMP_OFFSET_MAX,
    TEMP_OFFSET_MIN,
    TEMP_OFFSET_STEP,
)
from .entity import MigoControlEntity, MigoRoomEntity
from .helpers import generate_unique_id, get_devices_by_type, get_home_id_or_log_error

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

    # Create number entities for each gateway
    for device_id in get_devices_by_type(coordinator, DEVICE_TYPE_GATEWAY):
        # Heating curve (slope)
        entities.append(
            MigoHeatingCurveNumber(
                coordinator=coordinator,
                device_id=device_id,
                api=data.api,
            )
        )
        # DHW Temperature
        entities.append(
            MigoDHWTemperatureNumber(
                coordinator=coordinator,
                device_id=device_id,
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


class MigoHeatingCurveNumber(MigoControlEntity, NumberEntity):
    """MiGO Heating Curve (slope) number entity."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "heating_curve"
    _attr_native_min_value = HEATING_CURVE_MIN / 10  # 0.5
    _attr_native_max_value = HEATING_CURVE_MAX / 10  # 3.5
    _attr_native_step = HEATING_CURVE_STEP / 10  # 0.1
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:chart-bell-curve-cumulative"

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
        api: MigoApi,
    ) -> None:
        """Initialize the heating curve number entity."""
        super().__init__(coordinator, device_id, api)
        self._attr_unique_id = generate_unique_id("heating_curve", device_id)

    @property
    def _cache_key(self) -> str:
        """Return the cache key for this entity."""
        return f"heating_curve_{self._device_id}"

    @property
    def native_value(self) -> float | None:
        """Return the current heating curve slope value."""
        # Check optimistic cache first (API doesn't return this value)
        cached = self.coordinator.get_cached_value(self._cache_key)
        if cached is not None:
            return cached
        # Fallback to API data (if ever returned)
        slope = self._device_data.get("heating_curve_slope")
        if slope is not None:
            return slope / 10
        return HEATING_CURVE_DEFAULT / 10

    async def async_set_native_value(self, value: float) -> None:
        """Set the heating curve slope."""
        # Convert UI value (e.g., 1.4) to API value (e.g., 14)
        slope = int(value * 10)

        _LOGGER.debug(
            "Setting heating curve to %s (api: %s) for device %s",
            value,
            slope,
            self._device_id,
        )
        await self._call_api_and_refresh(
            self._api.set_heating_curve,
            device_id=self._device_id,
            slope=slope,
        )
        # Store in optimistic cache (API doesn't return this value)
        self.coordinator.set_cached_value(self._cache_key, value)
        _LOGGER.debug("Heating curve set for device %s", self._device_id)


class MigoDHWTemperatureNumber(MigoControlEntity, NumberEntity):
    """MiGO Domestic Hot Water temperature number entity."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "dhw_temperature"
    _attr_native_min_value = DHW_TEMP_MIN  # 45
    _attr_native_max_value = DHW_TEMP_MAX  # 65
    _attr_native_step = DHW_TEMP_STEP  # 1
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:water-thermometer"

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
        api: MigoApi,
    ) -> None:
        """Initialize the DHW temperature number entity."""
        super().__init__(coordinator, device_id, api)
        self._attr_unique_id = generate_unique_id("dhw_temperature", device_id)

    @property
    def _cache_key(self) -> str:
        """Return the cache key for this entity."""
        return f"dhw_temp_{self._device_id}"

    @property
    def native_value(self) -> int | None:
        """Return the current DHW temperature."""
        # Check optimistic cache first (API doesn't return this value)
        cached = self.coordinator.get_cached_value(self._cache_key)
        if cached is not None:
            return cached
        # Fallback to API data (if ever returned)
        return self._device_data.get("dhw_setpoint_temperature")

    async def async_set_native_value(self, value: float) -> None:
        """Set the DHW temperature."""
        home_id = get_home_id_or_log_error(self._device_data, "device", self._device_id)
        if not home_id:
            return

        _LOGGER.debug("Setting DHW temperature to %s°C for device %s", int(value), self._device_id)
        await self._call_api_and_refresh(
            self._api.set_dhw_temperature,
            home_id=home_id,
            module_id=self._device_id,
            temperature=int(value),
        )
        # Store in optimistic cache (API doesn't return this value)
        self.coordinator.set_cached_value(self._cache_key, int(value))
        _LOGGER.debug("DHW temperature set for device %s", self._device_id)


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
