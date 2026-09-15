"""Tests for the binary_sensor platform."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.migo_netatmo.binary_sensor import (
    GATEWAY_BINARY_SENSORS,
    THERMOSTAT_BINARY_SENSORS,
    MigoAwayModeBinarySensor,
    MigoDHWScheduleBinarySensor,
    MigoGatewayBinarySensor,
    MigoThermostatBinarySensor,
)
from custom_components.migo_netatmo.const import MODE_AWAY, MODE_SCHEDULE


class TestMigoGatewayBinarySensor:
    """Tests for gateway-attached binary sensors (ebus_error, boiler_error)."""

    def test_ebus_error_reflects_raw_boolean(self, mock_coordinator) -> None:
        """ebus_error has no value_fn: the raw boolean passes through."""
        mock_coordinator.devices["gateway_001"]["ebus_error"] = True
        description = GATEWAY_BINARY_SENSORS[0]
        assert description.key == "ebus_error"

        sensor = MigoGatewayBinarySensor(mock_coordinator, "gateway_001", description)

        assert sensor.is_on is True

    def test_boiler_error_uses_value_fn_to_coerce_list(self, mock_coordinator) -> None:
        """boiler_error's value_fn coerces the raw list-or-None into a bool."""
        description = GATEWAY_BINARY_SENSORS[1]
        assert description.key == "boiler_error"

        mock_coordinator.devices["gateway_001"]["boiler_error"] = ["E01"]
        sensor_with_error = MigoGatewayBinarySensor(mock_coordinator, "gateway_001", description)
        assert sensor_with_error.is_on is True

        mock_coordinator.devices["gateway_001"]["boiler_error"] = None
        sensor_without_error = MigoGatewayBinarySensor(mock_coordinator, "gateway_001", description)
        assert sensor_without_error.is_on is None


class TestMigoThermostatBinarySensor:
    """Tests for thermostat-attached binary sensors (boiler_status, reachable)."""

    def test_boiler_status_reflects_device_data(self, mock_coordinator) -> None:
        """boiler_status has no value_fn: the raw boolean passes through."""
        description = THERMOSTAT_BINARY_SENSORS[0]
        assert description.key == "boiler_status"
        mock_coordinator.devices["module_789"]["boiler_status"] = True

        sensor = MigoThermostatBinarySensor(mock_coordinator, "module_789", description)

        assert sensor.is_on is True

    def test_reachable_sensor_ignores_reachability_for_availability(self, mock_coordinator) -> None:
        """The 'reachable' diagnostic sensor stays available even when unreachable."""
        description = THERMOSTAT_BINARY_SENSORS[1]
        assert description.key == "reachable"
        assert description.ignores_reachability is True

        mock_coordinator.devices["module_789"]["reachable"] = False
        sensor = MigoThermostatBinarySensor(mock_coordinator, "module_789", description)

        assert sensor.is_on is False
        assert sensor._ignore_reachable is True


class TestMigoAwayModeBinarySensor:
    """Tests for the read-only away mode binary sensor."""

    @pytest.fixture
    def binary_sensor(self, mock_coordinator):
        """Create the away mode binary sensor."""
        return MigoAwayModeBinarySensor(mock_coordinator, "gateway_001")

    def test_is_on_false_when_schedule(self, binary_sensor, mock_coordinator):
        """Off when therm_mode is schedule."""
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_SCHEDULE
        assert binary_sensor.is_on is False

    def test_is_on_true_when_away(self, binary_sensor, mock_coordinator):
        """On when therm_mode is away."""
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_AWAY
        assert binary_sensor.is_on is True

    def test_is_on_none_when_home_unresolved(self, binary_sensor, mock_coordinator):
        """Unavailable (None) if the device has no home_id."""
        mock_coordinator.devices["gateway_001"] = {"id": "gateway_001"}
        assert binary_sensor.is_on is None

    def test_is_on_reads_optimistic_cache_first(self, binary_sensor, mock_coordinator):
        """Reflects a MigoAwayModeSwitch toggle immediately, not one refresh behind.

        Regression guard: this read-only companion used to read
        coordinator.homes directly, so it visibly disagreed with the switch
        (which does check its own cache) until the next coordinator refresh.
        """
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_SCHEDULE
        mock_coordinator.get_cached_value = MagicMock(return_value=True)

        assert binary_sensor.is_on is True


