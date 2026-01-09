"""Select platform for MiGO integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DEVICE_TYPE_GATEWAY,
    HEATING_TYPES,
    MODE_AWAY,
    MODE_FROST_GUARD,
    MODE_SCHEDULE,
    SCHEDULE_TYPE_THERM,
)
from .entity import MigoControlEntity, MigoHomeControlEntity
from .helpers import generate_unique_id, get_devices_by_type

if TYPE_CHECKING:
    from . import MigoConfigEntry
    from .api import MigoApi
    from .coordinator import MigoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Thermostat mode options
THERM_MODE_OPTIONS: list[str] = [MODE_SCHEDULE, MODE_AWAY, MODE_FROST_GUARD]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MigoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MiGO select entities."""
    data = entry.runtime_data
    coordinator = data.coordinator

    entities: list[SelectEntity] = []

    for home_id, home_data in coordinator.homes.items():
        # Thermostat mode select
        entities.append(
            MigoThermModeSelect(
                coordinator=coordinator,
                home_id=home_id,
                api=data.api,
            )
        )

        # Schedule select (only if schedules are available)
        schedules = home_data.get("schedules", [])
        therm_schedules = [s for s in schedules if s.get("type") == SCHEDULE_TYPE_THERM]
        if therm_schedules:
            entities.append(
                MigoScheduleSelect(
                    coordinator=coordinator,
                    home_id=home_id,
                    api=data.api,
                )
            )

    # Create heating type select for each gateway
    for device_id in get_devices_by_type(coordinator, DEVICE_TYPE_GATEWAY):
        entities.append(
            MigoHeatingTypeSelect(
                coordinator=coordinator,
                device_id=device_id,
                api=data.api,
            )
        )

    async_add_entities(entities)


class MigoThermModeSelect(MigoHomeControlEntity, SelectEntity):
    """MiGO Thermostat mode select entity."""

    _attr_translation_key = "therm_mode"

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        home_id: str,
        api: MigoApi,
    ) -> None:
        """Initialize the thermostat mode select entity."""
        super().__init__(coordinator, home_id, api)
        self._attr_unique_id = generate_unique_id("therm_mode", home_id)
        self._attr_options = THERM_MODE_OPTIONS

    @property
    def current_option(self) -> str | None:
        """Return the current thermostat mode."""
        return self._home_data.get("therm_mode")

    async def async_select_option(self, option: str) -> None:
        """Change the thermostat mode."""
        if option not in THERM_MODE_OPTIONS:
            _LOGGER.error("Invalid therm mode: %s", option)
            return

        _LOGGER.debug("Setting therm mode to %s for home %s", option, self._home_id)
        await self._call_api_and_refresh(
            self._api.set_therm_mode,
            home_id=self._home_id,
            mode=option,
        )
        _LOGGER.debug("Therm mode set to %s for home %s", option, self._home_id)


class MigoScheduleSelect(MigoHomeControlEntity, SelectEntity):
    """MiGO Schedule select entity."""

    _attr_translation_key = "schedule"

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        home_id: str,
        api: MigoApi,
    ) -> None:
        """Initialize the schedule select entity."""
        super().__init__(coordinator, home_id, api)
        self._attr_unique_id = generate_unique_id("schedule", home_id)

    @property
    def options(self) -> list[str]:
        """Return the list of available schedules."""
        schedules = self._home_data.get("schedules", [])
        # Only return heating schedules (type: therm)
        return [s.get("name", f"Schedule {s.get('id')}") for s in schedules if s.get("type") == SCHEDULE_TYPE_THERM]

    @property
    def current_option(self) -> str | None:
        """Return the currently active schedule."""
        schedules = self._home_data.get("schedules", [])
        for schedule in schedules:
            if schedule.get("type") == SCHEDULE_TYPE_THERM and schedule.get("selected"):
                return schedule.get("name", f"Schedule {schedule.get('id')}")
        return None

    def _get_schedule_id_by_name(self, name: str) -> str | None:
        """Get schedule ID from its name."""
        schedules = self._home_data.get("schedules", [])
        for schedule in schedules:
            if schedule.get("type") == SCHEDULE_TYPE_THERM:
                schedule_name = schedule.get("name", f"Schedule {schedule.get('id')}")
                if schedule_name == name:
                    return schedule.get("id")
        return None

    async def async_select_option(self, option: str) -> None:
        """Change the active schedule."""
        schedule_id = self._get_schedule_id_by_name(option)
        if not schedule_id:
            _LOGGER.error("Schedule not found: %s", option)
            return

        _LOGGER.debug(
            "Switching to schedule %s (id=%s) for home %s",
            option,
            schedule_id,
            self._home_id,
        )
        await self._call_api_and_refresh(
            self._api.switch_home_schedule,
            home_id=self._home_id,
            schedule_id=schedule_id,
        )
        _LOGGER.debug("Schedule switched to %s for home %s", option, self._home_id)


class MigoHeatingTypeSelect(MigoControlEntity, SelectEntity):
    """MiGO Heating Type select entity."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "heating_type"
    _attr_icon = "mdi:radiator"

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
        api: MigoApi,
    ) -> None:
        """Initialize the heating type select entity."""
        super().__init__(coordinator, device_id, api)
        self._attr_unique_id = generate_unique_id("heating_type", device_id)
        self._attr_options = HEATING_TYPES

    @property
    def current_option(self) -> str | None:
        """Return the current heating type."""
        return self._device_data.get("heating_type", "unknown")

    async def async_select_option(self, option: str) -> None:
        """Change the heating type."""
        if option not in HEATING_TYPES:
            _LOGGER.error("Invalid heating type: %s", option)
            return

        _LOGGER.debug("Setting heating type to %s for device %s", option, self._device_id)
        await self._call_api_and_refresh(
            self._api.set_heating_type,
            device_id=self._device_id,
            heating_type=option,
        )
        _LOGGER.debug("Heating type set to %s for device %s", option, self._device_id)
