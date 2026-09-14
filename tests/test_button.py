"""Tests for the button platform (reset heating curve).

No Refresh button tests: `MigoGatewayRefreshButton`/`MigoThermostatRefreshButton`
were removed (see CHANGELOG) - `CoordinatorEntity.async_update()` (driving Home
Assistant's built-in `homeassistant.update_entity` action) already does exactly
what those buttons did, for every entity, so nothing depended on dedicated ones.
"""

from __future__ import annotations

from unittest.mock import MagicMock, create_autospec

import pytest

from custom_components.migo_netatmo.api import MigoApi
from custom_components.migo_netatmo.button import MigoResetHeatingCurveButton
from custom_components.migo_netatmo.const import DEFAULT_HEATING_CURVE


class TestMigoResetHeatingCurveButton:
    """Tests for the reset-heating-curve button."""

    @pytest.fixture
    def button(self, mock_coordinator):
        """Create the button entity under test."""
        api = create_autospec(MigoApi, instance=True)
        api.set_heating_curve.return_value = {"status": "ok"}
        entity = MigoResetHeatingCurveButton(mock_coordinator, "home_123", "gateway_001", api)
        entity.async_write_ha_state = MagicMock()
        return entity

    async def test_async_press_resets_curve_and_clears_cache(self, button, mock_coordinator) -> None:
        """Pressing resets the curve to the default slope, caches it, and refreshes."""
        await button.async_press()

        button._api.set_heating_curve.assert_awaited_once_with(device_id="gateway_001", slope=DEFAULT_HEATING_CURVE)
        mock_coordinator.set_cached_value.assert_called_once_with("heating_curve_gateway_001", DEFAULT_HEATING_CURVE)
        mock_coordinator.async_request_refresh.assert_awaited_once()
