"""API-calling mixin shared by MiGO entities."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import HomeAssistantError

from .api import MigoApiError, MigoAuthError, MigoConnectionError
from .const import DOMAIN
from .entity_descriptions import MigoEntityDescriptionMixin
from .helpers import generate_unique_id

if TYPE_CHECKING:
    from .api import MigoApi
    from .coordinator import MigoDataUpdateCoordinator
    from .models import ModuleData


class MigoApiControlMixin:
    """Mixin providing API control functionality.

    This mixin provides common functionality for entities that need to
    call API methods and refresh the coordinator after changes.
    """

    _api: MigoApi
    coordinator: MigoDataUpdateCoordinator

    if TYPE_CHECKING:
        # Provided by the Entity base class this mixin is always combined
        # with (see MigoGatewayControlEntity etc.) - declared here only so
        # the methods below type-check.
        def async_write_ha_state(self) -> None: ...

    async def _call_api(
        self,
        api_method: Callable[..., Awaitable[Any]],
        **kwargs: Any,
    ) -> Any:
        """Call an API method, translating failures into UI-visible errors.

        Args:
            api_method: The async API method to call.
            **kwargs: Arguments to pass to the API method.

        Raises:
            HomeAssistantError: On any API failure, with a translated message.
        """
        try:
            return await api_method(**kwargs)
        except MigoAuthError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="auth_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        except MigoConnectionError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"error": str(err)},
            ) from err
        except MigoApiError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="api_error",
                translation_placeholders={"error": str(err)},
            ) from err

    async def _call_api_and_refresh(
        self,
        api_method: Callable[..., Awaitable[Any]],
        **kwargs: Any,
    ) -> None:
        """Call an API method and refresh the coordinator.

        Args:
            api_method: The async API method to call.
            **kwargs: Arguments to pass to the API method.
        """
        await self._call_api(api_method, **kwargs)
        await self.coordinator.async_request_refresh()

    async def _call_api_optimistically(
        self,
        api_method: Callable[..., Awaitable[Any]],
        *,
        cache_key: str,
        optimistic_value: Any,
        on_optimistic: Callable[[], None] | None = None,
        clear_cache_on_success: bool = True,
        secondary_cache_key: str | None = None,
        secondary_optimistic_value: Any = None,
        **kwargs: Any,
    ) -> None:
        """Call an API method with immediate optimistic UI feedback.

        Unlike `_call_api_and_refresh`, this writes `optimistic_value` to the
        coordinator's cache and to entity state *before* the API call, so the
        UI reacts immediately instead of waiting for the coordinator's next
        refresh cycle. On success, it requests a refresh and then, unless
        `clear_cache_on_success` is False, clears the cache entry so API data
        regains authority - the cache key is not left behind to shadow future
        API values. On failure, the previous cached value (or its absence) is
        restored before the exception propagates.

        `clear_cache_on_success` defaults to True, matching every existing
        caller. Pass False for a value the API never echoes back on any read
        endpoint (see `MigoHeatingCurveNumber`/`MigoHysteresisNumber` in
        number.py): clearing the cache for one of those does not let "API
        data regain authority" the way the docstring above describes for
        everyone else - there is no API data for it - it instead makes
        `native_value` fall through to a hardcoded default, silently
        discarding the value that was just written and confirmed to succeed.

        `secondary_cache_key`/`secondary_optimistic_value`, if given, get the
        exact same set-before-call, roll-back-on-failure, clear-on-success
        treatment as `cache_key`/`optimistic_value`. Used where a single
        write changes state two different read-side properties each track
        with their own cache key (see climate.py's `hvac_mode` vs
        `preset_mode`, both derived from overlapping room/home fields but
        each only ever written by its own setter before this parameter
        existed - selecting a preset left `hvac_mode` showing the previous
        mode, and vice versa, until the next coordinator refresh).

        `on_optimistic`, if given, runs synchronously right after this
        entity's own optimistic cache/state write, before the API call - the
        one moment where a *different* entity's cache-aware read (e.g.
        `helpers.is_home_away()`) is guaranteed to see this entity's fresh
        optimistic value without also risking a read of stale coordinator
        data. Used by `MigoAwayModeSwitch` to clear and push
        `MigoAwayReturnDateTime`'s value in the same instant, rather than
        only when this entity's own state is written. On failure, after
        `cache_key`/`secondary_cache_key` are rolled back, listeners are
        pushed again so any entity that reacted to the premature broadcast
        above sees the corrected value too, rather than only self-correcting
        on the next real refresh.

        Deliberately does *not* write state again right after clearing the
        cache. `async_request_refresh()` goes through the coordinator's
        refresh debouncer (10s cooldown, `immediate=True`): the very first
        call in a while runs the fetch synchronously and pushes state via
        its own `async_update_listeners()` while the cache is still
        populated (showing the optimistic value, correctly) - but any call
        within 10s of a previous refresh (routine background polling, or
        just toggling more than one control in a row) is coalesced and
        returns immediately *without* having fetched anything yet. A write
        here would then render the just-cleared cache against still-stale
        coordinator data, i.e. the UI would revert to the old value and
        only jump back to the new one once the coalesced refresh actually
        completes a few seconds later - a real, reported regression from
        this line's own earlier addition, not a hypothetical. Leaving the
        optimistic value on screen (it already matches what was just
        requested, in the overwhelmingly common case) until the coordinator's
        own next real update is the better trade-off.

        Args:
            api_method: The async API method to call.
            cache_key: The coordinator optimistic-cache key for this entity.
            optimistic_value: The value to show immediately while the call is
                in flight.
            on_optimistic: Optional callback run right after the optimistic
                write above, before the API call.
            clear_cache_on_success: Whether to clear `cache_key` (and
                `secondary_cache_key`) once the call succeeds and a refresh
                has been requested. Defaults to True; pass False for a value
                the API never echoes back on any read endpoint.
            secondary_cache_key: Optional second coordinator cache key that
                gets the same set/roll-back/clear treatment as `cache_key`.
            secondary_optimistic_value: The value to show immediately for
                `secondary_cache_key`, while the call is in flight.
            **kwargs: Arguments to pass to the API method.

        Raises:
            HomeAssistantError: On any API failure, with a translated message
                (via `_call_api` - this used to call `api_method` directly,
                which skipped that translation and let a raw MigoApiError/
                MigoAuthError/MigoConnectionError escape to Home Assistant
                instead of the user-facing message every other write path
                gives; caught by climate.py's error-surfacing tests once it
                started using this helper too).
        """
        previous = self.coordinator.get_cached_value(cache_key)
        self.coordinator.set_cached_value(cache_key, optimistic_value)
        secondary_previous = None
        if secondary_cache_key is not None:
            secondary_previous = self.coordinator.get_cached_value(secondary_cache_key)
            self.coordinator.set_cached_value(secondary_cache_key, secondary_optimistic_value)
        self.async_write_ha_state()
        if on_optimistic is not None:
            on_optimistic()

        try:
            await self._call_api(api_method, **kwargs)
        except Exception:
            if previous is None:
                self.coordinator.clear_cached_value(cache_key)
            else:
                self.coordinator.set_cached_value(cache_key, previous)
            if secondary_cache_key is not None:
                if secondary_previous is None:
                    self.coordinator.clear_cached_value(secondary_cache_key)
                else:
                    self.coordinator.set_cached_value(secondary_cache_key, secondary_previous)
            self.async_write_ha_state()
            if on_optimistic is not None:
                # Undo the premature broadcast `on_optimistic` triggered
                # above: any entity that already reacted to it needs to see
                # the rolled-back value too, not just this entity's own
                # state (async_write_ha_state only re-renders this one).
                self.coordinator.async_update_listeners()
            raise

        await self.coordinator.async_request_refresh()
        if clear_cache_on_success:
            self.coordinator.clear_cached_value(cache_key)
            if secondary_cache_key is not None:
                self.coordinator.clear_cached_value(secondary_cache_key)


class _MigoCachedValueMixin:
    """Shared "optimistic cache, else computed fallback" read pattern.

    Every number.py/switch.py entity's native_value/is_on checked the
    coordinator's optimistic cache first (for immediate feedback right after
    a write, before the next refresh lands) and fell back to a per-entity
    computation otherwise - hand-rolled identically nine times. Combined
    alongside `MigoApiControlMixin`, which already shares the write side of
    the same pattern (`_call_api_optimistically`).
    """

    if TYPE_CHECKING:
        coordinator: MigoDataUpdateCoordinator

        @property
        def _cache_key(self) -> str: ...

    def _resolve_cached_value(self, fallback: Callable[[], Any]) -> Any:
        """Return the optimistic cache value if present, else `fallback()`."""
        cached = self.coordinator.get_cached_value(self._cache_key)
        return cached if cached is not None else fallback()


class _MigoDescriptionEntityMixin:
    """Shared init/read logic for MiGO's entity-description-driven entities.

    Combined with a device-data-providing entity base (`MigoGatewayEntity`/
    `MigoThermostatEntity`) and a Home Assistant platform's own `Entity`
    subclass - see `sensor.py`'s `_MigoDeviceSensorMixin`/`binary_sensor.py`'s
    `_MigoDeviceBinarySensorMixin` for the concrete platform-specific uses.
    """

    entity_description: MigoEntityDescriptionMixin
    # Declared explicitly as str | None, matching Entity's own type: without
    # this, mypy infers a narrower `str` from the assignment below, which it
    # then treats as incompatible with Entity's wider declaration once a
    # concrete entity inherits from both this mixin and Entity.
    _attr_unique_id: str | None

    if TYPE_CHECKING:

        @property
        def _device_data(self) -> ModuleData: ...

    def _init_description_entity(self, device_id: str, description: MigoEntityDescriptionMixin) -> None:
        """Set entity_description and the unique_id, from the description."""
        self.entity_description = description
        self._attr_unique_id = generate_unique_id(description.unique_id_key, device_id)

    def _resolve_described_value(self) -> Any:
        """Return entity_description.value_fn(data_key's value), or the raw value."""
        value = self._device_data.get(self.entity_description.data_key)
        if self.entity_description.value_fn:
            return self.entity_description.value_fn(value)
        return value
