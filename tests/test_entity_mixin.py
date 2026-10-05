"""Tests for MigoApiControlMixin._call_api_optimistically.

Covers the ordering fix for the two latency bugs reported on the forum:
the DHW boost switch had no optimistic cache at all, and the anticipation
switch filled its cache *after* the refresh that writes entity state,
so the UI lagged one poll cycle behind in both cases.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.migo_netatmo.api import MigoApiError
from custom_components.migo_netatmo.entity_mixin import MigoApiControlMixin


class _FakeEntity(MigoApiControlMixin):
    """Minimal concrete stand-in for an entity using the mixin."""

    def __init__(self, coordinator):
        """Wire up the coordinator and a trackable async_write_ha_state."""
        self.coordinator = coordinator
        self.async_write_ha_state = MagicMock()


@pytest.fixture
def coordinator():
    """A coordinator mock with a real dict-backed optimistic cache."""
    coord = MagicMock()
    cache: dict = {}
    coord.get_cached_value = MagicMock(side_effect=lambda key, default=None: cache.get(key, default))
    coord.set_cached_value = MagicMock(side_effect=cache.__setitem__)
    coord.clear_cached_value = MagicMock(side_effect=lambda key: cache.pop(key, None))
    coord.async_request_refresh = AsyncMock()
    return coord


class TestCallApiOptimistically:
    """Tests for the optimistic call/refresh/clear ordering."""

    @pytest.mark.asyncio
    async def test_success_order_cache_then_api_then_refresh_then_clear(self, coordinator):
        """Cache is set (and state written) before the API call, cleared after refresh."""
        events: list[tuple] = []
        coordinator.set_cached_value.side_effect = lambda key, value: events.append(("set", key, value))
        coordinator.clear_cached_value.side_effect = lambda key: events.append(("clear", key))
        coordinator.async_request_refresh.side_effect = lambda: events.append(("refresh",))

        async def api_method(**kwargs):
            events.append(("api_call", kwargs))

        entity = _FakeEntity(coordinator)

        await entity._call_api_optimistically(
            api_method,
            cache_key="dhw_gateway_001",
            optimistic_value=True,
            enabled=True,
        )

        assert events == [
            ("set", "dhw_gateway_001", True),
            ("api_call", {"enabled": True}),
            ("refresh",),
            ("clear", "dhw_gateway_001"),
        ]
        # Only the pre-call optimistic write - deliberately no write after
        # clearing the cache. Regression guard: a write there once caused a
        # real, reported UI flicker (toggle jumps to the old value, then
        # back to the new one a few seconds later) whenever
        # async_request_refresh() got coalesced by the coordinator's
        # debouncer (routine within its 10s cooldown) instead of actually
        # completing a fetch - see the docstring in entity.py for the full
        # mechanism.
        entity.async_write_ha_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_success_clears_cache_so_api_data_regains_authority(self, coordinator):
        """After a successful call, the cache key is gone (not left shadowing API data)."""
        entity = _FakeEntity(coordinator)

        async def api_method(**kwargs):
            return None

        await entity._call_api_optimistically(
            api_method,
            cache_key="anticipation_home_123",
            optimistic_value=True,
        )

        assert coordinator.get_cached_value("anticipation_home_123") is None

    @pytest.mark.asyncio
    async def test_failure_restores_previous_cached_value(self, coordinator):
        """On API failure, a previously cached value is restored, not cleared."""
        coordinator.set_cached_value("k", "previous_value")

        entity = _FakeEntity(coordinator)

        async def failing_api(**kwargs):
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await entity._call_api_optimistically(
                failing_api,
                cache_key="k",
                optimistic_value="new_value",
            )

        assert coordinator.get_cached_value("k") == "previous_value"
        coordinator.async_request_refresh.assert_not_called()
        # Optimistic write, then the restore write.
        assert entity.async_write_ha_state.call_count == 2

    @pytest.mark.asyncio
    async def test_failure_with_no_previous_value_clears_cache(self, coordinator):
        """On API failure with nothing cached before, the cache key is cleared, not set to None."""
        entity = _FakeEntity(coordinator)

        async def failing_api(**kwargs):
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await entity._call_api_optimistically(
                failing_api,
                cache_key="k",
                optimistic_value="new_value",
            )

        coordinator.clear_cached_value.assert_called_once_with("k")
        assert coordinator.get_cached_value("k") is None
        coordinator.async_request_refresh.assert_not_called()

    @pytest.mark.asyncio
    async def test_clear_cache_on_success_false_keeps_optimistic_value(self, coordinator):
        """clear_cache_on_success=False leaves the cache populated after a successful call.

        Regression guard: for a value the API never echoes back on any read
        endpoint (e.g. number.py's heating_curve/hysteresis), the default
        (clear on success) makes native_value fall straight through to a
        hardcoded default right after a successful, confirmed write.
        """
        entity = _FakeEntity(coordinator)

        async def api_method(**kwargs):
            return None

        await entity._call_api_optimistically(
            api_method,
            cache_key="heating_curve_gateway_001",
            optimistic_value=3.4,
            clear_cache_on_success=False,
        )

        assert coordinator.get_cached_value("heating_curve_gateway_001") == 3.4
        coordinator.async_request_refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_secondary_cache_key_set_and_cleared_on_success(self, coordinator):
        """secondary_cache_key gets the same set-before-call, clear-on-success treatment.

        Used where a single write changes two different read-side
        properties, each tracked with its own cache key (see climate.py's
        hvac_mode vs preset_mode).
        """
        entity = _FakeEntity(coordinator)

        async def api_method(**kwargs):
            # Both should already be set before the API call runs.
            assert coordinator.get_cached_value("hvac_mode_room_456") == "off"
            assert coordinator.get_cached_value("preset_mode_room_456") == "dhw_only"

        await entity._call_api_optimistically(
            api_method,
            cache_key="hvac_mode_room_456",
            optimistic_value="off",
            secondary_cache_key="preset_mode_room_456",
            secondary_optimistic_value="dhw_only",
        )

        assert coordinator.get_cached_value("hvac_mode_room_456") is None
        assert coordinator.get_cached_value("preset_mode_room_456") is None

    @pytest.mark.asyncio
    async def test_secondary_cache_key_rolled_back_on_failure(self, coordinator):
        """On failure, secondary_cache_key is restored to its previous value too."""
        coordinator.set_cached_value("preset_mode_room_456", "boost")
        entity = _FakeEntity(coordinator)

        async def failing_api(**kwargs):
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await entity._call_api_optimistically(
                failing_api,
                cache_key="hvac_mode_room_456",
                optimistic_value="off",
                secondary_cache_key="preset_mode_room_456",
                secondary_optimistic_value="dhw_only",
            )

        assert coordinator.get_cached_value("hvac_mode_room_456") is None
        assert coordinator.get_cached_value("preset_mode_room_456") == "boost"

    @pytest.mark.asyncio
    async def test_on_optimistic_rebroadcasts_listeners_on_failure(self, coordinator):
        """A premature on_optimistic broadcast is corrected via a second broadcast on failure.

        Regression guard: on_optimistic runs before the API call and can
        push a *different* entity's state (e.g. MigoAwayModeSwitch clearing
        MigoAwayReturnDateTime's cache). Before this, only this entity's own
        async_write_ha_state ran on rollback - any entity that reacted to
        the premature broadcast stayed wrong until the next real refresh.
        """
        entity = _FakeEntity(coordinator)
        on_optimistic = MagicMock()

        async def failing_api(**kwargs):
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await entity._call_api_optimistically(
                failing_api,
                cache_key="k",
                optimistic_value="new_value",
                on_optimistic=on_optimistic,
            )

        on_optimistic.assert_called_once()
        coordinator.async_update_listeners.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_rebroadcast_on_failure_without_on_optimistic(self, coordinator):
        """No listener re-broadcast on failure when on_optimistic wasn't used - nothing to correct."""
        entity = _FakeEntity(coordinator)

        async def failing_api(**kwargs):
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await entity._call_api_optimistically(
                failing_api,
                cache_key="k",
                optimistic_value="new_value",
            )

        coordinator.async_update_listeners.assert_not_called()

    @pytest.mark.asyncio
    async def test_api_error_is_translated_to_home_assistant_error(self, coordinator):
        """A MigoApiError surfaces as a translated HomeAssistantError, not raw.

        Regression guard: this used to call `api_method` directly instead
        of going through `_call_api`, which skipped `_call_api`'s
        MigoApiError/MigoAuthError/MigoConnectionError -> HomeAssistantError
        translation entirely - every entity using this helper (all number.py
        and switch.py writes, and climate.py once it adopted it) would have
        let a raw, untranslated API exception escape to Home Assistant
        instead of the user-facing message every other write path gives.
        Caught by climate.py's own error-surfacing tests once it started
        using this helper.
        """
        entity = _FakeEntity(coordinator)

        async def failing_api(**kwargs):
            raise MigoApiError("boom")

        with pytest.raises(HomeAssistantError) as exc_info:
            await entity._call_api_optimistically(
                failing_api,
                cache_key="k",
                optimistic_value="new_value",
            )

        assert exc_info.value.translation_key == "api_error"
        coordinator.async_request_refresh.assert_not_called()
