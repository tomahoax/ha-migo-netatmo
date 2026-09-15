"""Tests for MiGo (Netatmo) integration setup and unload."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.migo_netatmo import async_remove_config_entry_device
from custom_components.migo_netatmo.api import MigoApiError, MigoAuthError
from custom_components.migo_netatmo.const import DOMAIN


async def test_setup_entry(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test the integration sets up and populates runtime data."""
    assert init_integration.state is ConfigEntryState.LOADED

    data = init_integration.runtime_data
    assert data.api is not None
    assert data.coordinator.homes.keys() == {"home_123"}
    assert data.coordinator.rooms.keys() == {"room_456"}
    assert set(data.coordinator.devices) == {"gateway_001", "module_789"}


async def test_setup_entry_creates_entities(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test that entities exist and have real states after setup."""
    climate = hass.states.get("climate.my_home_thermostat_thermostat")
    assert climate is not None
    assert climate.state == "auto"
    assert climate.attributes["current_temperature"] == 21.5
    assert climate.attributes["temperature"] == 20.0

    # The signal-strength and firmware sensors are disabled by default
    # (entity-disabled-by-default), so they exist in the entity registry but have
    # no state; ebus_error stays enabled. The exact set is pinned by
    # test_unique_ids.test_disabled_by_default_contract.
    ebus_error = hass.states.get("binary_sensor.my_home_gateway_ebus_error")
    assert ebus_error is not None
    assert ebus_error.state == "off"

    battery = hass.states.get("sensor.my_home_thermostat_battery")
    assert battery is not None
    assert battery.state == "85"
    assert battery.attributes["battery_state"] == "high"

    boiler = hass.states.get("binary_sensor.my_home_thermostat_boiler_status")
    assert boiler is not None
    assert boiler.state == "on"


async def test_unload_entry(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test the integration unloads cleanly."""
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()

    assert init_integration.state is ConfigEntryState.NOT_LOADED


async def test_setup_entry_auth_error_starts_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    patch_migo_api: MagicMock,
) -> None:
    """Test that an auth failure at setup puts the entry in reauth."""
    patch_migo_api.authenticate.side_effect = MigoAuthError("bad credentials")
    mock_config_entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(flow["handler"] == "migo_netatmo" and flow["context"]["source"] == "reauth" for flow in flows)


async def test_setup_entry_api_error_retries(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    patch_migo_api: MagicMock,
) -> None:
    """Test that a connection failure at setup schedules a retry."""
    patch_migo_api.authenticate.side_effect = MigoApiError("cannot reach API")
    mock_config_entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_remove_stale_device(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test that only devices unknown to the API can be removed."""
    device_registry = dr.async_get(hass)

    live_device = device_registry.async_get_device(identifiers={(DOMAIN, "gateway_001")})
    assert live_device is not None
    assert not await async_remove_config_entry_device(hass, init_integration, live_device)

    stale_device = device_registry.async_get_or_create(
        config_entry_id=init_integration.entry_id,
        identifiers={(DOMAIN, "gateway_gone")},
        name="Old Gateway",
    )
    assert await async_remove_config_entry_device(hass, init_integration, stale_device)


async def test_stale_device_removed_automatically(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """A device the API stops reporting is removed without user action."""
    device_registry = dr.async_get(hass)
    stale = device_registry.async_get_or_create(
        config_entry_id=init_integration.entry_id,
        identifiers={(DOMAIN, "gateway_gone")},
        name="Old Gateway",
    )
    assert stale.id in {d.id for d in dr.async_entries_for_config_entry(device_registry, init_integration.entry_id)}

    coordinator = init_integration.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    remaining = {
        identifier
        for device in dr.async_entries_for_config_entry(device_registry, init_integration.entry_id)
        for domain, identifier in device.identifiers
        if domain == DOMAIN
    }
    assert "gateway_gone" not in remaining
    # The devices the API still reports are untouched
    assert {"gateway_001", "module_789"} <= remaining


async def test_failed_refresh_removes_nothing(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    patch_migo_api: MagicMock,
) -> None:
    """A failed refresh must not wipe every device.

    _async_update_data clears the stores before repopulating them, so without the
    last_update_success guard an outage would look like "the API reports nothing"
    and take every device with it.
    """
    device_registry = dr.async_get(hass)
    before = {d.id for d in dr.async_entries_for_config_entry(device_registry, init_integration.entry_id)}
    assert len(before) == 2

    patch_migo_api.get_homes_data.side_effect = MigoApiError("API is down")
    coordinator = init_integration.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert not coordinator.last_update_success
    after = {d.id for d in dr.async_entries_for_config_entry(device_registry, init_integration.entry_id)}
    assert after == before


async def test_empty_refresh_removes_nothing(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    patch_migo_api: MagicMock,
) -> None:
    """A syntactically valid but empty response must not wipe every device.

    This one succeeds, so last_update_success stays True and only the
    non-empty-known-ids guard stands between it and deleting everything.
    """
    device_registry = dr.async_get(hass)
    before = {d.id for d in dr.async_entries_for_config_entry(device_registry, init_integration.entry_id)}

    patch_migo_api.get_homes_data.return_value = {"body": {"homes": []}}
    coordinator = init_integration.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success
    assert not coordinator.devices
    after = {d.id for d in dr.async_entries_for_config_entry(device_registry, init_integration.entry_id)}
    assert after == before


async def test_no_device_removal_while_caches_are_empty(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test nothing is removable when the coordinator caches cannot be trusted.

    _async_update_data clears the stores before repopulating them, and an auth
    failure part-way through leaves the entry loaded with them empty. Without a
    guard, every device would look unreported and a live one could be deleted.
    """
    device_registry = dr.async_get(hass)
    live_device = device_registry.async_get_device(identifiers={(DOMAIN, "gateway_001")})
    assert live_device is not None

    coordinator = init_integration.runtime_data.coordinator
    coordinator.devices = {}
    coordinator.homes = {}

    assert not await async_remove_config_entry_device(hass, init_integration, live_device)

    # Also refuse after a failed refresh, even if stale data is still around.
    coordinator.devices = {"gateway_001": {"id": "gateway_001"}}
    coordinator.last_update_success = False
    stale_device = device_registry.async_get_or_create(
        config_entry_id=init_integration.entry_id,
        identifiers={(DOMAIN, "gateway_gone")},
        name="Old Gateway",
    )
    assert not await async_remove_config_entry_device(hass, init_integration, stale_device)


async def test_entities_unavailable_when_module_unreachable(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    patch_migo_api: MagicMock,
    home_status_response: dict,
) -> None:
    """Test entities become unavailable when their module is unreachable."""
    home = home_status_response["body"]["home"]
    home["rooms"][0]["reachable"] = False
    home["modules"][1]["reachable"] = False  # thermostat

    coordinator = init_integration.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get("climate.my_home_thermostat_thermostat").state == "unavailable"
    assert hass.states.get("sensor.my_home_thermostat_battery").state == "unavailable"
    # The connectivity diagnostic must stay available and report the outage
    assert hass.states.get("binary_sensor.my_home_thermostat_device_reachable").state == "off"
    # Gateway entities are unaffected
    assert hass.states.get("binary_sensor.my_home_gateway_ebus_error").state == "off"


async def test_unload_clears_credentials(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Unloading must not leave a live password and tokens in memory.

    The API object stays reachable through entry.runtime_data after unload.
    Hygiene rather than a vulnerability: a memory capture taken after a user
    removes the integration should not still contain working credentials.
    """
    api = init_integration.runtime_data.api

    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()

    api.clear_credentials.assert_called_once()
