"""Tests for live entity creation when new rooms/devices appear (dynamic-devices).

Entities must show up as soon as the coordinator sees a new room or device id,
without requiring the config entry to be reloaded. Looked up by unique_id via
the entity registry rather than a guessed entity_id, since a newly-appeared
room with no thermostat resolves its device_info to a fallback device whose
friendly name isn't obvious.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.migo_netatmo.const import DOMAIN


async def test_new_room_creates_climate_entity_without_reload(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    homes_data_response: dict,
) -> None:
    """A room appearing in a later refresh gets a live climate entity."""
    entity_registry = er.async_get(hass)
    new_unique_id = "migo_netatmo_climate_room_999"

    assert entity_registry.async_get_entity_id("climate", DOMAIN, new_unique_id) is None

    homes_data_response["body"]["homes"][0]["rooms"].append(
        {
            "id": "room_999",
            "name": "Bedroom",
            "type": "bedroom",
            "module_ids": [],
        }
    )

    coordinator = init_integration.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    entity_id = entity_registry.async_get_entity_id("climate", DOMAIN, new_unique_id)
    assert entity_id is not None
    assert hass.states.get(entity_id) is not None


async def test_new_gateway_creates_switch_entities_without_reload(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    homes_data_response: dict,
    home_status_response: dict,
) -> None:
    """A gateway appearing in a later refresh gets its switch entities live."""
    entity_registry = er.async_get(hass)
    new_unique_id = "migo_netatmo_dhw_gateway_002"

    assert entity_registry.async_get_entity_id("switch", DOMAIN, new_unique_id) is None

    homes_data_response["body"]["homes"][0]["modules"].append(
        {"id": "gateway_002", "type": "NAVaillant", "subtype": "NAEbusSdbg"}
    )
    home_status_response["body"]["home"]["modules"].append(
        {"id": "gateway_002", "type": "NAVaillant", "dhw_enabled": False}
    )

    coordinator = init_integration.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    entity_id = entity_registry.async_get_entity_id("switch", DOMAIN, new_unique_id)
    assert entity_id is not None
    assert hass.states.get(entity_id) is not None


async def test_reachable_room_and_device_ids_are_not_recreated(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    home_status_response: dict,
) -> None:
    """A refresh with no new ids must not raise or duplicate any entity."""
    entity_registry = er.async_get(hass)
    before = {
        entry.unique_id for entry in er.async_entries_for_config_entry(entity_registry, init_integration.entry_id)
    }

    coordinator = init_integration.runtime_data.coordinator
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    after = {entry.unique_id for entry in er.async_entries_for_config_entry(entity_registry, init_integration.entry_id)}
    assert after == before
