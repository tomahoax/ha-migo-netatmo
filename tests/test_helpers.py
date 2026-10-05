"""Tests for MiGo (Netatmo) helper functions.

Covers timetable resolution (current_week_minutes, resolve_timetable_zone),
therm/event schedule pairing (get_event_schedule), boiler mode derivation
(derive_boiler_mode), the shared Away lookup (is_home_away), and the
smaller pure utilities in helpers.py (safe_float, generate_unique_id,
get_devices_by_type, get_home_id_or_raise, get_gateway_mac_for_home,
get_thermostat_for_room).
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.migo_netatmo.const import (
    BOILER_MODE_DHW_ONLY,
    BOILER_MODE_FROST_GUARD,
    BOILER_MODE_NORMAL,
)
from custom_components.migo_netatmo.helpers import (
    MINUTES_PER_WEEK,
    current_week_minutes,
    derive_boiler_mode,
    generate_unique_id,
    get_devices_by_type,
    get_event_schedule,
    get_gateway_mac_for_home,
    get_home_id_or_raise,
    get_rooms_for_home,
    get_thermostat_for_room,
    is_home_away,
    resolve_timetable_zone,
    safe_float,
)


class TestCurrentWeekMinutes:
    """Tests for current_week_minutes."""

    def test_monday_midnight(self):
        """Monday 00:00 is minute 0."""
        now = datetime(2026, 1, 5, 0, 0)  # a Monday
        assert current_week_minutes(now) == 0

    def test_monday_morning(self):
        """Monday 07:45 matches the forum's real-world example offset."""
        now = datetime(2026, 1, 5, 7, 45)
        assert current_week_minutes(now) == 465

    def test_sunday_end_of_week(self):
        """Sunday 23:59 is the last minute of the week."""
        now = datetime(2026, 1, 11, 23, 59)  # a Sunday
        assert current_week_minutes(now) == 6 * 1440 + 23 * 60 + 59


class TestResolveTimetableZone:
    """Tests for resolve_timetable_zone."""

    def test_empty_timetable(self):
        """An empty timetable resolves to nothing."""
        assert resolve_timetable_zone([], 100) is None

    def test_picks_last_entry_not_in_future(self):
        """Uses the forum's real timetable: zone 1 @0, zone 7 @465, zone 0 @555."""
        timetable = [
            {"zone_id": 1, "m_offset": 0},
            {"zone_id": 7, "m_offset": 465},
            {"zone_id": 0, "m_offset": 555},
        ]
        assert resolve_timetable_zone(timetable, 500) == 7
        assert resolve_timetable_zone(timetable, 600) == 0
        assert resolve_timetable_zone(timetable, 465) == 7

    def test_wraps_to_last_entry_before_first_offset(self):
        """Before the week's first offset, the active slot is the last one (Sunday carry-over)."""
        timetable = [
            {"zone_id": 1, "m_offset": 60},
            {"zone_id": 0, "m_offset": 500},
        ]
        assert resolve_timetable_zone(timetable, 30) == 0

    def test_unsorted_timetable(self):
        """The API does not guarantee ordering; entries out of order still resolve correctly."""
        timetable = [
            {"zone_id": 0, "m_offset": 555},
            {"zone_id": 1, "m_offset": 0},
            {"zone_id": 7, "m_offset": 465},
        ]
        assert resolve_timetable_zone(timetable, 500) == 7

    def test_missing_m_offset_defaults_to_zero(self):
        """A missing m_offset defaults to 0 rather than raising."""
        timetable = [{"zone_id": 3}]
        assert resolve_timetable_zone(timetable, 10) == 3

    def test_out_of_range_week_minutes_wraps(self):
        """A week_minutes outside [0, MINUTES_PER_WEEK) is wrapped, not trusted as-is.

        The sole real caller (current_week_minutes) always returns an
        in-range value, but the function's own contract shouldn't silently
        misbehave for a hypothetical future caller that doesn't.
        """
        timetable = [
            {"zone_id": 1, "m_offset": 0},
            {"zone_id": 7, "m_offset": 465},
            {"zone_id": 0, "m_offset": 555},
        ]
        assert resolve_timetable_zone(timetable, 500 + MINUTES_PER_WEEK) == 7
        assert resolve_timetable_zone(timetable, 500 - MINUTES_PER_WEEK) == 7


