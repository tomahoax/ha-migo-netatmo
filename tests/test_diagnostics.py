"""Tests for MiGO (Netatmo) diagnostics."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.migo_netatmo.diagnostics import async_get_config_entry_diagnostics

REDACTED = "**REDACTED**"


async def test_diagnostics_redacts_credentials(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test diagnostics content and credential redaction."""
    diagnostics = await async_get_config_entry_diagnostics(hass, init_integration)

    assert diagnostics["entry"]["data"]["username"] == REDACTED
    assert diagnostics["entry"]["data"]["password"] == REDACTED

    # Coordinator data is present and support-relevant IDs are kept
    assert "home_123" in diagnostics["homes"]
    assert "room_456" in diagnostics["rooms"]
    assert set(diagnostics["devices"]) == {"gateway_001", "module_789"}
    assert "gateway_001" in diagnostics["consumption"]
