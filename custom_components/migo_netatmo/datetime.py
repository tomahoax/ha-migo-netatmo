"""DateTime platform for MiGO integration."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, override

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DEVICE_TYPE_GATEWAY, MODE_AWAY
from .entity import MigoGatewayControlEntity
from .entity_setup import register_dynamic_entities
from .helpers import generate_unique_id, get_devices_by_type, get_home_id_or_raise, is_home_away

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

    # Unlike every other platform in this integration, this used to build
    # entities once from the gateways known at setup time, without going
    # through register_dynamic_entities - a gateway added to the account
    # after the first refresh never got an "Away until" entity, unlike its
    # away_mode switch and binary_sensor companions.
    register_dynamic_entities(
        entry,
        coordinator,
        async_add_entities,
        get_current_ids=lambda: get_devices_by_type(coordinator, DEVICE_TYPE_GATEWAY),
        create_entities=lambda device_id: [
            MigoAwayReturnDateTime(coordinator=coordinator, device_id=device_id, api=data.api)
        ],
    )


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
    @override
    def native_value(self) -> datetime | None:
        """Return the return time, from the optimistic cache or the API.

        Only surfaced while actually Away: `therm_mode_endtime` may linger
        server-side from a past Away period after `therm_mode` itself has
        moved on, and showing it then would be misleading. Uses
        `is_home_away()` for that check - the same optimistic cache
        `MigoAwayModeSwitch` writes, not just raw `coordinator.homes` data -
        so toggling Away off clears this value immediately (the switch
        pushes this entity's listener right when it sets that cache, see
        `MigoAwayModeSwitch._clear_away_until_locally`) instead of only
        once a real coordinator refresh confirms it, which can lag several
        seconds behind a plain toggle.

        Reported live: reactivating Away right after a *previous* Away
        period with a return time made the old date flash briefly before
        disappearing. `is_home_away()` can already be `True` from the
        switch's fresh optimistic cache the instant it's toggled on -
        before `coordinator.homes` itself has been refreshed - so a second
        gate below requires the *raw* `therm_mode` to also already say
        `"away"` before trusting `therm_mode_endtime`: `is_home_away()`
        only proves Away is conceptually active, not that the rest of
        `coordinator.homes` has caught up to that same reality yet. Once
        the real API call and refresh land, both agree and the correct
        value (`None`, since the switch always sends `endtime=None`) shows
        with no intermediate flash.
        """
        cached = self.coordinator.get_cached_value(self._cache_key)
        if cached is not None:
            # Stored as an int Unix timestamp, not a datetime: dev's merge
            # narrowed the coordinator's optimistic cache to
            # `bool | int | float` (every write traced to justify that exact
            # union), so this stores the same timestamp `async_set_value`
            # already computes for the API call rather than widening that
            # union for one entity.
            return datetime.fromtimestamp(int(cached), tz=UTC)

        home_id = self._device_data.get("home_id")
        if not home_id:
            return None
        if not is_home_away(self.coordinator, self._device_id, self._device_data):
            return None

        home_data = self.coordinator.homes.get(home_id, {})
        if home_data.get("therm_mode") != MODE_AWAY:
            return None

        endtime = home_data.get("therm_mode_endtime")
        if endtime is None:
            return None
        return datetime.fromtimestamp(endtime, tz=UTC)

    @override
    async def async_set_value(self, value: datetime) -> None:
        """Activate Away with a return time."""
        home_id = get_home_id_or_raise(self._device_data, "device", self._device_id)

        # HA's datetime service schema normally supplies an aware value, but
        # guard against a naive one anyway rather than silently trusting the
        # system's own local timezone (which may not match HA's configured
        # one) the way a plain value.timestamp() call would. The same
        # aware value is used for the optimistic cache below, so a naive
        # `value` can't leave `native_value` returning a naive datetime from
        # the cache while every other path (the API fallback) returns an
        # aware one.
        aware_value = dt_util.as_utc(value)

        # The API rejects a past endtime outright (400, "endtime in past"),
        # confirmed live. Reported as "no way to confirm the value": the
        # device page's compact date/time row can submit a partial edit
        # (e.g. a date with no time yet, or a stray keystroke) before the
        # user has actually finished picking a moment - Home Assistant's
        # own frontend has a related bug there (a `RangeError: Invalid time
        # value` in `ha-time-input.ts`/`hui-datetime-entity-row.ts`, not
        # something this integration can fix). Catching it here at least
        # turns a raw 400 (which silently rolled the value back to empty,
        # looking exactly like "nothing happened") into a clear, immediate
        # validation error instead of a wasted, confusing API round-trip.
        if aware_value <= dt_util.utcnow():
            raise ServiceValidationError("The Away return time must be in the future")

        endtime = int(aware_value.timestamp())
        _LOGGER.debug(
            "Activating away for home %s until %s (endtime=%s)",
            home_id,
            value,
            endtime,
        )
        await self._call_api_optimistically(
            self._api.set_home_therm_mode,
            cache_key=self._cache_key,
            optimistic_value=endtime,
            home_id=home_id,
            mode=MODE_AWAY,
            endtime=endtime,
        )
        _LOGGER.debug("Away return time set for home %s", home_id)
