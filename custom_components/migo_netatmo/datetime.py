"""DateTime platform for MiGO integration."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEVICE_TYPE_GATEWAY, MODE_AWAY
from .entity import MigoGatewayControlEntity
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
    """Set up MiGO datetime entities."""
    data = entry.runtime_data
    coordinator = data.coordinator

    entities: list[MigoAwayReturnDateTime] = []

    for device_id in get_devices_by_type(coordinator, DEVICE_TYPE_GATEWAY):
        entities.append(
            MigoAwayReturnDateTime(
                coordinator=coordinator,
                device_id=device_id,
                api=data.api,
            )
        )

    async_add_entities(entities)


class MigoAwayReturnDateTime(MigoGatewayControlEntity, DateTimeEntity):
    """MiGO Away return date/time entity.

    Setting a value activates Away (home-level `therm_mode`) with an end
    time, matching the MiGo app's own "indicate a return date/time" option
    when leaving. Uses `set_home_therm_mode` (the sethomedata endpoint)
    rather than `set_therm_mode` (setthermmode), which has no equivalent
    parameter.

    `therm_mode_endtime` is undocumented by Netatmo, but confirmed present
    on the home object in `homesdata`'s response via a live debug-log
    capture - unlike this integration's other write-only settings
    (`temperature_offset`, `hysteresis`, ...), it *does* round-trip, so
    `native_value` falls back to it once the optimistic cache is cleared,
    the same "cache first, API data second" shape those use.
    """

    _attr_translation_key = "away_until"
    _attr_icon = "mdi:home-clock"

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
        api: MigoApi,
    ) -> None:
        """Initialize the away return date/time entity."""
        super().__init__(coordinator, device_id, api)
        self._attr_unique_id = generate_unique_id("away_until", device_id)

    @property
    def _cache_key(self) -> str:
        """Return the cache key for this entity."""
        return f"away_until_{self._device_id}"

    @property
    def native_value(self) -> datetime | None:
        """Return the return time, from the optimistic cache or the API.

        Only surfaced while actually Away: `therm_mode_endtime` may linger
        server-side from a past Away period after `therm_mode` itself has
        moved on, and showing it then would be misleading.
        """
        cached = self.coordinator.get_cached_value(self._cache_key)
        if cached is not None:
            return cached

        home_id = self._device_data.get("home_id")
        if not home_id:
            return None
        home_data = self.coordinator.homes.get(home_id, {})
        if home_data.get("therm_mode") != MODE_AWAY:
            return None

        endtime = home_data.get("therm_mode_endtime")
        if endtime is None:
            return None
        return datetime.fromtimestamp(endtime, tz=UTC)

    async def async_set_value(self, value: datetime) -> None:
        """Activate Away with a return time."""
        home_id = get_home_id_or_log_error(self._device_data, "device", self._device_id)
        if not home_id:
            return

        endtime = int(value.timestamp())
        _LOGGER.debug(
            "Activating away for home %s until %s (endtime=%s)",
            home_id,
            value,
            endtime,
        )
        await self._call_api_optimistically(
            self._api.set_home_therm_mode,
            cache_key=self._cache_key,
            optimistic_value=value,
            home_id=home_id,
            mode=MODE_AWAY,
            endtime=endtime,
        )
        _LOGGER.debug("Away return time set for home %s", home_id)
