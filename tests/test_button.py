"""Tests for the button platform (manual refresh, reset heating curve)."""

from __future__ import annotations

from unittest.mock import create_autospec

import pytest

from custom_components.migo_netatmo.api import MigoApi
from custom_components.migo_netatmo.button import (
    MigoGatewayRefreshButton,
    MigoResetHeatingCurveButton,
    MigoThermostatRefreshButton,
)
from custom_components.migo_netatmo.const import DEFAULT_HEATING_CURVE


class TestMigoGatewayRefreshButton:
    """Tests for the gateway refresh button."""

    async def test_async_press_requests_refresh(self, mock_coordinator) -> None:
        """Pressing the button requests a coordinator refresh."""
        button = MigoGatewayRefreshButton(mock_coordinator, "gateway_001")

        await button.async_press()

        mock_coordinator.async_request_refresh.assert_awaited_once()


class TestMigoThermostatRefreshButton:
    """Tests for the thermostat refresh button."""

    async def test_async_press_requests_refresh(self, mock_coordinator) -> None:
        """Pressing the button requests a coordinator refresh."""
        button = MigoThermostatRefreshButton(mock_coordinator, "home_123", "module_789")

        await button.async_press()

        mock_coordinator.async_request_refresh.assert_awaited_once()


class TestMigoResetHeatingCurveButton:
    """Tests for the reset-heating-curve button."""

    @pytest.fixture
    def button(self, mock_coordinator):
        """Create the button entity under test."""
        api = create_autospec(MigoApi, instance=True)
        api.set_heating_curve.return_value = {"status": "ok"}
        return MigoResetHeatingCurveButton(mock_coordinator, "home_123", "gateway_001", api)

    async def test_async_press_resets_curve_and_clears_cache(self, button, mock_coordinator) -> None:
        """Pressing resets the curve to the default slope, caches it, and refreshes."""
        await button.async_press()

        button._api.set_heating_curve.assert_awaited_once_with(device_id="gateway_001", slope=DEFAULT_HEATING_CURVE)
        mock_coordinator.set_cached_value.assert_called_once_with("heating_curve_gateway_001", DEFAULT_HEATING_CURVE)
        mock_coordinator.async_request_refresh.assert_awaited_once()
