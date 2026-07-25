"""Registry contract tests for MiGo (Netatmo).

These tests pin the exact set of unique_ids, entity_ids and device
identifiers the integration registers. Any refactoring that changes one
of these breaks users' recorder history, dashboards and customisations:
such a change must be intentional and called out in release notes, never
an accident. Update the expected lists only in that case.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.migo_netatmo.const import DOMAIN

# (domain, unique_id, entity_id) for the standard one-home, one-room,
# gateway + thermostat setup from conftest fixtures.
EXPECTED_ENTITIES: list[tuple[str, str, str]] = [
    ("binary_sensor", "migo_netatmo_boiler_error_gateway_001", "binary_sensor.my_home_gateway_boiler_error"),
    ("binary_sensor", "migo_netatmo_boiler_status_module_789", "binary_sensor.my_home_thermostat_boiler_status"),
    ("binary_sensor", "migo_netatmo_ebus_error_gateway_001", "binary_sensor.my_home_gateway_ebus_error"),
    ("binary_sensor", "migo_netatmo_reachable_module_789", "binary_sensor.my_home_thermostat_device_reachable"),
    ("button", "migo_netatmo_refresh_gateway_gateway_001", "button.my_home_gateway_refresh"),
    ("button", "migo_netatmo_refresh_thermostat_module_789", "button.my_home_thermostat_refresh"),
    ("button", "migo_netatmo_reset_heating_curve_gateway_001", "button.my_home_thermostat_reset_heating_curve"),
    ("climate", "migo_netatmo_climate_room_456", "climate.my_home_thermostat_thermostat"),
    ("number", "migo_netatmo_dhw_temperature_gateway_001", "number.my_home_gateway_dhw_temperature"),
    ("number", "migo_netatmo_heating_curve_gateway_001", "number.my_home_thermostat_heating_curve"),
    ("number", "migo_netatmo_hysteresis_gateway_001", "number.my_home_thermostat_hysteresis_threshold"),
    ("number", "migo_netatmo_manual_setpoint_duration_home_123", "number.my_home_thermostat_manual_setpoint_duration"),
    ("number", "migo_netatmo_temp_offset_room_456", "number.my_home_thermostat_temperature_offset"),
    ("select", "migo_netatmo_schedule_home_123", "select.my_home_gateway_active_schedule"),
    ("sensor", "migo_netatmo_battery_module_789", "sensor.my_home_thermostat_battery"),
    ("sensor", "migo_netatmo_boiler_runtime_gateway_001", "sensor.my_home_gateway_daily_boiler_runtime"),
    ("sensor", "migo_netatmo_gateway_firmware_gateway_001", "sensor.my_home_gateway_gateway_firmware"),
    ("sensor", "migo_netatmo_outdoor_temp_gateway_001", "sensor.my_home_gateway_outdoor_temperature"),
    ("sensor", "migo_netatmo_rf_module_789", "sensor.my_home_thermostat_rf_signal"),
    ("sensor", "migo_netatmo_temp_room_456", "sensor.my_home_thermostat_living_room_temperature"),
    ("sensor", "migo_netatmo_thermostat_firmware_module_789", "sensor.my_home_thermostat_thermostat_firmware"),
    ("sensor", "migo_netatmo_wifi_gateway_001", "sensor.my_home_gateway_wifi_signal"),
    ("switch", "migo_netatmo_anticipation_home_123", "switch.my_home_thermostat_heating_anticipation"),
    ("switch", "migo_netatmo_dhw_gateway_001", "switch.my_home_gateway_dhw_boost"),
]


# Entities a fresh install gets disabled: verbose diagnostics that most users
# have no use for. Enabling one of these later is the user's choice, and the
# registry keeps that choice, so this set only governs new installs.
EXPECTED_DISABLED_BY_DEFAULT: list[str] = [
    "sensor.my_home_gateway_gateway_firmware",
    "sensor.my_home_gateway_wifi_signal",
    "sensor.my_home_thermostat_rf_signal",
    "sensor.my_home_thermostat_thermostat_firmware",
]


async def test_entity_registry_contract(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """The full (domain, unique_id, entity_id) set must stay stable."""
    entity_registry = er.async_get(hass)

    actual = sorted(
        (entry.domain, entry.unique_id, entry.entity_id)
        for entry in er.async_entries_for_config_entry(entity_registry, init_integration.entry_id)
    )

    assert actual == EXPECTED_ENTITIES


async def test_disabled_by_default_contract(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Exactly the verbose diagnostics must be disabled on a fresh install.

    Pins the entity-disabled-by-default rule in both directions: a useful entity
    silently becoming disabled is as much a regression as a noisy one becoming
    enabled. Battery and the error binary sensors must stay enabled in
    particular, since the README's automation examples build on them.
    """
    entity_registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(entity_registry, init_integration.entry_id)

    disabled = sorted(entry.entity_id for entry in entries if entry.disabled_by is not None)
    assert disabled == EXPECTED_DISABLED_BY_DEFAULT

    enabled = {entry.entity_id for entry in entries if entry.disabled_by is None}
    for documented in (
        "sensor.my_home_thermostat_battery",
        "binary_sensor.my_home_gateway_boiler_error",
        "binary_sensor.my_home_gateway_ebus_error",
    ):
        assert documented in enabled, f"{documented} is used by a README automation example"


async def test_device_registry_contract(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Device identifiers, names, models and linking must stay stable."""
    device_registry = dr.async_get(hass)

    gateway = device_registry.async_get_device(identifiers={(DOMAIN, "gateway_001")})
    assert gateway is not None
    assert gateway.name == "My Home Gateway"
    assert gateway.model == "NAVaillant"
    # No MAC connection: "gateway_001" is not MAC-shaped. Registering an
    # arbitrary API string as a MAC would let it merge with an unrelated device
    # in the user's home, since HA joins registry entries sharing a connection.
    assert gateway.connections == set()
    assert gateway.via_device_id is None

    thermostat = device_registry.async_get_device(identifiers={(DOMAIN, "module_789")})
    assert thermostat is not None
    assert thermostat.name == "My Home Thermostat"
    assert thermostat.model == "NAThermVaillant"
    # The thermostat is bridged through the gateway
    assert thermostat.via_device_id == gateway.id

    devices = dr.async_entries_for_config_entry(device_registry, init_integration.entry_id)
    assert len(devices) == 2


async def test_mac_shaped_ids_do_get_a_mac_connection(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    patch_migo_api: MagicMock,
    homes_data_response: dict,
) -> None:
    """A real gateway id IS a MAC, and must still register the connection.

    Covers the other branch of _looks_like_mac: the guard must not be so strict
    that it drops the connection for the ids the API actually returns.
    """
    real_mac = "70:ee:50:6b:e3:6a"
    home = homes_data_response["body"]["homes"][0]
    home["modules"][0]["id"] = real_mac
    home["modules"][1]["bridge"] = real_mac

    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    device_registry = dr.async_get(hass)
    gateway = device_registry.async_get_device(identifiers={(DOMAIN, real_mac)})
    assert gateway is not None
    assert gateway.connections == {(dr.CONNECTION_NETWORK_MAC, real_mac)}
