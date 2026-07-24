"""Select platform for MiGO integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SCHEDULE_TYPE_THERM
from .entity import MigoHomeControlEntity, register_dynamic_entities
from .helpers import generate_unique_id

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
    """Set up MiGO select entities."""
    data = entry.runtime_data
    coordinator = data.coordinator

    def _schedule_select(home_id: str) -> list[SelectEntity]:
        # Only add the schedule select if therm-type schedules are available.
        # This is gated on data content, not on the home_id itself: if a home
        # gains its first therm schedule after having already been seen, this
        # entity does not appear retroactively (dynamic-devices targets new
        # ids, not new capabilities on an id already known).
        schedules = coordinator.homes.get(home_id, {}).get("schedules", [])
        if not any(s.get("type") == SCHEDULE_TYPE_THERM for s in schedules):
            return []
        return [MigoScheduleSelect(coordinator=coordinator, home_id=home_id, api=data.api)]

    register_dynamic_entities(
        entry,
        coordinator,
        async_add_entities,
        get_current_ids=lambda: coordinator.homes,
        create_entities=_schedule_select,
    )


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
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="schedule_not_found",
                translation_placeholders={"schedule": option},
            )

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
