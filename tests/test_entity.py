"""Tests for entity.py/entity_device_info.py's device-info helpers."""

from __future__ import annotations

from custom_components.migo_netatmo.entity import MigoThermostatEntity

# mock_coordinator fixture lives in conftest.py, shared across test modules.


class TestThermostatEntityDeviceInfo:
    """Tests for MigoThermostatEntity.device_info's via_device linkage.

    Regression guard: an earlier version linked to the parent gateway via
    `via_device_id`, a registry-internal ID pre-resolved via a device
    registry lookup - `via_device` (the plain `(DOMAIN, identifier)` tuple
    form) was believed to be deprecated and at risk of raising instead of
    warning under some caller attributions. Neither belief survived contact
    with a real Home Assistant install: `via_device_id` is not a real
    `DeviceInfo` key in any released version - confirmed live, CI failing
    with `TypeError: DeviceRegistry.async_get_or_create() got an unexpected
    keyword argument 'via_device_id'` on every thermostat-attached entity,
    on every setup - and `via_device` itself carries no deprecation notice
    at all in the same real, currently-supported Home Assistant versions.
    Reverted to `via_device`, which Home Assistant itself resolves to the
    registry's internal ID (see `DeviceEntry.via_device_id` in
    test_unique_ids.py's `test_device_registry_contract`).
    """

    def test_omits_via_device_without_bridge(self, mock_coordinator):
        """No parent gateway known for this thermostat - no crash, just omitted."""
        entity = MigoThermostatEntity(mock_coordinator, "module_789")
        info = entity.device_info
        assert "via_device" not in info

    def test_sets_via_device_to_gateway_identifiers(self, mock_coordinator):
        """Links to the parent gateway via its (DOMAIN, identifier) tuple."""
        mock_coordinator.devices["module_789"]["bridge"] = "gateway_001"
        entity = MigoThermostatEntity(mock_coordinator, "module_789")
        info = entity.device_info
        assert info["via_device"] == ("migo_netatmo", "gateway_001")
