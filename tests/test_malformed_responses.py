"""Tests that a null-carrying API response degrades instead of crashing.

The MiGO backend is undocumented and unversioned, and it does send explicit
JSON nulls where a container is expected ({"homes": null} rather than an absent
key or an empty list). Every one of these paths previously raised TypeError or
AttributeError from inside _async_update_data, which fails the whole refresh
cycle rather than skipping the bad datum.

These live in their own module because they all assert the same property: a
malformed payload must not take the refresh down with it.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.migo_netatmo.coordinator import MigoDataUpdateCoordinator


class TestNullContainersInHomesData:
    """homesdata with nulls where containers are expected."""

    @pytest.mark.asyncio
    async def test_null_homes_list_yields_no_homes(
        self,
        coordinator: MigoDataUpdateCoordinator,
        mock_api: MagicMock,
    ) -> None:
        """A null "homes" is treated as no homes, not as len(None)."""
        mock_api.get_homes_data.return_value = {"body": {"homes": None}}

        result = await coordinator._async_update_data()

        assert result["homes"] == {}
        assert coordinator.rooms == {}

    @pytest.mark.asyncio
    async def test_null_rooms_and_modules_skip_the_home(
        self,
        coordinator: MigoDataUpdateCoordinator,
        mock_api: MagicMock,
    ) -> None:
        """A home whose modules are null is skipped like one with no modules."""
        mock_api.get_homes_data.return_value = {
            "body": {"homes": [{"id": "home_123", "name": "My Home", "modules": None, "rooms": None}]}
        }

        result = await coordinator._async_update_data()

        assert result["homes"] == {}


class TestNullContainersInHomeStatus:
    """homestatus and getconfigs with nulls where containers are expected."""

    @pytest.mark.asyncio
    async def test_null_home_in_status_body_leaves_rooms_unmerged(
        self,
        coordinator: MigoDataUpdateCoordinator,
        mock_api: MagicMock,
    ) -> None:
        """A null "home" in homestatus yields no status, not an AttributeError."""
        mock_api.get_home_status.return_value = {"body": {"home": None}}

        await coordinator._async_update_data()

        # The room still exists from homesdata; it just carries no live status.
        room = coordinator.rooms["room_456"]
        assert room["name"] == "Living Room"
        assert "therm_measured_temperature" not in room

    @pytest.mark.asyncio
    async def test_null_body_in_status_leaves_rooms_unmerged(
        self,
        coordinator: MigoDataUpdateCoordinator,
        mock_api: MagicMock,
    ) -> None:
        """A null "body" in homestatus is handled the same way."""
        mock_api.get_home_status.return_value = {"body": None}

        await coordinator._async_update_data()

        assert "therm_measured_temperature" not in coordinator.rooms["room_456"]

    @pytest.mark.asyncio
    async def test_null_home_in_configs_body_skips_config_merge(
        self,
        coordinator: MigoDataUpdateCoordinator,
        mock_api: MagicMock,
    ) -> None:
        """A null "home" in getconfigs yields no configs, not an AttributeError."""
        mock_api.get_configs.return_value = {"body": {"home": None}}

        await coordinator._async_update_data()

        assert "dhw_setpoint_temperature" not in coordinator.devices["gateway_001"]


class TestNullsInConsumptionSeries:
    """getmeasure list form with nulls in and around the series."""

    @pytest.mark.asyncio
    async def test_null_entry_in_series_is_skipped(
        self,
        coordinator: MigoDataUpdateCoordinator,
        mock_api: MagicMock,
    ) -> None:
        """A null element inside "value" is skipped, not measured with len().

        The null is last, so it is the first entry the reversed scan reaches.
        """
        mock_api.get_measure.return_value = {
            "body": [{"beg_time": 1700000000, "step_time": 86400, "value": [[120.0, 300.0], None]}]
        }

        await coordinator._async_update_data()

        assert coordinator.consumption["gateway_001"]["sum_boiler_on"] == 120.0

    @pytest.mark.asyncio
    async def test_null_step_time_falls_back_to_one_day(
        self,
        coordinator: MigoDataUpdateCoordinator,
        mock_api: MagicMock,
    ) -> None:
        """A null "step_time" does not break the timestamp arithmetic."""
        mock_api.get_measure.return_value = {
            "body": [{"beg_time": 1700000000, "step_time": None, "value": [[120.0, 300.0]]}]
        }

        await coordinator._async_update_data()

        assert coordinator.consumption["gateway_001"]["timestamp"] == 1700000000

    @pytest.mark.asyncio
    async def test_null_beg_time_skips_the_device(
        self,
        coordinator: MigoDataUpdateCoordinator,
        mock_api: MagicMock,
    ) -> None:
        """Without a start time the timestamps cannot be derived, so skip."""
        mock_api.get_measure.return_value = {
            "body": [{"beg_time": None, "step_time": 86400, "value": [[120.0, 300.0]]}]
        }

        await coordinator._async_update_data()

        assert "gateway_001" not in coordinator.consumption

    @pytest.mark.asyncio
    async def test_null_value_series_skips_the_device(
        self,
        coordinator: MigoDataUpdateCoordinator,
        mock_api: MagicMock,
    ) -> None:
        """A null "value" is treated as an empty series."""
        mock_api.get_measure.return_value = {"body": [{"beg_time": 1700000000, "value": None}]}

        await coordinator._async_update_data()

        assert "gateway_001" not in coordinator.consumption

    @pytest.mark.asyncio
    async def test_three_element_pair_does_not_break_the_refresh(
        self,
        coordinator: MigoDataUpdateCoordinator,
        mock_api: MagicMock,
    ) -> None:
        """A third element must not raise ValueError from tuple unpacking.

        The guard allows 2 OR MORE elements, so unpacking into exactly two names
        raised ValueError, which is not a MigoApiError and so failed the entire
        refresh instead of skipping one reading.
        """
        mock_api.get_measure.return_value = {"body": {"1700000000": [120.0, 300.0, 999.0]}}

        await coordinator._async_update_data()

        assert coordinator.consumption["gateway_001"]["sum_boiler_on"] == 120.0
        assert coordinator.consumption["gateway_001"]["sum_boiler_off"] == 300.0

    @pytest.mark.asyncio
    async def test_non_numeric_timestamp_key_is_skipped(
        self,
        coordinator: MigoDataUpdateCoordinator,
        mock_api: MagicMock,
    ) -> None:
        """A server-chosen key like "latest" must not raise from int()."""
        mock_api.get_measure.return_value = {"body": {"latest": [120.0, 300.0], "1700000000": [60.0, 200.0]}}

        await coordinator._async_update_data()

        # "latest" sorts above the digits, is skipped, and the real one is used.
        assert coordinator.consumption["gateway_001"]["timestamp"] == 1700000000
        assert coordinator.consumption["gateway_001"]["sum_boiler_on"] == 60.0

    @pytest.mark.asyncio
    async def test_null_body_in_measure_skips_the_device(
        self,
        coordinator: MigoDataUpdateCoordinator,
        mock_api: MagicMock,
    ) -> None:
        """A null "body" in getmeasure yields no consumption."""
        mock_api.get_measure.return_value = {"body": None}

        await coordinator._async_update_data()

        assert "gateway_001" not in coordinator.consumption
