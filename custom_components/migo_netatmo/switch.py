"""Switch platform for MiGO integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEVICE_TYPE_GATEWAY, MODE_AWAY, MODE_SCHEDULE
from .entity import MigoGatewayControlEntity, MigoThermostatHomeControlEntity
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
    """Set up MiGO switch entities."""
    data = entry.runtime_data
    coordinator = data.coordinator

    entities: list[SwitchEntity] = []

    # Create DHW switch for each gateway that supports DHW
    for device_id in get_devices_by_type(coordinator, DEVICE_TYPE_GATEWAY):
        entities.append(
            MigoDHWSwitch(
                coordinator=coordinator,
                device_id=device_id,
                api=data.api,
            )
        )

    # Create anticipation switch for each home
    for home_id in coordinator.homes:
        entities.append(
            MigoAnticipationSwitch(
                coordinator=coordinator,
                home_id=home_id,
                api=data.api,
            )
        )

    # Create away mode switch for each gateway
    for device_id in get_devices_by_type(coordinator, DEVICE_TYPE_GATEWAY):
        entities.append(
            MigoAwayModeSwitch(
                coordinator=coordinator,
                device_id=device_id,
                api=data.api,
            )
        )

    async_add_entities(entities)


class MigoDHWSwitch(MigoGatewayControlEntity, SwitchEntity):
    """MiGO Domestic Hot Water (DHW) boost switch entity."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "dhw_boost"
    _attr_icon = "mdi:water-boiler"

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
        api: MigoApi,
    ) -> None:
        """Initialize the DHW switch entity."""
        super().__init__(coordinator, device_id, api)
        self._attr_unique_id = generate_unique_id("dhw", device_id)

    @property
    def _cache_key(self) -> str:
        """Return the cache key for this entity."""
        return f"dhw_{self._device_id}"

    @property
    def is_on(self) -> bool | None:
        """Return True if DHW is enabled."""
        # Check optimistic cache first for immediate feedback
        cached = self.coordinator.get_cached_value(self._cache_key)
        if cached is not None:
            return cached
        # Fallback to API data
        return self._device_data.get("dhw_enabled")

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on DHW."""
        home_id = get_home_id_or_log_error(self._device_data, "device", self._device_id)
        if not home_id:
            return

        _LOGGER.debug("Enabling DHW for device %s", self._device_id)
        await self._call_api_optimistically(
            self._api.set_dhw_enabled,
            cache_key=self._cache_key,
            optimistic_value=True,
            home_id=home_id,
            module_id=self._device_id,
            enabled=True,
        )
        _LOGGER.debug("DHW enabled for device %s", self._device_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off DHW."""
        home_id = get_home_id_or_log_error(self._device_data, "device", self._device_id)
        if not home_id:
            return

        _LOGGER.debug("Disabling DHW for device %s", self._device_id)
        await self._call_api_optimistically(
            self._api.set_dhw_enabled,
            cache_key=self._cache_key,
            optimistic_value=False,
            home_id=home_id,
            module_id=self._device_id,
            enabled=False,
        )
        _LOGGER.debug("DHW disabled for device %s", self._device_id)


class MigoAnticipationSwitch(MigoThermostatHomeControlEntity, SwitchEntity):
    """MiGO Heating Anticipation switch entity."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "anticipation"
    _attr_icon = "mdi:clock-fast"

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        home_id: str,
        api: MigoApi,
    ) -> None:
        """Initialize the anticipation switch entity."""
        super().__init__(coordinator, home_id, api)
        self._attr_unique_id = generate_unique_id("anticipation", home_id)

    @property
    def _cache_key(self) -> str:
        """Return the cache key for this entity."""
        return f"anticipation_{self._home_id}"

    @property
    def is_on(self) -> bool | None:
        """Return True if anticipation is enabled."""
        # Check optimistic cache first for immediate feedback
        cached = self.coordinator.get_cached_value(self._cache_key)
        if cached is not None:
            return cached
        # Fallback to API data
        return self._home_data.get("anticipation", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable anticipation."""
        _LOGGER.debug("Enabling anticipation for home %s", self._home_id)
        await self._call_api_optimistically(
            self._api.set_anticipation,
            cache_key=self._cache_key,
            optimistic_value=True,
            home_id=self._home_id,
            enabled=True,
        )
        _LOGGER.debug("Anticipation enabled for home %s", self._home_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable anticipation."""
        _LOGGER.debug("Disabling anticipation for home %s", self._home_id)
        await self._call_api_optimistically(
            self._api.set_anticipation,
            cache_key=self._cache_key,
            optimistic_value=False,
            home_id=self._home_id,
            enabled=False,
        )
        _LOGGER.debug("Anticipation disabled for home %s", self._home_id)


class MigoAwayModeSwitch(MigoGatewayControlEntity, SwitchEntity):
    """MiGO Away (absence) mode switch, home-wide.

    Reads and writes the home-level `therm_mode` flag, which the climate
    entity's preset (derived from the same field, see climate.py) exposes
    but which is easier to automate as its own boolean switch. Writes via
    `set_therm_mode` (the same call the climate preset uses), so toggling
    this has no side effect on the boiler quick-action mode
    (Normal / DHW only / Frost guard).
    """

    _attr_translation_key = "away_mode"
    _attr_icon = "mdi:home-export-outline"

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
        api: MigoApi,
    ) -> None:
        """Initialize the away mode switch entity."""
        super().__init__(coordinator, device_id, api)
        self._attr_unique_id = generate_unique_id("away_mode", device_id)

    @property
    def _cache_key(self) -> str:
        """Return the cache key for this entity."""
        return f"away_mode_{self._device_id}"

    @property
    def is_on(self) -> bool | None:
        """Return True if away mode is active."""
        cached = self.coordinator.get_cached_value(self._cache_key)
        if cached is not None:
            return cached

        home_id = self._device_data.get("home_id")
        if not home_id:
            return None
        home_data = self.coordinator.homes.get(home_id)
        if home_data is None:
            return None
        return home_data.get("therm_mode") == MODE_AWAY

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable away mode."""
        home_id = get_home_id_or_log_error(self._device_data, "device", self._device_id)
        if not home_id:
            return

        _LOGGER.debug("Enabling away mode for home %s", home_id)
        await self._call_api_optimistically(
            self._api.set_therm_mode,
            cache_key=self._cache_key,
            optimistic_value=True,
            home_id=home_id,
            mode=MODE_AWAY,
        )
        _LOGGER.debug("Away mode enabled for home %s", home_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable away mode (back to schedule)."""
        home_id = get_home_id_or_log_error(self._device_data, "device", self._device_id)
        if not home_id:
            return

        _LOGGER.debug("Disabling away mode for home %s", home_id)
        await self._call_api_optimistically(
            self._api.set_therm_mode,
            cache_key=self._cache_key,
            optimistic_value=False,
            home_id=home_id,
            mode=MODE_SCHEDULE,
        )
        _LOGGER.debug("Away mode disabled for home %s", home_id)
