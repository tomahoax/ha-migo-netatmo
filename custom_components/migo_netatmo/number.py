"""Number platform for MiGO integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, override

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DEFAULT_DHW_TEMPERATURE,
    DEFAULT_HEATING_CURVE,
    DEFAULT_HYSTERESIS,
    DEFAULT_MANUAL_SETPOINT_DURATION,
    DEFAULT_TEMP_OFFSET,
    DEVICE_TYPE_GATEWAY,
    DHW_TEMP_MAX,
    DHW_TEMP_MIN,
    DHW_TEMP_STEP,
    HEATING_CURVE_MAX,
    HEATING_CURVE_MIN,
    HEATING_CURVE_STEP,
    HYSTERESIS_MAX,
    HYSTERESIS_MIN,
    HYSTERESIS_STEP,
    MANUAL_SETPOINT_DURATION_MAX,
    MANUAL_SETPOINT_DURATION_MIN,
    MANUAL_SETPOINT_DURATION_STEP,
    TEMP_OFFSET_MAX,
    TEMP_OFFSET_MIN,
    TEMP_OFFSET_STEP,
)
from .entity import (
    MigoGatewayControlEntity,
    MigoRoomControlEntity,
    MigoThermostatHomeControlEntity,
)
from .entity_mixin import _MigoCachedValueMixin
from .entity_setup import register_dynamic_entities
from .helpers import generate_unique_id, get_devices_by_type, get_home_id_or_raise
from .models import ModuleData

if TYPE_CHECKING:
    from . import MigoConfigEntry
    from .api import MigoApi
    from .coordinator import MigoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Serialise write commands against the cloud API
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MigoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MiGO number entities."""
    data = entry.runtime_data
    coordinator = data.coordinator

    # Manual setpoint duration entity for each home
    register_dynamic_entities(
        entry,
        coordinator,
        async_add_entities,
        get_current_ids=lambda: coordinator.homes,
        create_entities=lambda home_id: [
            MigoManualSetpointDurationNumber(coordinator=coordinator, home_id=home_id, api=data.api)
        ],
    )

    def _gateway_numbers(device_id: str) -> list[NumberEntity]:
        numbers: list[NumberEntity] = [
            MigoDHWTemperatureNumber(coordinator=coordinator, device_id=device_id, api=data.api)
        ]
        # Hysteresis and heating curve are gateway parameters, assigned to the
        # Thermostat device, hence the extra home_id lookup.
        home_id = coordinator.devices.get(device_id, {}).get("home_id")
        if home_id:
            numbers.append(
                MigoHysteresisNumber(coordinator=coordinator, home_id=home_id, device_id=device_id, api=data.api)
            )
            numbers.append(
                MigoHeatingCurveNumber(coordinator=coordinator, home_id=home_id, device_id=device_id, api=data.api)
            )
        return numbers

    register_dynamic_entities(
        entry,
        coordinator,
        async_add_entities,
        get_current_ids=lambda: get_devices_by_type(coordinator, DEVICE_TYPE_GATEWAY),
        create_entities=_gateway_numbers,
    )

    def _room_numbers(room_id: str) -> list[NumberEntity]:
        home_id = coordinator.rooms.get(room_id, {}).get("home_id")
        if not home_id:
            return []
        return [MigoTemperatureOffsetNumber(coordinator=coordinator, room_id=room_id, home_id=home_id, api=data.api)]

    register_dynamic_entities(
        entry,
        coordinator,
        async_add_entities,
        get_current_ids=lambda: coordinator.rooms,
        create_entities=_room_numbers,
    )


class MigoManualSetpointDurationNumber(_MigoCachedValueMixin, MigoThermostatHomeControlEntity, NumberEntity):
    """MiGO Manual setpoint default duration number entity."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "manual_setpoint_duration"
    _attr_native_min_value = MANUAL_SETPOINT_DURATION_MIN  # 5 minutes
    _attr_native_max_value = MANUAL_SETPOINT_DURATION_MAX  # 720 minutes (12h)
    _attr_native_step = MANUAL_SETPOINT_DURATION_STEP  # 5 minutes
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        home_id: str,
        api: MigoApi,
    ) -> None:
        """Initialize the manual setpoint duration number entity."""
        super().__init__(coordinator, home_id, api)
        self._attr_unique_id = generate_unique_id("manual_setpoint_duration", home_id)

    @property
    def _cache_key(self) -> str:
        """Return the cache key for this entity."""
        return f"manual_setpoint_duration_{self._home_id}"

    def _native_value_fallback(self) -> int:
        """Return the API-derived value, falling back to the documented default."""
        # therm_setpoint_default_duration is in minutes
        home_data = self.coordinator.homes.get(self._home_id, {})
        duration_minutes = home_data.get("therm_setpoint_default_duration")
        if duration_minutes is not None:
            return int(duration_minutes)
        # Default to 3 hours (180 minutes) as shown in the app
        return DEFAULT_MANUAL_SETPOINT_DURATION

    @property
    @override
    def native_value(self) -> int | None:
        """Return the current manual setpoint duration in minutes."""
        return int(self._resolve_cached_value(self._native_value_fallback))

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Set the manual setpoint duration."""
        minutes = int(value)

        _LOGGER.debug(
            "Setting manual setpoint duration to %s minutes for home %s",
            minutes,
            self._home_id,
        )
        await self._call_api_optimistically(
            self._api.set_manual_setpoint_duration,
            cache_key=self._cache_key,
            optimistic_value=minutes,
            home_id=self._home_id,
            duration=minutes,
        )
        _LOGGER.debug("Manual setpoint duration set for home %s", self._home_id)