class TestGetEventSchedule:
    """Tests for get_event_schedule (therm/event pairing)."""

    def test_no_schedules(self):
        """A home with no schedules resolves to nothing."""
        assert get_event_schedule({}) is None

    def test_linked_schedules_dict_mapping(self):
        """A {therm_id: event_id} mapping is preferred over the selected fallback."""
        home = {
            "schedules": [
                {"id": "t1", "type": "therm", "selected": True},
                {"id": "e1", "type": "event", "selected": False, "name": "Linked"},
                {"id": "e2", "type": "event", "selected": True, "name": "Fallback"},
            ],
            "linked_schedules": {"t1": "e1"},
        }
        schedule = get_event_schedule(home)
        assert schedule is not None
        assert schedule["id"] == "e1"

    def test_linked_schedules_list_of_pairs(self):
        """A list of [therm_id, event_id] pairs is also handled."""
        home = {
            "schedules": [
                {"id": "t1", "type": "therm", "selected": True},
                {"id": "e1", "type": "event", "selected": False},
            ],
            "linked_schedules": [["t1", "e1"]],
        }
        schedule = get_event_schedule(home)
        assert schedule["id"] == "e1"

    def test_linked_schedules_list_of_dicts(self):
        """A list of {arbitrary_key: id, ...} pair dicts is also handled."""
        home = {
            "schedules": [
                {"id": "t1", "type": "therm", "selected": True},
                {"id": "e1", "type": "event", "selected": False},
            ],
            "linked_schedules": [{"therm_id": "t1", "event_id": "e1"}],
        }
        schedule = get_event_schedule(home)
        assert schedule["id"] == "e1"

    def test_linked_schedules_dict_reverse_mapping(self):
        """A reverse {event_id: therm_id} mapping is also handled."""
        home = {
            "schedules": [
                {"id": "t1", "type": "therm", "selected": True},
                {"id": "e1", "type": "event", "selected": False},
            ],
            "linked_schedules": {"e1": "t1"},
        }
        schedule = get_event_schedule(home)
        assert schedule["id"] == "e1"

    def test_linked_schedules_list_no_match_falls_back(self):
        """A linked_schedules list that doesn't mention the selected therm id falls back."""
        home = {
            "schedules": [
                {"id": "t1", "type": "therm", "selected": True},
                {"id": "e1", "type": "event", "selected": True, "name": "Selected"},
            ],
            "linked_schedules": [["other_t", "other_e"]],
        }
        schedule = get_event_schedule(home)
        assert schedule["id"] == "e1"

    def test_falls_back_to_selected_event_without_linked_schedules(self):
        """Without linked_schedules, falls back to the independently selected event schedule."""
        home = {
            "schedules": [
                {"id": "t1", "type": "therm", "selected": True},
                {"id": "e1", "type": "event", "selected": True, "name": "Selected"},
            ],
        }
        schedule = get_event_schedule(home)
        assert schedule["id"] == "e1"

    def test_falls_back_when_linked_schedules_unresolvable(self):
        """An unresolvable linked_schedules value falls back rather than returning nothing."""
        home = {
            "schedules": [
                {"id": "t1", "type": "therm", "selected": True},
                {"id": "e1", "type": "event", "selected": True, "name": "Selected"},
            ],
            "linked_schedules": {"other_therm": "other_event"},
        }
        schedule = get_event_schedule(home)
        assert schedule["id"] == "e1"

    def test_no_selected_therm_and_no_selected_event(self):
        """Nothing selected anywhere resolves to nothing."""
        home = {
            "schedules": [
                {"id": "t1", "type": "therm", "selected": False},
                {"id": "e1", "type": "event", "selected": False},
            ],
        }
        assert get_event_schedule(home) is None


