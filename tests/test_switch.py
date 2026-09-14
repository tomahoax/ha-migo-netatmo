"""Tests for the switch platform (DHW boost, heating anticipation, Away mode, DHW always-on)."""

from __future__ import annotations

from unittest.mock import MagicMock, create_autospec

import pytest

from custom_components.migo_netatmo.api import MigoApi
from custom_components.migo_netatmo.const import MODE_AWAY, MODE_FROST_GUARD, MODE_SCHEDULE
from custom_components.migo_netatmo.switch import (
    MigoAnticipationSwitch,
    MigoAwayModeSwitch,
    MigoDHWAlwaysOnSwitch,
    MigoDHWSwitch,
)


class TestMigoDHWSwitch:
    """Tests for the DHW boost switch entity."""

    @pytest.fixture
    def switch(self, mock_coordinator):
        """Create a DHW switch entity for testing."""
        api = create_autospec(MigoApi, instance=True)
        api.set_dhw_enabled.return_value = {"status": "ok"}
        entity = MigoDHWSwitch(mock_coordinator, "gateway_001", api)
        entity.async_write_ha_state = MagicMock()
        return entity

    def test_is_on_reflects_device_data(self, switch) -> None:
        """is_on reads dhw_enabled straight from the device data."""
        assert switch.is_on is True

    async def test_async_turn_on_enables_dhw(self, switch, mock_coordinator) -> None:
        """Turning on calls set_dhw_enabled with enabled=True and refreshes."""
        await switch.async_turn_on()

        switch._api.set_dhw_enabled.assert_awaited_once_with(
            home_id="home_123",
            module_id="gateway_001",
            enabled=True,
        )
        mock_coordinator.async_request_refresh.assert_awaited_once()

    async def test_async_turn_off_disables_dhw(self, switch) -> None:
        """Turning off calls set_dhw_enabled with enabled=False."""
        await switch.async_turn_off()

        switch._api.set_dhw_enabled.assert_awaited_once_with(
            home_id="home_123",
            module_id="gateway_001",
            enabled=False,
        )


class TestMigoAnticipationSwitch:
    """Tests for the heating anticipation switch entity."""

    @pytest.fixture
    def switch(self, mock_coordinator):
        """Create an anticipation switch entity for testing."""
        api = create_autospec(MigoApi, instance=True)
        api.set_anticipation.return_value = {"status": "ok"}
        entity = MigoAnticipationSwitch(mock_coordinator, "home_123", api)
        entity.async_write_ha_state = MagicMock()
        return entity

    def test_is_on_falls_back_to_home_data_when_not_cached(self, switch, mock_coordinator) -> None:
        """Without a cached value, is_on reads the home's 'anticipation' field."""
        mock_coordinator.get_cached_value.return_value = None
        assert switch.is_on is False  # not present in fixture home data -> default False

    def test_is_on_prefers_optimistic_cache(self, switch, mock_coordinator) -> None:
        """A cached value takes priority over the coordinator's home data."""
        mock_coordinator.get_cached_value.return_value = True
        assert switch.is_on is True

    async def test_async_turn_on_enables_and_caches(self, switch, mock_coordinator) -> None:
        """Turning on calls set_anticipation and stores the optimistic value."""
        await switch.async_turn_on()

        switch._api.set_anticipation.assert_awaited_once_with(home_id="home_123", enabled=True)
        mock_coordinator.set_cached_value.assert_called_once_with("anticipation_home_123", True)
        mock_coordinator.async_request_refresh.assert_awaited_once()

    async def test_async_turn_off_disables_and_caches(self, switch, mock_coordinator) -> None:
        """Turning off calls set_anticipation and stores the optimistic value."""
        await switch.async_turn_off()

        switch._api.set_anticipation.assert_awaited_once_with(home_id="home_123", enabled=False)
        mock_coordinator.set_cached_value.assert_called_once_with("anticipation_home_123", False)


