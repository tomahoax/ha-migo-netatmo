"""Tests for the binary_sensor platform."""

from __future__ import annotations

from custom_components.migo_netatmo.binary_sensor import (
    GATEWAY_BINARY_SENSORS,
    THERMOSTAT_BINARY_SENSORS,
    MigoGatewayBinarySensor,
    MigoThermostatBinarySensor,
)


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
