"""Tests for the binary_sensor platform."""

from __future__ import annotations

from custom_components.migo_netatmo.binary_sensor import (
    GATEWAY_BINARY_SENSORS,
    THERMOSTAT_BINARY_SENSORS,
    MigoBinarySensorEntityDescription,
    MigoGatewayBinarySensor,
    MigoRoomBinarySensor,
    MigoThermostatBinarySensor,
)

# No entities ship in ROOM_BINARY_SENSORS today, but the class itself must
# still behave correctly for the day a room-based binary sensor is added.
_ROOM_TEST_DESCRIPTION = MigoBinarySensorEntityDescription(
    key="test_flag",
    data_key="test_flag",
    unique_id_key="test_flag",
)


class TestMigoRoomBinarySensor:
    """Tests for the (currently unused, but supported) room binary sensor class."""

    def test_is_on_reads_room_data(self, mock_coordinator) -> None:
        """is_on reads the description's data_key straight from room data."""
        mock_coordinator.rooms["room_456"]["test_flag"] = True
        sensor = MigoRoomBinarySensor(mock_coordinator, "room_456", _ROOM_TEST_DESCRIPTION)

        assert sensor.is_on is True
        assert sensor.unique_id == "migo_netatmo_test_flag_room_456"

    def test_ignores_reachability_is_copied_from_description(self, mock_coordinator) -> None:
        """_ignore_reachable mirrors the description's ignores_reachability flag."""
        description = MigoBinarySensorEntityDescription(
            key="reachable",
            data_key="reachable",
            unique_id_key="reachable",
            ignores_reachability=True,
        )
        sensor = MigoRoomBinarySensor(mock_coordinator, "room_456", description)

        assert sensor._ignore_reachable is True


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
