"""Tests for entity.py/entity_device_info.py's device-info helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from custom_components.migo_netatmo.entity import MigoThermostatEntity
from custom_components.migo_netatmo.entity_device_info import _entity_config_entry_id, _resolve_via_device_id

# mock_coordinator fixture lives in conftest.py, shared across test modules.


class TestResolveViaDeviceId:
    """Tests for _resolve_via_device_id.

    Regression guard: `via_device` (the identifiers-tuple form) is
    deprecated and, unlike most Home Assistant deprecation warnings, a
    caller Home Assistant attributes to a *core* integration (which can
    happen for entities added outside their platform's normal initial
    setup, e.g. as a side effect of an entity registry edit) makes it raise
    instead of just log - this broke entity setup live once already. All
    four `device_info` properties that link to a parent gateway now resolve
    `via_device_id` through this function instead.

    Uses `async_get_device_by_identifier` (config-entry-scoped), not
    `async_get_device` - that one is deprecated too (a live warning caught
    after the first fix shipped), and the exact same "raises instead of
    warns under some caller attributions" risk applies to it as well.
    """

    def test_none_when_hass_not_set(self):
        """No hass yet (as in every device_info test in this file, none of which set it)."""
        assert _resolve_via_device_id(None, "entry_1", "gateway_001") is None

    def test_none_when_config_entry_id_not_set(self):
        """No platform/config entry yet either - same "not fully added" case."""
        hass = MagicMock()
        assert _resolve_via_device_id(hass, None, "gateway_001") is None

    def test_none_when_gateway_not_registered(self):
        """The gateway device hasn't been registered yet - omit rather than raise."""
        hass = MagicMock()
        with patch("custom_components.migo_netatmo.entity_device_info.dr.async_get") as mock_async_get:
            mock_async_get.return_value.async_get_device_by_identifier.return_value = None
            assert _resolve_via_device_id(hass, "entry_1", "gateway_001") is None

    def test_returns_registry_device_id_when_found(self):
        """Resolves to the registry's own internal device_id, not the identifiers tuple."""
        hass = MagicMock()
        with patch("custom_components.migo_netatmo.entity_device_info.dr.async_get") as mock_async_get:
            mock_async_get.return_value.async_get_device_by_identifier.return_value = MagicMock(
                id="internal_device_id_123"
            )
            result = _resolve_via_device_id(hass, "entry_1", "gateway_001")

        assert result == "internal_device_id_123"
        mock_async_get.return_value.async_get_device_by_identifier.assert_called_once_with(
            ("migo_netatmo", "gateway_001"), "entry_1"
        )


class TestEntityConfigEntryId:
    """Tests for _entity_config_entry_id."""

    def test_none_when_platform_not_set(self):
        """Matches every other test's entity construction - no platform, no crash."""
        entity = MagicMock(spec=[])
        assert _entity_config_entry_id(entity) is None

    def test_none_when_platform_has_no_config_entry(self):
        entity = MagicMock()
        entity.platform.config_entry = None
        assert _entity_config_entry_id(entity) is None

    def test_returns_platform_config_entry_id(self):
        entity = MagicMock()
        entity.platform.config_entry.entry_id = "entry_123"
        assert _entity_config_entry_id(entity) == "entry_123"


class TestThermostatEntityDeviceInfo:
    """Tests for MigoThermostatEntity.device_info's via_device_id linkage."""

    def test_omits_via_device_id_without_hass(self, mock_coordinator):
        """No hass set (matches every other test's entity construction) - no crash, just omitted."""
        mock_coordinator.devices["module_789"]["bridge"] = "gateway_001"
        entity = MigoThermostatEntity(mock_coordinator, "module_789")
        info = entity.device_info
        assert "via_device_id" not in info

    def test_sets_via_device_id_when_gateway_registered(self, mock_coordinator):
        """Links to the parent gateway's registry device_id when it can be resolved."""
        mock_coordinator.devices["module_789"]["bridge"] = "gateway_001"
        entity = MigoThermostatEntity(mock_coordinator, "module_789")
        entity.hass = MagicMock()
        entity.platform = MagicMock()
        entity.platform.config_entry.entry_id = "entry_1"

        with patch("custom_components.migo_netatmo.entity_device_info.dr.async_get") as mock_async_get:
            mock_async_get.return_value.async_get_device_by_identifier.return_value = MagicMock(
                id="internal_gateway_id"
            )
            info = entity.device_info

        assert info["via_device_id"] == "internal_gateway_id"