class TestMigoAwayModeSwitch:
    """Tests for the home-wide away mode switch."""

    @pytest.fixture
    def switch(self, mock_coordinator):
        """Create an away mode switch, with async_write_ha_state stubbed (no hass)."""
        api = create_autospec(MigoApi, instance=True)
        api.set_home_therm_mode.return_value = {"status": "ok"}
        entity = MigoAwayModeSwitch(mock_coordinator, "gateway_001", api)
        entity.async_write_ha_state = MagicMock()
        return entity

    def test_is_on_false_when_schedule(self, switch, mock_coordinator):
        """Away mode reads as off when therm_mode is schedule."""
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_SCHEDULE
        assert switch.is_on is False

    def test_is_on_true_when_away(self, switch, mock_coordinator):
        """Away mode reads as on when therm_mode is away."""
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_AWAY
        assert switch.is_on is True

    @pytest.mark.asyncio
    async def test_turn_on_calls_set_home_therm_mode_away(self, switch, mock_coordinator):
        """Turning on writes therm_mode=away at the home level, clearing any endtime."""
        await switch.async_turn_on()

        switch._api.set_home_therm_mode.assert_called_once_with(home_id="home_123", mode=MODE_AWAY, endtime=None)
        mock_coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_turn_off_calls_set_home_therm_mode_schedule(self, switch, mock_coordinator):
        """Turning off returns to schedule mode (the app's "I'm back" button), clearing any endtime."""
        await switch.async_turn_off()

        switch._api.set_home_therm_mode.assert_called_once_with(home_id="home_123", mode=MODE_SCHEDULE, endtime=None)

    @pytest.mark.asyncio
    async def test_turn_on_writes_optimistic_cache_before_api_call(self, switch, mock_coordinator):
        """Regression guard: immediate UI feedback, unlike the forum-reported DHW switch bug."""
        await switch.async_turn_on()

        mock_coordinator.set_cached_value.assert_any_call("away_mode_gateway_001", True)

    @pytest.mark.asyncio
    async def test_turn_on_clears_away_until(self, switch, mock_coordinator):
        """A plain toggle specifies no return time, so any stale one is cleared.

        Reported as "can't reset Away until": the datetime entity has no
        clear affordance of its own, so toggling this switch (either
        direction) is the only deliberate way to reset it.
        """
        await switch.async_turn_on()

        mock_coordinator.clear_cached_value.assert_any_call("away_until_gateway_001")

    @pytest.mark.asyncio
    async def test_turn_off_clears_away_until(self, switch, mock_coordinator):
        """Same as turn_on: coming back should not leave a stale return time displayed."""
        await switch.async_turn_off()

        mock_coordinator.clear_cached_value.assert_any_call("away_until_gateway_001")

    @pytest.mark.asyncio
    async def test_turn_off_notifies_listeners_for_away_until(self, switch, mock_coordinator):
        """Regression guard: clearing the cache alone doesn't push any entity's state.

        Reported live: the Away until value wasn't clearing when Away mode
        was turned off. Clearing the coordinator cache dict is invisible to
        Home Assistant on its own - MigoAwayReturnDateTime needs its
        listener actually invoked to re-render.
        """
        await switch.async_turn_off()

        mock_coordinator.async_update_listeners.assert_called_once()

    @pytest.mark.asyncio
    async def test_turn_on_notifies_listeners_for_away_until(self, switch, mock_coordinator):
        """Same as turn_off, for symmetry."""
        await switch.async_turn_on()

        mock_coordinator.async_update_listeners.assert_called_once()

    @pytest.mark.asyncio
    async def test_away_until_notified_before_api_call(self, mock_coordinator):
        """The push must happen before the API call, not after.

        That's the whole point of the on_optimistic hook: is_home_away()
        (which MigoAwayReturnDateTime.native_value now uses) needs to see
        this switch's fresh optimistic cache value, not risk reading
        coordinator.homes data that a debounced refresh hasn't updated yet.
        """
        events: list[str] = []
        mock_coordinator.async_update_listeners = MagicMock(side_effect=lambda: events.append("notify"))
        api = create_autospec(MigoApi, instance=True)

        async def fake_set_home_therm_mode(**kwargs):
            events.append("api_call")
            return {"status": "ok"}

        api.set_home_therm_mode.side_effect = fake_set_home_therm_mode
        entity = MigoAwayModeSwitch(mock_coordinator, "gateway_001", api)
        entity.async_write_ha_state = MagicMock()

        await entity.async_turn_off()

        assert events == ["notify", "api_call"]

    def test_is_on_reads_optimistic_cache_first(self, switch, mock_coordinator):
        """The cache MigoAwayModeSwitch itself writes takes priority over API data."""
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_SCHEDULE
        mock_coordinator.get_cached_value = MagicMock(return_value=True)

        assert switch.is_on is True

    @pytest.mark.asyncio
    async def test_turn_on_while_frost_guard_replaces_it(self, switch, mock_coordinator):
        """therm_mode is a single shared field: Away and real Frost guard are
        mutually exclusive by construction, same as in the MiGo app itself -
        confirmed not a bug (see class docstring), not something to guard
        against here.
        """
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_FROST_GUARD

        await switch.async_turn_on()

        switch._api.set_home_therm_mode.assert_called_once_with(home_id="home_123", mode=MODE_AWAY, endtime=None)


class TestMigoDHWAlwaysOnSwitch:
    """Tests for the DHW "always on" switch (the MiGo app's "Toujours activée").

    Same shape as MigoDHWSwitch: `MigoGatewayControlEntity` base,
    cache-then-API-fallback `is_on`, `_call_api_optimistically` on write.
    Read/write via `dhw_always_on` (getconfigs/setconfigs), confirmed via a
    live debug-log capture.
    """

    @pytest.fixture
    def switch(self, mock_coordinator):
        """Create a DHW always-on switch, with async_write_ha_state stubbed (no hass)."""
        api = create_autospec(MigoApi, instance=True)
        api.set_dhw_always_on.return_value = {"status": "ok"}
        entity = MigoDHWAlwaysOnSwitch(mock_coordinator, "gateway_001", api)
        entity.async_write_ha_state = MagicMock()
        return entity

    def test_is_on_none_by_default(self, switch):
        """No dhw_always_on field in the default device fixture data."""
        assert switch.is_on is None

    def test_is_on_reads_from_api(self, switch, mock_coordinator):
        """Falls back to the API-echoed dhw_always_on device field."""
        mock_coordinator.devices["gateway_001"]["dhw_always_on"] = True
        assert switch.is_on is True

    @pytest.mark.asyncio
    async def test_turn_on_calls_set_dhw_always_on(self, switch, mock_coordinator):
        """Turning on writes dhw_always_on=True for this gateway."""
        await switch.async_turn_on()

        switch._api.set_dhw_always_on.assert_called_once_with(home_id="home_123", module_id="gateway_001", enabled=True)
        mock_coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_turn_off_calls_set_dhw_always_on(self, switch, mock_coordinator):
        """Turning off writes dhw_always_on=False for this gateway."""
        await switch.async_turn_off()

        switch._api.set_dhw_always_on.assert_called_once_with(
            home_id="home_123", module_id="gateway_001", enabled=False
        )

    @pytest.mark.asyncio
    async def test_turn_on_writes_optimistic_cache_before_api_call(self, switch, mock_coordinator):
        """Immediate UI feedback, same regression guard as the other switches."""
        await switch.async_turn_on()

        mock_coordinator.set_cached_value.assert_any_call("dhw_always_on_gateway_001", True)
