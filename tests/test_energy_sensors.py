"""Tests for the measured energy sensors.

These exist because the boiler reports real energy, not just runtime. The MiGO app
displays it, and the API returns it from the same getmeasure call the integration
already makes, split heating vs domestic hot water for both gas and electricity.

Two properties matter and are easy to get wrong:

- The unit. The API reports Wh at whole-kWh resolution; the sensors report kWh.
  Getting this backwards would be wrong by a factor of 1000 and would look
  plausible on a dashboard.
- The index order. getmeasure returns one value per requested measure type,
  positionally, so const.MEASURE_TYPES *is* the schema. Nothing in the type system
  ties the indices in _consumption_record to that tuple, so a test has to.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.migo_netatmo.const import MEASURE_TYPES, WH_PER_KWH
from custom_components.migo_netatmo.coordinator import MigoDataUpdateCoordinator, _consumption_record
from custom_components.migo_netatmo.sensor import ENERGY_SENSORS

# Mirrors the conftest consumption fixture's most recent row, which is the one the
# sensors read: [boiler_on, boiler_off, gas_heat, gas_dhw, elec_heat, elec_dhw]
EXPECTED_KWH = {
    "sensor.my_home_gateway_gas_for_heating": 18.0,
    "sensor.my_home_gateway_gas_for_hot_water": 2.0,
    "sensor.my_home_gateway_electricity_for_heating": 0.15,
    "sensor.my_home_gateway_electricity_for_hot_water": 0.075,
}


class TestMeasureOrder:
    """The positional contract between MEASURE_TYPES and _consumption_record."""

    def test_record_fields_follow_measure_types_order(self) -> None:
        """A row of distinct values must land on the field for its own index.

        This is the drift guard: reorder MEASURE_TYPES without reordering the
        indices in _consumption_record, and gas would be reported as electricity.
        """
        # One distinguishable value per position.
        row = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0]

        record = _consumption_record(row, timestamp=1704240000)

        assert record["timestamp"] == 1704240000
        for index, measure_type in enumerate(MEASURE_TYPES):
            assert record[measure_type] == row[index], (  # type: ignore[literal-required]
                f"{measure_type} is at index {index} in MEASURE_TYPES but "
                f"_consumption_record put {record.get(measure_type)} there"  # type: ignore[call-overload]
            )

    def test_all_six_types_are_requested(self) -> None:
        """All six come back in one request, so there is no reason to ask for less."""
        assert len(MEASURE_TYPES) == 6
        assert MEASURE_TYPES[0] == "sum_boiler_on"
        # The French spelling is the API's, and getting it wrong returns an empty
        # series rather than an error.
        assert "sum_energy_gaz_heating" in MEASURE_TYPES
        assert "sum_energy_gas_heating" not in MEASURE_TYPES

    def test_a_short_row_yields_a_short_record(self) -> None:
        """A boiler reporting only the two time measures must not raise."""
        record = _consumption_record([3600.0, 82800.0], timestamp=1)

        assert record["sum_boiler_on"] == 3600.0
        assert "sum_energy_gaz_heating" not in record

    def test_an_empty_row_yields_only_a_timestamp(self) -> None:
        """The degenerate case still produces a usable record."""
        assert _consumption_record([], timestamp=42) == {"timestamp": 42}


class TestEnergySensorDescriptions:
    """The descriptions themselves, before any Home Assistant is involved."""

    @pytest.mark.parametrize("description", ENERGY_SENSORS, ids=lambda d: d.key)
    def test_is_shaped_for_the_energy_dashboard(self, description) -> None:
        """device_class energy in kWh is exactly what the dashboard accepts.

        Anything else and the sensor silently fails to appear in the picker, which
        is the failure this whole feature exists to fix.
        """
        assert description.device_class is SensorDeviceClass.ENERGY
        assert description.native_unit_of_measurement == UnitOfEnergy.KILO_WATT_HOUR
        assert description.state_class is SensorStateClass.TOTAL_INCREASING

    def test_unique_id_keys_are_distinct(self) -> None:
        """A collision would make two sensors fight over one registry entry."""
        keys = [d.unique_id_key for d in ENERGY_SENSORS]
        assert len(keys) == len(set(keys)) == 4


class TestEnergySensorStates:
    """End-to-end against a real Home Assistant instance."""

    async def test_reports_kwh_not_wh(
        self,
        hass: HomeAssistant,
        init_integration: MockConfigEntry,
    ) -> None:
        """The API reports Wh; the sensors must divide by 1000.

        A factor-of-1000 error here would look entirely plausible on a dashboard,
        which is why the expected values are spelled out rather than computed.
        """
        for entity_id, expected in EXPECTED_KWH.items():
            state = hass.states.get(entity_id)
            assert state is not None, f"{entity_id} does not exist"
            assert float(state.state) == pytest.approx(expected), entity_id

    async def test_attributes_are_dashboard_ready(
        self,
        hass: HomeAssistant,
        init_integration: MockConfigEntry,
    ) -> None:
        """What the Energy dashboard's picker actually filters on."""
        state = hass.states.get("sensor.my_home_gateway_gas_for_heating")
        assert state is not None
        assert state.attributes["device_class"] == "energy"
        assert state.attributes["unit_of_measurement"] == "kWh"
        assert state.attributes["state_class"] == "total_increasing"

    async def test_unavailable_measure_yields_unknown(
        self,
        hass: HomeAssistant,
        init_integration: MockConfigEntry,
        patch_migo_api: MagicMock,
    ) -> None:
        """A boiler reporting only boiler times must not fabricate a zero.

        Reporting 0 kWh would enter the Energy dashboard's statistics as a real
        measurement, which is worse than reporting nothing.
        """
        patch_migo_api.get_measure.return_value = {
            "body": {"1704240000": [5400, 81000]},
            "status": "ok",
        }
        coordinator: MigoDataUpdateCoordinator = init_integration.runtime_data.coordinator

        await coordinator.async_refresh()
        await hass.async_block_till_done()

        for entity_id in EXPECTED_KWH:
            state = hass.states.get(entity_id)
            assert state is not None
            assert state.state == "unknown", entity_id

        # The runtime sensor, which only needs the first two values, still works.
        runtime = hass.states.get("sensor.my_home_gateway_daily_boiler_runtime")
        assert runtime is not None
        assert float(runtime.state) == 5400.0

    async def test_wh_per_kwh_is_the_only_conversion(self) -> None:
        """Guards against someone 'fixing' the constant."""
        assert WH_PER_KWH == 1000
