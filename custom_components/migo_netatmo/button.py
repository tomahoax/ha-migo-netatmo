"""Button platform for MiGO integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import MigoHomeEntity
from .helpers import generate_unique_id

if TYPE_CHECKING:
    from . import MigoConfigEntry
    from .coordinator import MigoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MigoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MiGO button entities."""
    data = entry.runtime_data
    coordinator = data.coordinator

    entities: list[ButtonEntity] = []

    # Create a refresh button for each home
    for home_id in coordinator.homes:
        entities.append(
            MigoRefreshButton(
                coordinator=coordinator,
                home_id=home_id,
            )
        )

    async_add_entities(entities)


class MigoRefreshButton(MigoHomeEntity, ButtonEntity):
    """MiGO Refresh button entity."""

    _attr_translation_key = "refresh"
    _attr_icon = "mdi:refresh"

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        home_id: str,
    ) -> None:
        """Initialize the refresh button entity."""
        super().__init__(coordinator, home_id)
        self._attr_unique_id = generate_unique_id("refresh", home_id)

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.debug("Manual refresh requested for home %s", self._home_id)
        await self.coordinator.async_request_refresh()
