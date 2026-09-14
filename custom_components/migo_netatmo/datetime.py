"""DateTime platform for MiGO integration."""

from __future__ import annotations

import logging
from datetime import datetime
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
    when leaving. Uses `set_home_therm_mode` (the sethomedata endpoint,
    which documents an optional `therm_mode_endtime`) rather than
    `set_therm_mode` (setthermmode), which has no such parameter.

    Deliberately does not touch `switch.away_mode`: this is an additive way
    to leave with a return time, not a replacement for the plain indefinite
    on/off toggle, which stays on the already-proven setthermmode call.

    `therm_mode_endtime` is documented only as a sethomedata *request*
    field, never confirmed as part of homesdata's or homestatus's response,
    so there is no way to read it back from the API at all. `native_value`
    reflects the optimistic cache only - and unlike the entities
    `MigoApiControlMixin._call_api_optimistically` is meant for, that cache
    is deliberately never cleared after a successful call, since there is no
    real API data for it to hand back to.
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
        """Return the last return time set from Home Assistant, if any."""
        return self.coordinator.get_cached_value(self._cache_key)

    async def async_set_value(self, value: datetime) -> None:
        """Activate Away with a return time.

        Does not use `_call_api_optimistically`: that helper clears its
        cache key after a successful refresh so real API data can take
        over, but there is no real API data for this value (see class
        docstring) - clearing it would make the just-set value vanish from
        the UI immediately. The cache is written before the call for the
        same immediate-feedback reason, and restored on failure, but never
        cleared on success.
        """
        home_id = get_home_id_or_log_error(self._device_data, "device", self._device_id)
        if not home_id:
            return

        endtime = int(value.timestamp())
        previous = self.coordinator.get_cached_value(self._cache_key)
        self.coordinator.set_cached_value(self._cache_key, value)
        self.async_write_ha_state()

        _LOGGER.debug(
            "Activating away for home %s until %s (endtime=%s)",
            home_id,
            value,
            endtime,
        )
        try:
            await self._api.set_home_therm_mode(home_id=home_id, mode=MODE_AWAY, endtime=endtime)
        except Exception:
            if previous is None:
                self.coordinator.clear_cached_value(self._cache_key)
            else:
                self.coordinator.set_cached_value(self._cache_key, previous)
            self.async_write_ha_state()
            raise

        await self.coordinator.async_request_refresh()
        _LOGGER.debug("Away return time set for home %s", home_id)
