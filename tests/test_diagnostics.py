"""Tests for MiGO (Netatmo) diagnostics.

The load-bearing test here is test_no_sensitive_key_survives: it walks the whole
diagnostics payload and fails on ANY sensitive key that still carries its value.
The previous version of this file only asserted on username and password, which
is why invitation_code, oem_serial, boiler_id and every home and room name went
unredacted for as long as they did: the redaction worked, the list of what to
redact was incomplete, and no test looked.

Users treat a REDACTED marker as a promise that the file is safe to attach to a
public issue. This test is that promise.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.migo_netatmo.diagnostics import async_get_config_entry_diagnostics
from custom_components.migo_netatmo.redact import REDACTED, SENSITIVE_KEYS


def _leaks(value: Any, path: str = "") -> list[str]:
    """Return the path of every sensitive key still carrying its own value."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            here = f"{path}.{key}" if path else str(key)
            if key in SENSITIVE_KEYS and item != REDACTED:
                found.append(f"{here} = {item!r}")
            else:
                found.extend(_leaks(item, here))
    elif isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            found.extend(_leaks(item, f"{path}[{i}]"))
    return found


async def test_no_sensitive_key_survives(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """No sensitive key anywhere in the payload may keep its value."""
    diagnostics = await async_get_config_entry_diagnostics(hass, init_integration)

    assert _leaks(diagnostics) == []


async def test_specific_fields_that_leaked_are_redacted(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Named regression guard on the fields the security audit found exposed.

    The generic walk above would catch these too, but naming them means a future
    change to SENSITIVE_KEYS cannot quietly stop covering them.
    """
    diagnostics = await async_get_config_entry_diagnostics(hass, init_integration)

    home = diagnostics["homes"]["home_123"]
    assert home["coordinates"] == REDACTED
    assert home["city"] == REDACTED
    assert home["invitation_code"] == REDACTED
    assert home["name"] == REDACTED

    assert diagnostics["entry"]["data"]["username"] == REDACTED
    assert diagnostics["entry"]["data"]["password"] == REDACTED

    # Nested inside a list, two levels down.
    assert diagnostics["homes"]["home_123"]["rooms"][0]["name"] == REDACTED
    assert diagnostics["devices"]["gateway_001"]["oem_serial"] == REDACTED


async def test_support_relevant_identifiers_are_kept(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Redaction must not go so far that diagnostics stop being useful."""
    diagnostics = await async_get_config_entry_diagnostics(hass, init_integration)

    assert "home_123" in diagnostics["homes"]
    assert "room_456" in diagnostics["rooms"]
    assert set(diagnostics["devices"]) == {"gateway_001", "module_789"}
    assert "gateway_001" in diagnostics["consumption"]

    # Ids, types and the polling interval survive: they are what makes a bug
    # report actionable, and they identify neither the person nor the place.
    assert diagnostics["homes"]["home_123"]["id"] == "home_123"
    assert diagnostics["devices"]["gateway_001"]["type"] == "NAVaillant"
    assert diagnostics["devices"]["module_789"]["bridge"] == "gateway_001"


async def test_redaction_does_not_damage_coordinator_data(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Downloading diagnostics must not corrupt the running integration."""
    coordinator = init_integration.runtime_data.coordinator

    await async_get_config_entry_diagnostics(hass, init_integration)

    assert coordinator.homes["home_123"]["name"] == "My Home"
    assert coordinator.rooms["room_456"]["name"] == "Living Room"