class MigoTemperatureOffsetNumber(_MigoCachedValueMixin, MigoRoomControlEntity, NumberEntity):
    """MiGO Temperature offset number entity for rooms."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "temperature_offset"
    _attr_native_min_value = TEMP_OFFSET_MIN  # -5.0
    _attr_native_max_value = TEMP_OFFSET_MAX  # 5.0
    _attr_native_step = TEMP_OFFSET_STEP  # 0.5
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        room_id: str,
        home_id: str,
        api: MigoApi,
    ) -> None:
        """Initialize the temperature offset number entity."""
        super().__init__(coordinator, room_id, api)
        self._home_id = home_id
        self._attr_unique_id = generate_unique_id("temp_offset", room_id)

    @property
    def _cache_key(self) -> str:
        """Return the cache key for this entity."""
        return f"temp_offset_{self._room_id}"

    def _native_value_fallback(self) -> float:
        """Return the API-derived value, falling back to the documented default.

        Only therm_setpoint_offset (the user-configured value) is used:
        measure_offset_NAVaillant_temperature is hardware sensor calibration,
        not the user-configurable offset, so it is not read here.
        """
        offset = self._room_data.get("therm_setpoint_offset")
        if offset is not None:
            return float(offset)
        return DEFAULT_TEMP_OFFSET

    @property
    @override
    def native_value(self) -> float | None:
        """Return the current temperature offset."""
        return self._resolve_cached_value(self._native_value_fallback)

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Set the temperature offset."""
        _LOGGER.debug("Setting temperature offset to %s°C for room %s", value, self._room_id)
        await self._call_api_optimistically(
            self._api.set_temperature_offset,
            cache_key=self._cache_key,
            optimistic_value=value,
            home_id=self._home_id,
            room_id=self._room_id,
            offset=value,
        )
        _LOGGER.debug("Temperature offset set for room %s", self._room_id)


class MigoDHWTemperatureNumber(_MigoCachedValueMixin, MigoGatewayControlEntity, NumberEntity):
    """MiGO Domestic Hot Water temperature number entity."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "dhw_temperature"
    _attr_native_min_value = DHW_TEMP_MIN  # 45°C
    _attr_native_max_value = DHW_TEMP_MAX  # 60°C
    _attr_native_step = DHW_TEMP_STEP  # 1°C
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.SLIDER

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
        return f"dhw_temperature_{self._device_id}"

    def _native_value_fallback(self) -> int:
        """Return the API-derived value, falling back to the documented default."""
        temp = self._device_data.get("dhw_setpoint_temperature")
        if temp is not None:
            return int(temp)
        # Default to 60°C as shown in the screenshot
        return DEFAULT_DHW_TEMPERATURE

    @property
    @override
    def native_value(self) -> int | None:
        """Return the current DHW temperature."""
        return int(self._resolve_cached_value(self._native_value_fallback))

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Set the DHW temperature."""
        temperature = int(value)
        home_id = get_home_id_or_raise(self._device_data, "device", self._device_id)

        _LOGGER.debug(
            "Setting DHW temperature to %s°C for device %s",
            temperature,
            self._device_id,
        )
        await self._call_api_optimistically(
            self._api.set_dhw_temperature,
            cache_key=self._cache_key,
            optimistic_value=temperature,
            home_id=home_id,
            module_id=self._device_id,
            temperature=temperature,
        )
        _LOGGER.debug("DHW temperature set for device %s", self._device_id)


