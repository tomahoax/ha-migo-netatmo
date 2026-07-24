"""Tests for the switch platform (DHW boost, heating anticipation)."""

from __future__ import annotations

from unittest.mock import create_autospec

import pytest

from custom_components.migo_netatmo.api import MigoApi
from custom_components.migo_netatmo.switch import MigoAnticipationSwitch, MigoDHWSwitch


class TestMigoDHWSwitch:
    """Tests for the DHW boost switch entity."""

    @pytest.fixture
    def switch(self, mock_coordinator):
        """Create a DHW switch entity for testing."""
        api = create_autospec(MigoApi, instance=True)
        api.set_dhw_enabled.return_value = {"status": "ok"}
        return MigoDHWSwitch(mock_coordinator, "gateway_001", api)

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
        return MigoAnticipationSwitch(mock_coordinator, "home_123", api)

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
