"""Button platform for MiGO integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_HEATING_CURVE, DEVICE_TYPE_GATEWAY
from .entity import MigoHomeEntity, MigoThermostatHomeControlEntity
from .helpers import generate_unique_id, get_devices_by_type

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

    # Create reset heating curve button for each gateway
    for device_id in get_devices_by_type(coordinator, DEVICE_TYPE_GATEWAY):
        device_data = coordinator.devices.get(device_id, {})
        home_id = device_data.get("home_id")
        if home_id:
            entities.append(
                MigoResetHeatingCurveButton(
                    coordinator=coordinator,
                    home_id=home_id,
                    device_id=device_id,
                    api=data.api,
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


class MigoResetHeatingCurveButton(MigoThermostatHomeControlEntity, ButtonEntity):
    """MiGO Reset heating curve button entity."""

    _attr_translation_key = "reset_heating_curve"
    _attr_icon = "mdi:chart-bell-curve"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        home_id: str,
        device_id: str,
        api: MigoApi,
    ) -> None:
        """Initialize the reset heating curve button entity."""
        super().__init__(coordinator, home_id, api)
        self._device_id = device_id
        self._attr_unique_id = generate_unique_id("reset_heating_curve", device_id)

    async def async_press(self) -> None:
        """Handle the button press - reset heating curve to default."""
        _LOGGER.debug(
            "Resetting heating curve to default (%s) for device %s",
            DEFAULT_HEATING_CURVE,
            self._device_id,
        )
        await self._api.set_heating_curve(
            device_id=self._device_id,
            slope=DEFAULT_HEATING_CURVE,
        )
        # Clear cache and refresh
        cache_key = f"heating_curve_{self._device_id}"
        self.coordinator.set_cached_value(cache_key, DEFAULT_HEATING_CURVE)
        await self.coordinator.async_request_refresh()