class MigoHysteresisNumber(_MigoCachedValueMixin, MigoThermostatHomeControlEntity, NumberEntity):
    """MiGO Hysteresis threshold number entity.

    Note: Although hysteresis is a gateway parameter, it's assigned to the
    Thermostat device per user preference.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "hysteresis"
    _attr_native_min_value = HYSTERESIS_MIN  # 0.1°C
    _attr_native_max_value = HYSTERESIS_MAX  # 2.0°C
    _attr_native_step = HYSTERESIS_STEP  # 0.1°C
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        home_id: str,
        device_id: str,
        api: MigoApi,
    ) -> None:
        """Initialize the hysteresis number entity."""
        super().__init__(coordinator, home_id, api)
        self._device_id = device_id  # Gateway device ID for API calls
        self._attr_unique_id = generate_unique_id("hysteresis", device_id)

    @property
    def _device_data(self) -> ModuleData:
        """Get current gateway device data."""
        return self.coordinator.devices.get(self._device_id, {})

    @property
    def _cache_key(self) -> str:
        """Return the cache key for this entity."""
        return f"hysteresis_{self._device_id}"

    def _native_value_fallback(self) -> float:
        """Return the API-derived value, falling back to the documented default.

        Hysteresis in Celsius is the deadband value plus one, over ten.

        Reported live: this entity doesn't pick up a hysteresis change made
        from the MiGo app, even though writing from Home Assistant does
        reach the API correctly. Investigated: `simple_heating_algo_deadband`
        is documented (see docs/api/reference.md) to be echoed back on
        homestatus, but a live homestatus capture taken during later
        development didn't actually contain it for this gateway module -
        `self._device_data.get(...)` below has, in practice, never had
        anything to return. Kept in case a future capture proves the field
        does show up under some condition; until then this always falls
        through to the optimistic cache (right after a write from Home
        Assistant) or DEFAULT_HYSTERESIS - same write-only situation as
        `MigoHeatingCurveNumber` below.
        """
        deadband = self._device_data.get("simple_heating_algo_deadband")
        if deadband is not None:
            return round((deadband + 1) / 10, 1)
        # Default to 1.6°C (deadband=15) as seen in typical configuration
        return DEFAULT_HYSTERESIS

    @property
    @override
    def native_value(self) -> float | None:
        """Return the current hysteresis threshold."""
        return self._resolve_cached_value(self._native_value_fallback)

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Set the hysteresis threshold."""
        hysteresis = round(value, 1)

        _LOGGER.debug(
            "Setting hysteresis to %s°C for device %s",
            hysteresis,
            self._device_id,
        )
        await self._call_api_optimistically(
            self._api.set_hysteresis,
            cache_key=self._cache_key,
            optimistic_value=hysteresis,
            device_id=self._device_id,
            hysteresis=hysteresis,
        )
        _LOGGER.debug("Hysteresis set for device %s", self._device_id)


class MigoHeatingCurveNumber(_MigoCachedValueMixin, MigoThermostatHomeControlEntity, NumberEntity):
    """MiGO Heating curve (slope) number entity.

    Note: Although heating curve is a gateway parameter, it's assigned to the
    Thermostat device per user preference.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "heating_curve"
    _attr_native_min_value = HEATING_CURVE_MIN  # 0.0
    _attr_native_max_value = HEATING_CURVE_MAX  # 5.0
    _attr_native_step = HEATING_CURVE_STEP  # 0.1
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        home_id: str,
        device_id: str,
        api: MigoApi,
    ) -> None:
        """Initialize the heating curve number entity."""
        super().__init__(coordinator, home_id, api)
        self._device_id = device_id  # Gateway device ID for API calls
        self._attr_unique_id = generate_unique_id("heating_curve", device_id)

    @property
    def _device_data(self) -> ModuleData:
        """Get current gateway device data."""
        return self.coordinator.devices.get(self._device_id, {})

    @property
    def _cache_key(self) -> str:
        """Return the cache key for this entity."""
        return f"heating_curve_{self._device_id}"

    def _native_value_fallback(self) -> float:
        """Return the API-derived value, falling back to the documented default.

        Write-only setting: `heating_curve` is never present in
        `homesdata`/`homestatus`/`getconfigs` (confirmed via a live
        debug-log capture across all three), so `self._device_data.get(...)`
        below never actually has anything to return - it's kept in case a
        future capture ever finds it echoed back somewhere, but in practice
        this always falls through to the optimistic cache (right after a
        write from Home Assistant) or DEFAULT_HEATING_CURVE otherwise - see
        the constant's own comment in const.py on why that's not a real
        factory default, just this installation's calibrated value.
        """
        # slope in UI = api_slope / 10
        api_slope = self._device_data.get("heating_curve")
        if api_slope is not None:
            return round(api_slope / 10, 1)
        return DEFAULT_HEATING_CURVE

    @property
    @override
    def native_value(self) -> float | None:
        """Return the current heating curve slope."""
        return self._resolve_cached_value(self._native_value_fallback)

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Set the heating curve slope."""
        slope = round(value, 1)

        _LOGGER.debug(
            "Setting heating curve to %s for device %s",
            slope,
            self._device_id,
        )
        await self._call_api_optimistically(
            self._api.set_heating_curve,
            cache_key=self._cache_key,
            optimistic_value=slope,
            device_id=self._device_id,
            slope=slope,
        )
        _LOGGER.debug("Heating curve set for device %s", self._device_id)
