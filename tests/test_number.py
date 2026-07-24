"""Tests for the number platform (config-style numeric entities)."""

from __future__ import annotations

from unittest.mock import create_autospec

import pytest

from custom_components.migo_netatmo.api import MigoApi
from custom_components.migo_netatmo.const import (
    DEFAULT_DHW_TEMPERATURE,
    DEFAULT_HEATING_CURVE,
    DEFAULT_HYSTERESIS,
    DEFAULT_MANUAL_SETPOINT_DURATION,
    DEFAULT_TEMP_OFFSET,
)
from custom_components.migo_netatmo.number import (
    MigoDHWTemperatureNumber,
    MigoHeatingCurveNumber,
    MigoHysteresisNumber,
    MigoManualSetpointDurationNumber,
    MigoTemperatureOffsetNumber,
)


@pytest.fixture
def api():
    """Create an autospecced API mock shared by all number entity fixtures."""
    mock = create_autospec(MigoApi, instance=True)
    mock.set_manual_setpoint_duration.return_value = {"status": "ok"}
    mock.set_temperature_offset.return_value = {"status": "ok"}
    mock.set_dhw_temperature.return_value = {"status": "ok"}
    mock.set_hysteresis.return_value = {"status": "ok"}
    mock.set_heating_curve.return_value = {"status": "ok"}
    return mock


class TestMigoManualSetpointDurationNumber:
    """Tests for the manual setpoint default duration entity."""

    @pytest.fixture
    def entity(self, mock_coordinator, api):
        """Create the entity under test."""
        return MigoManualSetpointDurationNumber(mock_coordinator, "home_123", api)

    def test_native_value_uses_cache_when_present(self, entity, mock_coordinator) -> None:
        """A cached value takes priority over API data."""
        mock_coordinator.get_cached_value.return_value = 45
        assert entity.native_value == 45

    def test_native_value_falls_back_to_home_data(self, entity, mock_coordinator) -> None:
        """Without a cached value, the home's stored duration is used."""
        mock_coordinator.homes["home_123"]["therm_setpoint_default_duration"] = 120
        assert entity.native_value == 120

    def test_native_value_defaults_when_absent(self, entity) -> None:
        """With no cache and no API value, the documented default applies."""
        assert entity.native_value == DEFAULT_MANUAL_SETPOINT_DURATION

    async def test_async_set_native_value(self, entity, mock_coordinator) -> None:
        """Setting a value calls the API, caches it, and refreshes (no coordinator API call awaited)."""
        await entity.async_set_native_value(90.0)

        entity._api.set_manual_setpoint_duration.assert_awaited_once_with(home_id="home_123", duration=90)
        mock_coordinator.set_cached_value.assert_called_once_with("manual_setpoint_duration_home_123", 90)
        mock_coordinator.async_request_refresh.assert_awaited_once()


class TestMigoTemperatureOffsetNumber:
    """Tests for the room temperature offset entity."""

    @pytest.fixture
    def entity(self, mock_coordinator, api):
        """Create the entity under test."""
        return MigoTemperatureOffsetNumber(mock_coordinator, "room_456", "home_123", api)

    def test_native_value_uses_cache_when_present(self, entity, mock_coordinator) -> None:
        """A cached value takes priority over API data."""
        mock_coordinator.get_cached_value.return_value = 1.5
        assert entity.native_value == 1.5

    def test_native_value_falls_back_to_room_data(self, entity, mock_coordinator) -> None:
        """Without a cached value, therm_setpoint_offset from the room is used."""
        mock_coordinator.rooms["room_456"]["therm_setpoint_offset"] = -2.0
        assert entity.native_value == -2.0

    def test_native_value_defaults_when_absent(self, entity) -> None:
        """With no cache and no API value, the documented default applies."""
        assert entity.native_value == DEFAULT_TEMP_OFFSET

    async def test_async_set_native_value(self, entity, mock_coordinator) -> None:
        """Setting a value calls the API, caches it, and refreshes."""
        await entity.async_set_native_value(-1.0)

        entity._api.set_temperature_offset.assert_awaited_once_with(home_id="home_123", room_id="room_456", offset=-1.0)
        mock_coordinator.set_cached_value.assert_called_once_with("temp_offset_room_456", -1.0)
        mock_coordinator.async_request_refresh.assert_awaited_once()


