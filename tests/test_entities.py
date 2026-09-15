"""Cross-platform entity tests that don't belong to a single platform's own test file.

Per-platform tests moved out to their own files: test_climate.py, test_switch.py,
test_binary_sensor.py, test_sensor.py, test_datetime.py, test_entity.py,
test_number.py.
"""

from __future__ import annotations

from unittest.mock import create_autospec

from homeassistant.const import EntityCategory

from custom_components.migo_netatmo.api import MigoApi
from custom_components.migo_netatmo.binary_sensor import MigoAwayModeBinarySensor
from custom_components.migo_netatmo.switch import (
    MigoAnticipationSwitch,
    MigoAwayModeSwitch,
    MigoDHWAlwaysOnSwitch,
    MigoDHWSwitch,
)

# mock_coordinator fixture lives in conftest.py, shared across test modules.


class TestDevicePageOrganization:
    """Regression guard for the Controls/Configuration/Diagnostic reorganization.

    See docs/entities.md's "Device Page Organization" section: operational
    toggles and quick actions (including Refresh) land in Controls (no
    entity_category), setpoints/tuning values and the buttons acting on them
    stay in Configuration, and read-only companions to a Controls entity
    move to Diagnostic. These assertions exist so the grouping can't
    silently drift.
    """

    # Note: entity_category must be read from an instance's `.entity_category`
    # property, not `_attr_entity_category` on the class - Home Assistant's
    # CachedProperty machinery turns the latter into a descriptor at class
    # definition time, so accessing it unbound (on the class, no instance)
    # returns the descriptor object rather than the configured value.

    def test_dhw_boost_switch_is_primary_control(self, mock_coordinator):
        """DHW boost is an operational toggle, not a configuration value."""
        api = create_autospec(MigoApi, instance=True)
        entity = MigoDHWSwitch(mock_coordinator, "gateway_001", api)
        assert entity.entity_category is None

    def test_anticipation_switch_is_primary_control(self, mock_coordinator):
        """Heating anticipation is an operational toggle, not a configuration value."""
        api = create_autospec(MigoApi, instance=True)
        entity = MigoAnticipationSwitch(mock_coordinator, "home_123", api)
        assert entity.entity_category is None

    def test_away_mode_switch_is_primary_control(self, mock_coordinator):
        """Away mode switch stays a primary control (unchanged by this reorganization)."""
        api = create_autospec(MigoApi, instance=True)
        entity = MigoAwayModeSwitch(mock_coordinator, "gateway_001", api)
        assert entity.entity_category is None

    def test_dhw_always_on_switch_is_primary_control(self, mock_coordinator):
        """DHW always-on is an operational override, same reasoning as DHW boost."""
        api = create_autospec(MigoApi, instance=True)
        entity = MigoDHWAlwaysOnSwitch(mock_coordinator, "gateway_001", api)
        assert entity.entity_category is None

    def test_away_mode_binary_sensor_is_diagnostic(self, mock_coordinator):
        """Read-only companion to the switch: moved out of Sensors to avoid duplicating it."""
        entity = MigoAwayModeBinarySensor(mock_coordinator, "gateway_001")
        assert entity.entity_category == EntityCategory.DIAGNOSTIC
