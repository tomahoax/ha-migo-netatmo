"""Switch platform for MiGO integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEVICE_TYPE_GATEWAY
from .entity import MigoControlEntity, MigoHomeControlEntity
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

    async_add_entities(entities)


class MigoDHWSwitch(MigoControlEntity, SwitchEntity):
    """MiGO Domestic Hot Water (DHW) switch entity."""

    _attr_translation_key = "dhw"

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
    def is_on(self) -> bool | None:
        """Return True if DHW is enabled."""
        return self._device_data.get("dhw_enabled")

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on DHW."""
        home_id = get_home_id_or_log_error(self._device_data, "device", self._device_id)
        if not home_id:
            return

        _LOGGER.debug("Enabling DHW for device %s", self._device_id)
        await self._call_api_and_refresh(
            self._api.set_dhw_enabled,
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
        await self._call_api_and_refresh(
            self._api.set_dhw_enabled,
            home_id=home_id,
            module_id=self._device_id,
            enabled=False,
        )
        _LOGGER.debug("DHW disabled for device %s", self._device_id)


class MigoAnticipationSwitch(MigoHomeControlEntity, SwitchEntity):
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
        await self._call_api_and_refresh(
            self._api.set_anticipation,
            home_id=self._home_id,
            enabled=True,
        )
        # Store in optimistic cache for immediate feedback
        self.coordinator.set_cached_value(self._cache_key, True)
        _LOGGER.debug("Anticipation enabled for home %s", self._home_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable anticipation."""
        _LOGGER.debug("Disabling anticipation for home %s", self._home_id)
        await self._call_api_and_refresh(
            self._api.set_anticipation,
            home_id=self._home_id,
            enabled=False,
        )
        # Store in optimistic cache for immediate feedback
        self.coordinator.set_cached_value(self._cache_key, False)
        _LOGGER.debug("Anticipation disabled for home %s", self._home_id)
