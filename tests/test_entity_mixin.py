"""Tests for MigoApiControlMixin._call_api_optimistically.

Covers the ordering fix for the two latency bugs reported on the forum:
the DHW boost switch had no optimistic cache at all, and the anticipation
switch filled its cache *after* the refresh that writes entity state,
so the UI lagged one poll cycle behind in both cases.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.migo_netatmo.entity import MigoApiControlMixin


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
