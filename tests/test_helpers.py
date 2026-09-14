"""Tests for MiGo (Netatmo) helper functions added for the forum feedback work.

Covers timetable resolution (current_week_minutes, resolve_timetable_zone),
therm/event schedule pairing (get_event_schedule), and boiler mode
derivation (derive_boiler_mode).
"""

from __future__ import annotations

from datetime import datetime

from custom_components.migo_netatmo.const import (
    BOILER_MODE_DHW_ONLY,
    BOILER_MODE_FROST_GUARD,
    BOILER_MODE_NORMAL,
)
from custom_components.migo_netatmo.helpers import (
    current_week_minutes,
    derive_boiler_mode,
    get_event_schedule,
    resolve_timetable_zone,
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