class TestMigoDHWScheduleBinarySensor:
    """Tests for the scheduled DHW state binary sensor.

    Uses the forum's real timetable example: zone 1 (Night, dhw off) @00:00,
    zone 7 (Matin, dhw off) @465 (Monday 07:45), zone 0 (dhw on) @555
    (Monday 09:15).
    """

    EVENT_SCHEDULE = {
        "id": "event_1",
        "name": "Vacances int Light",
        "type": "event",
        "selected": True,
        "timetable": [
            {"zone_id": 1, "m_offset": 0},
            {"zone_id": 7, "m_offset": 465},
            {"zone_id": 0, "m_offset": 555},
        ],
        "zones": [
            {"id": 1, "name": "Nuit", "modules": [{"id": "gateway_001", "dhw_enabled": False}]},
            {"id": 7, "name": "Matin", "modules": [{"id": "gateway_001", "dhw_enabled": False}]},
            {"id": 0, "name": "Comfort", "modules": [{"id": "gateway_001", "dhw_enabled": True}]},
        ],
    }

    @pytest.fixture
    def binary_sensor(self, mock_coordinator):
        """Create the DHW schedule binary sensor with an event schedule wired in."""
        mock_coordinator.homes["home_123"]["schedules"] = [self.EVENT_SCHEDULE]
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_SCHEDULE
        return MigoDHWScheduleBinarySensor(mock_coordinator, "gateway_001")

    def test_resolves_off_slot(self, binary_sensor, freezer):
        """Monday 08:00 is within the 'Matin' slot (dhw off).

        The offset is explicit (-08:00) rather than bare UTC: the real
        `hass` fixture behind `enable_custom_integrations` (autouse for
        every test, conftest.py) pins `dt_util`'s default timezone to
        US/Pacific for the test's duration, so `current_week_minutes()`'s
        `dt_util.now()` reads the frozen instant back in that zone, not UTC.
        """
        freezer.move_to("2026-01-05 08:00:00-08:00")  # a Monday, US/Pacific wall-clock
        assert binary_sensor.is_on is False
        assert binary_sensor.extra_state_attributes["zone_id"] == 7
        assert binary_sensor.extra_state_attributes["zone_name"] == "Matin"
        assert binary_sensor.extra_state_attributes["overridden_by_away"] is False

    def test_resolves_on_slot(self, binary_sensor, freezer):
        """Monday 10:00 is within the last slot (dhw on)."""
        freezer.move_to("2026-01-05 10:00:00-08:00")  # a Monday
        assert binary_sensor.is_on is True
        assert binary_sensor.extra_state_attributes["zone_id"] == 0

    def test_forced_off_when_away(self, binary_sensor, mock_coordinator, freezer):
        """Away mode forces the sensor off even if the resolved slot has DHW on."""
        freezer.move_to("2026-01-05 10:00:00-08:00")  # resolves to the "on" slot
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_AWAY

        assert binary_sensor.is_on is False
        assert binary_sensor.extra_state_attributes["overridden_by_away"] is True

    def test_unavailable_without_event_schedule(self, mock_coordinator, freezer):
        """No event schedule at all resolves to unavailable (None), never a guessed value."""
        mock_coordinator.homes["home_123"]["schedules"] = []
        sensor = MigoDHWScheduleBinarySensor(mock_coordinator, "gateway_001")

        freezer.move_to("2026-01-05 10:00:00-08:00")
        assert sensor.is_on is None

    def test_uses_single_module_when_id_absent(self, mock_coordinator, freezer):
        """Falls back to a zone's single module even without a matching id (forum's real payload)."""
        schedule = {
            **self.EVENT_SCHEDULE,
            "zones": [
                {"id": 1, "modules": [{"dhw_enabled": False}]},
                {"id": 7, "name": "Matin", "modules": [{"dhw_enabled": False}]},
                {"id": 0, "modules": [{"dhw_enabled": True}]},
            ],
        }
        mock_coordinator.homes["home_123"]["schedules"] = [schedule]
        sensor = MigoDHWScheduleBinarySensor(mock_coordinator, "gateway_001")

        freezer.move_to("2026-01-05 10:00:00-08:00")
        assert sensor.is_on is True

    def test_forced_off_when_away_without_event_schedule(self, mock_coordinator, freezer):
        """Away still forces off even when the schedule itself can't be resolved.

        Regression guard: the away override used to be applied only on the
        fully-resolved path, so an unresolvable schedule during Away
        reported unknown (None) instead of the documented unconditional off.
        """
        mock_coordinator.homes["home_123"]["schedules"] = []
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_AWAY
        sensor = MigoDHWScheduleBinarySensor(mock_coordinator, "gateway_001")

        freezer.move_to("2026-01-05 10:00:00-08:00")
        assert sensor.is_on is False
        assert sensor.extra_state_attributes["overridden_by_away"] is True

    def test_forced_off_when_away_with_unresolvable_zone(self, mock_coordinator, freezer):
        """Same as above, for a schedule whose timetable resolves to no matching zone."""
        schedule = {**self.EVENT_SCHEDULE, "zones": []}
        mock_coordinator.homes["home_123"]["schedules"] = [schedule]
        mock_coordinator.homes["home_123"]["therm_mode"] = MODE_AWAY
        sensor = MigoDHWScheduleBinarySensor(mock_coordinator, "gateway_001")

        freezer.move_to("2026-01-05 10:00:00-08:00")
        assert sensor.is_on is False
        assert sensor.extra_state_attributes["overridden_by_away"] is True

    def test_resolve_cached_per_coordinator_update(self, binary_sensor, freezer):
        """is_on and extra_state_attributes share one resolution per update cycle.

        Regression guard: _resolve() used to fully recompute (including a
        timetable sort) on every property access - once from is_on, once
        from extra_state_attributes.
        """
        freezer.move_to("2026-01-05 08:00:00-08:00")

        first = binary_sensor.is_on
        attrs = binary_sensor.extra_state_attributes
        assert first is False
        assert attrs["zone_id"] == 7
        # extra_state_attributes must not have mutated the cached dict that
        # is_on's own result came from (an aliasing hazard the cache adds).
        assert binary_sensor.is_on is False

        binary_sensor.async_write_ha_state = MagicMock()
        binary_sensor._handle_coordinator_update()
        assert binary_sensor._resolved_cache is None