class TestDeriveBoilerMode:
    """Tests for derive_boiler_mode, using the forum's 5-state table."""

    def test_normal(self):
        """Normal: therm_mode schedule, room home."""
        assert derive_boiler_mode("schedule", ["home"]) == BOILER_MODE_NORMAL

    def test_frost_guard_from_home(self):
        """Veille (standby): therm_mode itself is hg."""
        assert derive_boiler_mode("hg", ["home"]) == BOILER_MODE_FROST_GUARD

    def test_dhw_only_from_room(self):
        """Eau chaude seulement: the room is hg while therm_mode stays schedule."""
        assert derive_boiler_mode("schedule", ["hg"]) == BOILER_MODE_DHW_ONLY

    def test_away_is_normal(self):
        """Away is orthogonal: it doesn't change the boiler quick-action mode."""
        assert derive_boiler_mode("away", ["home"]) == BOILER_MODE_NORMAL

    def test_frost_guard_wins_over_room_hg(self):
        """Real standby takes priority even if a room also happens to read hg."""
        assert derive_boiler_mode("hg", ["hg"]) == BOILER_MODE_FROST_GUARD

    def test_no_rooms(self):
        """A home with no rooms defaults to normal rather than raising."""
        assert derive_boiler_mode("schedule", []) == BOILER_MODE_NORMAL


class TestGetRoomsForHome:
    """Tests for get_rooms_for_home."""

    def test_filters_by_home_id(self):
        """Only rooms belonging to the given home are returned."""
        coordinator = MagicMock()
        coordinator.rooms = {
            "room_1": {"id": "room_1", "home_id": "home_a"},
            "room_2": {"id": "room_2", "home_id": "home_b"},
            "room_3": {"id": "room_3", "home_id": "home_a"},
        }
        rooms = get_rooms_for_home(coordinator, "home_a")
        assert {r["id"] for r in rooms} == {"room_1", "room_3"}

    def test_no_matching_rooms(self):
        """A home with no rooms returns an empty list rather than raising."""
        coordinator = MagicMock()
        coordinator.rooms = {"room_1": {"id": "room_1", "home_id": "home_b"}}
        assert get_rooms_for_home(coordinator, "home_a") == []


class TestIsHomeAway:
    """Tests for is_home_away - the shared lookup MigoAwayModeSwitch,
    MigoAwayModeBinarySensor and MigoDHWScheduleBinarySensor all use.
    """

    def _coordinator(self, cached=None, home_data=None):
        coordinator = MagicMock()
        coordinator.get_cached_value = MagicMock(return_value=cached)
        coordinator.homes = {"home_123": home_data} if home_data is not None else {}
        return coordinator

    def test_reads_optimistic_cache_first(self):
        """A cached value (written by MigoAwayModeSwitch) wins over API data."""
        coordinator = self._coordinator(cached=True, home_data={"therm_mode": "schedule"})
        assert is_home_away(coordinator, "gateway_001", {"home_id": "home_123"}) is True

    def test_falls_back_to_api_when_no_cache(self):
        """Once the cache is cleared, falls back to the API-echoed therm_mode."""
        coordinator = self._coordinator(cached=None, home_data={"therm_mode": "away"})
        assert is_home_away(coordinator, "gateway_001", {"home_id": "home_123"}) is True

        coordinator = self._coordinator(cached=None, home_data={"therm_mode": "schedule"})
        assert is_home_away(coordinator, "gateway_001", {"home_id": "home_123"}) is False

    def test_none_when_home_id_missing(self):
        """Unresolvable (None) if the device has no home_id."""
        coordinator = self._coordinator(cached=None)
        assert is_home_away(coordinator, "gateway_001", {}) is None

    def test_none_when_home_unresolved(self):
        """Unresolvable (None) if the home_id doesn't match any known home."""
        coordinator = self._coordinator(cached=None)
        assert is_home_away(coordinator, "gateway_001", {"home_id": "home_123"}) is None


class TestSafeFloat:
    """Tests for safe_float."""

    def test_none_returns_default(self) -> None:
        """None input returns the default unchanged."""
        assert safe_float(None) is None
        assert safe_float(None, default=1.0) == 1.0

    def test_valid_values_convert(self) -> None:
        """Numeric strings and numbers convert to float."""
        assert safe_float("21.5") == 21.5
        assert safe_float(20) == 20.0

    def test_invalid_value_returns_default(self) -> None:
        """A non-numeric value falls back to the default."""
        assert safe_float("not_a_number") is None
        assert safe_float("not_a_number", default=0.0) == 0.0

    def test_invalid_type_returns_default(self) -> None:
        """A value that can't be coerced to float falls back to the default."""
        assert safe_float(object(), default=-1.0) == -1.0


