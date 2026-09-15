"""Tests for the sensor platform (boiler mode)."""

from __future__ import annotations

import pytest

from custom_components.migo_netatmo.const import (
    BOILER_MODE_DHW_ONLY,
    BOILER_MODE_FROST_GUARD,
    BOILER_MODE_NORMAL,
    MODE_FROST_GUARD,
    MODE_HOME,
    MODE_SCHEDULE,
)
from custom_components.migo_netatmo.sensor import MigoBoilerModeSensor

# mock_coordinator fixture lives in conftest.py, shared across test modules.


class TestMigoBoilerModeSensor:
    """Tests for the derived boiler quick-action mode sensor."""

    @pytest.fixture
    def sensor(self, mock_coordinator):
        """Create the boiler mode sensor."""
        return MigoBoilerModeSensor(mock_coordinator, "gateway_001")

    def test_normal(self, sensor, mock_coordinator):
        """Normal: home therm_mode schedule, room mode home."""
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_SCHEDULE
        mock_coordinator.rooms["room_456"]["therm_setpoint_mode"] = MODE_HOME
        assert sensor.native_value == BOILER_MODE_NORMAL

    def test_dhw_only(self, sensor, mock_coordinator):
        """DHW only: a room is hg while home therm_mode stays schedule."""
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_SCHEDULE
        mock_coordinator.rooms["room_456"]["therm_setpoint_mode"] = MODE_FROST_GUARD
        assert sensor.native_value == BOILER_MODE_DHW_ONLY

    def test_frost_guard(self, sensor, mock_coordinator):
        """Frost guard: home therm_mode itself is hg."""
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_FROST_GUARD
        assert sensor.native_value == BOILER_MODE_FROST_GUARD

    def test_none_when_home_unresolved(self, sensor, mock_coordinator):
        """Unavailable (None) if the device has no home_id."""
        mock_coordinator.devices["gateway_001"] = {"id": "gateway_001"}
        assert sensor.native_value is None

    def test_ignores_rooms_from_other_homes(self, sensor, mock_coordinator):
        """A DHW-only room in a different home must not leak into this gateway's mode.

        Regression guard: native_value used to scan every room in every
        home before filtering by home_id inline, rather than through a
        home-scoped lookup - same result today, but this pins the scoping
        so a future change to that lookup can't silently regress it.
        """
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_SCHEDULE
        mock_coordinator.rooms["room_456"]["therm_setpoint_mode"] = MODE_HOME
        mock_coordinator.rooms["other_room"] = {
            "id": "other_room",
            "home_id": "other_home",
            "therm_setpoint_mode": MODE_FROST_GUARD,
        }

        assert sensor.native_value == BOILER_MODE_NORMAL
