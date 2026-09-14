"""Tests for the datetime platform (Away return time)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, create_autospec

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.migo_netatmo.api import MigoApi
from custom_components.migo_netatmo.const import MODE_AWAY, MODE_SCHEDULE
from custom_components.migo_netatmo.datetime import MigoAwayReturnDateTime

# mock_coordinator fixture lives in conftest.py, shared across test modules.


class TestMigoAwayReturnDateTime:
    """Tests for the Away return date/time entity.

    `therm_mode_endtime` is confirmed to round-trip via the API (a live
    debug-log capture, cross-checked against the user's own MiGo app
    screenshot), so this uses the standard `_call_api_optimistically`
    pattern like every other read/write entity: the cache is cleared after
    a successful call, and `native_value` falls back to the API-echoed
    value (gated on `therm_mode == MODE_AWAY`, so a lingering endtime from
    a past Away period isn't shown once the mode has moved on).
    """

    @pytest.fixture
    def cache(self, mock_coordinator):
        """Give mock_coordinator a real dict-backed cache instead of a bare MagicMock."""
        store: dict = {}
        mock_coordinator.get_cached_value = MagicMock(side_effect=lambda k, default=None: store.get(k, default))
        mock_coordinator.set_cached_value = MagicMock(side_effect=store.__setitem__)
        mock_coordinator.clear_cached_value = MagicMock(side_effect=lambda k: store.pop(k, None))
        return store

    @pytest.fixture
    def entity(self, mock_coordinator):
        api = create_autospec(MigoApi, instance=True)
        api.set_home_therm_mode.return_value = {"status": "ok"}
        ent = MigoAwayReturnDateTime(mock_coordinator, "gateway_001", api)
        ent.async_write_ha_state = MagicMock()
        return ent

    @pytest.mark.asyncio
    async def test_set_value_activates_away_with_endtime(self, entity, cache):
        """Converts the datetime to a Unix timestamp and activates Away."""
        value = datetime(2026, 12, 24, 18, 0, tzinfo=UTC)

        await entity.async_set_value(value)

        entity._api.set_home_therm_mode.assert_called_once_with(
            home_id="home_123", mode=MODE_AWAY, endtime=int(value.timestamp())
        )

    @pytest.mark.asyncio
    async def test_cache_cleared_after_successful_set(self, entity, cache):
        """Unlike the earlier hand-rolled implementation, the cache IS cleared on success."""
        value = datetime(2026, 12, 24, 18, 0, tzinfo=UTC)

        await entity.async_set_value(value)

        assert cache == {}

    @pytest.mark.asyncio
    async def test_set_value_rejects_past_datetime(self, entity, cache):
        """Regression guard: the real API rejects a past endtime with a 400
        ("endtime in past"), reported live - `_call_api_optimistically`'s
        rollback then silently cleared the value, looking exactly like
        "no way to confirm the value" rather than a validation failure.
        Caught here instead, before any API call or optimistic write.
        """
        past_value = datetime(2020, 1, 1, tzinfo=UTC)

        with pytest.raises(ServiceValidationError):
            await entity.async_set_value(past_value)

        entity._api.set_home_therm_mode.assert_not_called()
        assert cache == {}

    @pytest.mark.asyncio
    async def test_native_value_falls_back_to_api_after_successful_set(self, entity, mock_coordinator, cache):
        """Once the optimistic cache is cleared, native_value re-derives from the API-echoed home data."""
        value = datetime(2026, 12, 24, 18, 0, tzinfo=UTC)
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_AWAY
        mock_coordinator.homes["home_123"]["therm_mode_endtime"] = int(value.timestamp())

        await entity.async_set_value(value)

        assert entity.native_value == value

    def test_native_value_none_by_default(self, entity):
        """No return time has been set yet, and therm_mode is not away by default."""
        assert entity.native_value is None

    def test_native_value_from_api_when_away(self, entity, mock_coordinator):
        """Falls back to the API-echoed therm_mode_endtime while actually Away."""
        value = datetime(2026, 12, 24, 18, 0, tzinfo=UTC)
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_AWAY
        mock_coordinator.homes["home_123"]["therm_mode_endtime"] = int(value.timestamp())

        assert entity.native_value == value

    def test_native_value_none_when_switch_cache_says_away_but_raw_data_not_refreshed_yet(
        self, entity, mock_coordinator
    ):
        """Regression guard for the reported "old date flashes on reactivation" complaint.

        Reactivating switch.migo_{home}_away_mode sets its own cache to
        True (via _call_api_optimistically) *before* the API call, and its
        on_optimistic hook pushes this entity's listener right then - so
        is_home_away() already reads True while coordinator.homes hasn't
        been refreshed yet and still carries therm_mode="schedule" plus
        whatever therm_mode_endtime a *previous* Away period left behind.
        native_value must not show that stale value in this window.
        """
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_SCHEDULE
        mock_coordinator.homes["home_123"]["therm_mode_endtime"] = 1234567890
        mock_coordinator.get_cached_value = MagicMock(
            side_effect=lambda key, default=None: True if key == "away_mode_gateway_001" else default
        )

        assert entity.native_value is None

    def test_native_value_shows_once_raw_data_agrees_too(self, entity, mock_coordinator):
        """Once coordinator.homes itself catches up (raw therm_mode == away), the value shows - no over-correction."""
        value = datetime(2026, 12, 24, 18, 0, tzinfo=UTC)
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_AWAY
        mock_coordinator.homes["home_123"]["therm_mode_endtime"] = int(value.timestamp())
        mock_coordinator.get_cached_value = MagicMock(
            side_effect=lambda key, default=None: True if key == "away_mode_gateway_001" else default
        )

        assert entity.native_value == value

    def test_native_value_none_when_not_away_even_with_stale_endtime(self, entity, mock_coordinator):
        """A lingering endtime from a past Away period isn't shown once therm_mode has moved on."""
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_SCHEDULE
        mock_coordinator.homes["home_123"]["therm_mode_endtime"] = 1234567890

        assert entity.native_value is None

    def test_native_value_none_when_home_unresolved(self, entity, mock_coordinator):
        """Unavailable (None) if the device has no home_id."""
        mock_coordinator.devices["gateway_001"] = {"id": "gateway_001"}
        assert entity.native_value is None

    def test_native_value_none_when_switch_cache_says_not_away_even_if_home_data_stale(self, entity, mock_coordinator):
        """Reads MigoAwayModeSwitch's own cache, not just raw coordinator.homes data.

        Regression guard for the reported "turning off Away doesn't clear
        Away until" complaint: the switch's own async_request_refresh() can
        be coalesced by the coordinator's debouncer, leaving
        coordinator.homes stale (still showing therm_mode="away") for
        several more seconds. native_value must still show cleared
        immediately once the switch's away_mode cache says otherwise,
        rather than waiting on that stale raw data.
        """
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_AWAY
        mock_coordinator.homes["home_123"]["therm_mode_endtime"] = 1234567890
        # Simulate MigoAwayModeSwitch having just set its own cache to False
        # (as _call_api_optimistically does, synchronously, before the API
        # call even returns) while coordinator.homes above is still stale.
        mock_coordinator.get_cached_value = MagicMock(
            side_effect=lambda key, default=None: False if key == "away_mode_gateway_001" else default
        )

        assert entity.native_value is None

    @pytest.mark.asyncio
    async def test_set_value_restores_previous_on_failure(self, entity, cache):
        """A failed call restores whatever return time was cached before it.

        Cached as an int Unix timestamp, not a datetime object: dev's merge
        narrowed the coordinator's optimistic-cache type to
        `bool | int | float`, and `native_value` converts it back to a
        datetime on read (see `datetime.py`'s own comment on this).
        """
        previous = datetime(2026, 12, 20, 9, 0, tzinfo=UTC)
        cache["away_until_gateway_001"] = int(previous.timestamp())
        entity._api.set_home_therm_mode.side_effect = RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await entity.async_set_value(datetime(2026, 12, 24, 18, 0, tzinfo=UTC))

        assert entity.native_value == previous
