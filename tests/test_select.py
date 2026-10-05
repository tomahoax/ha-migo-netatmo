"""Tests for the select platform (schedule selection)."""

from __future__ import annotations

from unittest.mock import create_autospec

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.migo_netatmo.api import MigoApi
from custom_components.migo_netatmo.select import MigoScheduleSelect


class TestMigoScheduleSelect:
    """Tests for the schedule select entity."""

    @pytest.fixture
    def select(self, mock_coordinator):
        """Create a schedule select entity for testing."""
        api = create_autospec(MigoApi, instance=True)
        api.switch_home_schedule.return_value = {"status": "ok"}
        return MigoScheduleSelect(mock_coordinator, "home_123", api)

    def test_options_lists_only_therm_schedules(self, select) -> None:
        """Only therm-type schedules are exposed, event-only ones are excluded."""
        assert select.options == ["Comfort", "Eco"]

    def test_current_option_returns_selected_schedule(self, select) -> None:
        """The selected therm schedule is reported as the current option."""
        assert select.current_option == "Comfort"

    def test_current_option_none_when_no_schedule_selected(self, select, mock_coordinator) -> None:
        """No selected therm schedule reports current_option as None."""
        for schedule in mock_coordinator.homes["home_123"]["schedules"]:
            schedule["selected"] = False

        assert select.current_option is None

    async def test_async_select_option_switches_schedule(self, select, mock_coordinator) -> None:
        """Selecting an option calls switch_home_schedule with the matching ID."""
        await select.async_select_option("Eco")

        select._api.switch_home_schedule.assert_awaited_once_with(
            home_id="home_123",
            schedule_id="schedule_002",
        )
        mock_coordinator.async_request_refresh.assert_awaited_once()

    async def test_async_select_option_unknown_name_raises(self, select) -> None:
        """Selecting a name that doesn't match any schedule raises a UI error."""
        with pytest.raises(ServiceValidationError):
            await select.async_select_option("Does not exist")

        select._api.switch_home_schedule.assert_not_awaited()