class TestGenerateUniqueId:
    """Tests for generate_unique_id."""

    def test_format(self) -> None:
        """The unique ID follows the migo_netatmo_{type}_{id} convention."""
        assert generate_unique_id("temp", "room_456") == "migo_netatmo_temp_room_456"


def _make_coordinator(
    devices: dict[str, dict[str, Any]] | None = None,
    rooms: dict[str, dict[str, Any]] | None = None,
) -> Any:
    """Build a minimal stand-in exposing the .devices/.rooms attributes these helpers read."""
    return SimpleNamespace(devices=devices or {}, rooms=rooms or {})


class TestGetDevicesByType:
    """Tests for get_devices_by_type."""

    def test_filters_by_type(self) -> None:
        """Only devices matching the requested type are returned."""
        coordinator = _make_coordinator(
            devices={
                "gw1": {"type": "NAVaillant"},
                "therm1": {"type": "NAThermVaillant"},
                "therm2": {"type": "NAThermVaillant"},
            }
        )
        result = get_devices_by_type(coordinator, "NAThermVaillant")
        assert set(result) == {"therm1", "therm2"}

    def test_no_match_returns_empty_dict(self) -> None:
        """No devices of the requested type returns an empty dict."""
        coordinator = _make_coordinator(devices={"gw1": {"type": "NAVaillant"}})
        assert get_devices_by_type(coordinator, "Unknown") == {}


class TestGetHomeIdOrRaise:
    """Tests for get_home_id_or_raise."""

    def test_returns_home_id_when_present(self) -> None:
        """A data dict with home_id returns it unchanged."""
        assert get_home_id_or_raise({"home_id": "home_123"}, "room", "room_456") == "home_123"

    def test_raises_when_missing(self) -> None:
        """A data dict without home_id raises a translated HomeAssistantError."""
        with pytest.raises(HomeAssistantError):
            get_home_id_or_raise({}, "room", "room_456")


class TestGetGatewayMacForHome:
    """Tests for get_gateway_mac_for_home."""

    def test_finds_matching_gateway(self) -> None:
        """The gateway device ID for the given home is returned."""
        coordinator = _make_coordinator(
            devices={
                "70:ee:50:6b:e3:6a": {"type": "NAVaillant", "home_id": "home_123"},
                "other_gw": {"type": "NAVaillant", "home_id": "home_999"},
            }
        )
        assert get_gateway_mac_for_home(coordinator, "home_123") == "70:ee:50:6b:e3:6a"

    def test_no_match_returns_none(self) -> None:
        """No gateway for the given home returns None."""
        coordinator = _make_coordinator(devices={})
        assert get_gateway_mac_for_home(coordinator, "home_123") is None


class TestGetThermostatForRoom:
    """Tests for get_thermostat_for_room."""

    def test_finds_thermostat_via_module_ids(self) -> None:
        """The thermostat module linked to the room is returned."""
        coordinator = _make_coordinator(
            devices={"therm1": {"type": "NAThermVaillant"}},
            rooms={"room_456": {"module_ids": ["therm1"]}},
        )
        assert get_thermostat_for_room(coordinator, "room_456") == "therm1"

    def test_no_module_ids_returns_none(self) -> None:
        """A room without module_ids returns None."""
        coordinator = _make_coordinator(rooms={"room_456": {}})
        assert get_thermostat_for_room(coordinator, "room_456") is None

    def test_module_not_a_thermostat_returns_none(self) -> None:
        """A linked module that isn't a thermostat type returns None."""
        coordinator = _make_coordinator(
            devices={"gw1": {"type": "NAVaillant"}},
            rooms={"room_456": {"module_ids": ["gw1"]}},
        )
        assert get_thermostat_for_room(coordinator, "room_456") is None