class TestMigoDHWTemperatureNumber:
    """Tests for the DHW target temperature entity."""

    @pytest.fixture
    def entity(self, mock_coordinator, api):
        """Create the entity under test."""
        return MigoDHWTemperatureNumber(mock_coordinator, "gateway_001", api)

    def test_native_value_uses_cache_when_present(self, entity, mock_coordinator) -> None:
        """A cached value takes priority over API data."""
        mock_coordinator.get_cached_value.return_value = 58
        assert entity.native_value == 58

    def test_native_value_falls_back_to_device_data(self, entity, mock_coordinator) -> None:
        """Without a cached value, the gateway's setpoint is used."""
        mock_coordinator.devices["gateway_001"]["dhw_setpoint_temperature"] = 50
        assert entity.native_value == 50

    def test_native_value_defaults_when_absent(self, entity) -> None:
        """With no cache and no API value, the documented default applies."""
        assert entity.native_value == DEFAULT_DHW_TEMPERATURE

    async def test_async_set_native_value(self, entity, mock_coordinator) -> None:
        """Setting a value calls the API with the gateway's home_id, then caches and refreshes."""
        await entity.async_set_native_value(55.0)

        entity._api.set_dhw_temperature.assert_awaited_once_with(
            home_id="home_123", module_id="gateway_001", temperature=55
        )
        mock_coordinator.set_cached_value.assert_called_once_with("dhw_temperature_gateway_001", 55)
        mock_coordinator.async_request_refresh.assert_awaited_once()


class TestMigoHysteresisNumber:
    """Tests for the hysteresis threshold entity."""

    @pytest.fixture
    def entity(self, mock_coordinator, api):
        """Create the entity under test."""
        return MigoHysteresisNumber(mock_coordinator, "home_123", "gateway_001", api)

    def test_native_value_uses_cache_when_present(self, entity, mock_coordinator) -> None:
        """A cached value takes priority over API data."""
        mock_coordinator.get_cached_value.return_value = 0.8
        assert entity.native_value == 0.8

    def test_native_value_falls_back_to_device_data(self, entity, mock_coordinator) -> None:
        """Without a cached value, hysteresis is derived from the deadband."""
        mock_coordinator.devices["gateway_001"]["simple_heating_algo_deadband"] = 15
        assert entity.native_value == 1.6

    def test_native_value_defaults_when_absent(self, entity) -> None:
        """With no cache and no API value, the documented default applies."""
        assert entity.native_value == DEFAULT_HYSTERESIS

    async def test_async_set_native_value(self, entity, mock_coordinator) -> None:
        """Setting a value calls the API, caches it, and refreshes."""
        await entity.async_set_native_value(0.42)

        entity._api.set_hysteresis.assert_awaited_once_with(device_id="gateway_001", hysteresis=0.4)
        mock_coordinator.set_cached_value.assert_called_once_with("hysteresis_gateway_001", 0.4)
        mock_coordinator.async_request_refresh.assert_awaited_once()


class TestMigoHeatingCurveNumber:
    """Tests for the heating curve (slope) entity."""

    @pytest.fixture
    def entity(self, mock_coordinator, api):
        """Create the entity under test."""
        return MigoHeatingCurveNumber(mock_coordinator, "home_123", "gateway_001", api)

    def test_native_value_uses_cache_when_present(self, entity, mock_coordinator) -> None:
        """A cached value takes priority over API data."""
        mock_coordinator.get_cached_value.return_value = 2.0
        assert entity.native_value == 2.0

    def test_native_value_falls_back_to_device_data(self, entity, mock_coordinator) -> None:
        """Without a cached value, the UI slope is derived from the API's stored value."""
        mock_coordinator.devices["gateway_001"]["heating_curve"] = 17
        assert entity.native_value == 1.7

    def test_native_value_defaults_when_absent(self, entity) -> None:
        """With no cache and no API value, the documented default applies."""
        assert entity.native_value == DEFAULT_HEATING_CURVE

    async def test_async_set_native_value(self, entity, mock_coordinator) -> None:
        """Setting a value calls the API, caches it, and refreshes."""
        await entity.async_set_native_value(1.73)

        entity._api.set_heating_curve.assert_awaited_once_with(device_id="gateway_001", slope=1.7)
        mock_coordinator.set_cached_value.assert_called_once_with("heating_curve_gateway_001", 1.7)
        mock_coordinator.async_request_refresh.assert_awaited_once()
