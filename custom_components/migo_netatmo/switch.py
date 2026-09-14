"""Switch platform for MiGO integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, override

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEVICE_TYPE_GATEWAY, MODE_AWAY, MODE_SCHEDULE
from .entity import MigoGatewayControlEntity, MigoThermostatHomeControlEntity
from .entity_mixin import _MigoCachedValueMixin
from .entity_setup import register_dynamic_entities
from .helpers import generate_unique_id, get_devices_by_type, get_home_id_or_raise, is_home_away

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
    """Set up MiGO switch entities."""
    data = entry.runtime_data
    coordinator = data.coordinator

    # DHW switch for each gateway that supports DHW
    register_dynamic_entities(
        entry,
        coordinator,
        async_add_entities,
        get_current_ids=lambda: get_devices_by_type(coordinator, DEVICE_TYPE_GATEWAY),
        create_entities=lambda device_id: [MigoDHWSwitch(coordinator=coordinator, device_id=device_id, api=data.api)],
    )

    # Anticipation switch for each home
    register_dynamic_entities(
        entry,
        coordinator,
        async_add_entities,
        get_current_ids=lambda: coordinator.homes,
        create_entities=lambda home_id: [
            MigoAnticipationSwitch(coordinator=coordinator, home_id=home_id, api=data.api)
        ],
    )

    # Away mode switch for each gateway
    register_dynamic_entities(
        entry,
        coordinator,
        async_add_entities,
        get_current_ids=lambda: get_devices_by_type(coordinator, DEVICE_TYPE_GATEWAY),
        create_entities=lambda device_id: [
            MigoAwayModeSwitch(coordinator=coordinator, device_id=device_id, api=data.api)
        ],
    )

    # DHW always-on switch for each gateway that supports DHW
    register_dynamic_entities(
        entry,
        coordinator,
        async_add_entities,
        get_current_ids=lambda: get_devices_by_type(coordinator, DEVICE_TYPE_GATEWAY),
        create_entities=lambda device_id: [
            MigoDHWAlwaysOnSwitch(coordinator=coordinator, device_id=device_id, api=data.api)
        ],
    )


class MigoDHWSwitch(_MigoCachedValueMixin, MigoGatewayControlEntity, SwitchEntity):
    """MiGO Domestic Hot Water (DHW) boost switch entity.

    No entity_category: this is a control with an immediate operational
    effect (a quick, temporary override), not a set-once configuration
    value, so it belongs in the primary "Controls" card alongside the other
    toggles rather than in "Configuration".
    """

    _attr_translation_key = "dhw_boost"

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
    @override
    def is_on(self) -> bool | None:
        """Return True if DHW is enabled."""
        return self._resolve_cached_value(lambda: self._device_data.get("dhw_enabled"))

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on DHW."""
        home_id = get_home_id_or_raise(self._device_data, "device", self._device_id)

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

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off DHW."""
        home_id = get_home_id_or_raise(self._device_data, "device", self._device_id)

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


class MigoAnticipationSwitch(_MigoCachedValueMixin, MigoThermostatHomeControlEntity, SwitchEntity):
    """MiGO Heating Anticipation switch entity.

    No entity_category: same reasoning as MigoDHWSwitch - an operational
    toggle, not a configuration value.
    """

    _attr_translation_key = "anticipation"

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
    @override
    def is_on(self) -> bool | None:
        """Return True if anticipation is enabled."""
        return bool(self._resolve_cached_value(lambda: self._home_data.get("anticipation", False)))

    @override
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

    @override
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
    but which is easier to automate as its own boolean switch.

    Writes via `set_home_therm_mode` (sethomedata) with an explicit
    `endtime=None`, rather than `set_therm_mode` (setthermmode, which has
    no such parameter at all): `therm_mode_endtime` is confirmed to persist
    server-side independently of `therm_mode` itself (see
    `datetime.MigoAwayReturnDateTime`), so turning Away on or off from this
    plain switch - which never specifies a return time - has to clear it
    explicitly, or a stale one set earlier (from `MigoAwayReturnDateTime`,
    or from the MiGo app itself) would resurface on the next refresh.

    Writes only the home-level `therm_mode` field, never room state, so the
    room-level boiler quick-action (Normal / DHW only) is always untouched.
    Real Frost guard/standby is the home-level third quick-action state
    (`therm_mode == "hg"`, see `helpers.derive_boiler_mode`) and shares this
    same field with Away, so the two are mutually exclusive by construction:
    turning Away on while Frost guard is active does replace it, same as it
    would in the MiGo app itself (there is no API-level way to represent
    both at once) - not a bug this integration introduces.
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
        return is_home_away(self.coordinator, self._device_id, self._device_data)

    def _clear_away_until_locally(self) -> None:
        """Clear the local cache for the Away return time and push it now.

        Shares the cache key format with `datetime.py`'s
        `MigoAwayReturnDateTime` (same device_id), the same cross-entity
        coupling `MigoResetHeatingCurveButton`/`MigoHeatingCurveNumber`
        already use for `heating_curve_{device_id}`. The actual clearing
        happens server-side too, via `endtime=None` on the API call below.

        Passed as `_call_api_optimistically`'s `on_optimistic` hook, so it
        runs right after *this* switch's own optimistic cache is set - not
        after the whole call completes - which matters:
        `MigoAwayReturnDateTime.native_value` gates on `is_home_away()`,
        which checks this same switch's cache first. Pushing listeners at
        that exact moment means the datetime entity re-renders while the
        switch's cache already reflects the new state, so it reads as
        correctly not-Away (or Away) immediately - not against
        `coordinator.homes` data that may still be stale for several more
        seconds (see `_call_api_optimistically`'s own docstring). Pushing
        any earlier or later would risk exactly that staleness.
        """
        self.coordinator.clear_cached_value(f"away_until_{self._device_id}")
        self.coordinator.async_update_listeners()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable away mode."""
        home_id = get_home_id_or_raise(self._device_data, "device", self._device_id)

        _LOGGER.debug("Enabling away mode for home %s", home_id)
        await self._call_api_optimistically(
            self._api.set_home_therm_mode,
            cache_key=self._cache_key,
            optimistic_value=True,
            on_optimistic=self._clear_away_until_locally,
            home_id=home_id,
            mode=MODE_AWAY,
            endtime=None,
        )
        _LOGGER.debug("Away mode enabled for home %s", home_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable away mode (back to schedule)."""
        home_id = get_home_id_or_raise(self._device_data, "device", self._device_id)

        _LOGGER.debug("Disabling away mode for home %s", home_id)
        await self._call_api_optimistically(
            self._api.set_home_therm_mode,
            cache_key=self._cache_key,
            optimistic_value=False,
            on_optimistic=self._clear_away_until_locally,
            home_id=home_id,
            mode=MODE_SCHEDULE,
            endtime=None,
        )
        _LOGGER.debug("Away mode disabled for home %s", home_id)


class MigoDHWAlwaysOnSwitch(_MigoCachedValueMixin, MigoGatewayControlEntity, SwitchEntity):
    """MiGO DHW "always on" switch entity.

    Mirrors the MiGo app's "Toujours activée" toggle on the DHW temperature
    settings screen: when enabled, the boiler never suspends DHW heating,
    overriding whatever the active schedule's per-slot "Production d'eau
    chaude" setting would otherwise say.

    Read/write via `/syncapi/v1/getconfigs` and `/syncapi/v1/setconfigs`
    (`dhw_always_on`, confirmed via a live debug-log capture), the same
    module-level config field pair `MigoDHWTemperatureNumber` already uses
    for `dhw_setpoint_temperature` - so this stays alongside `MigoDHWSwitch`
    in the primary "Controls" card rather than "Configuration": like DHW
    boost, it's an operational override the user reaches for directly, not
    a set-once value.
    """

    _attr_translation_key = "dhw_always_on"
    _attr_icon = "mdi:water-boiler-alert"

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
        api: MigoApi,
    ) -> None:
        """Initialize the DHW always-on switch entity."""
        super().__init__(coordinator, device_id, api)
        self._attr_unique_id = generate_unique_id("dhw_always_on", device_id)

    @property
    def _cache_key(self) -> str:
        """Return the cache key for this entity."""
        return f"dhw_always_on_{self._device_id}"

    @property
    def is_on(self) -> bool | None:
        """Return True if DHW always-on is enabled."""
        return self._resolve_cached_value(lambda: self._device_data.get("dhw_always_on"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable DHW always-on."""
        home_id = get_home_id_or_raise(self._device_data, "device", self._device_id)

        _LOGGER.debug("Enabling DHW always-on for device %s", self._device_id)
        await self._call_api_optimistically(
            self._api.set_dhw_always_on,
            cache_key=self._cache_key,
            optimistic_value=True,
            home_id=home_id,
            module_id=self._device_id,
            enabled=True,
        )
        _LOGGER.debug("DHW always-on enabled for device %s", self._device_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable DHW always-on."""
        home_id = get_home_id_or_raise(self._device_data, "device", self._device_id)

        _LOGGER.debug("Disabling DHW always-on for device %s", self._device_id)
        await self._call_api_optimistically(
            self._api.set_dhw_always_on,
            cache_key=self._cache_key,
            optimistic_value=False,
            home_id=home_id,
            module_id=self._device_id,
            enabled=False,
        )
        _LOGGER.debug("DHW always-on disabled for device %s", self._device_id)
