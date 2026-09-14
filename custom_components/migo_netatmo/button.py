"""Button platform for MiGO integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, override

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_HEATING_CURVE, DEVICE_TYPE_GATEWAY
from .entity import MigoThermostatHomeControlEntity, register_dynamic_entities
from .helpers import generate_unique_id, get_devices_by_type

if TYPE_CHECKING:
    from . import MigoConfigEntry
    from .api import MigoApi
    from .coordinator import MigoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Serialise write commands against the cloud API
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MigoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MiGO button entities."""
    data = entry.runtime_data
    coordinator = data.coordinator

    def _gateway_buttons(device_id: str) -> list[ButtonEntity]:
        buttons: list[ButtonEntity] = []
        home_id = coordinator.devices.get(device_id, {}).get("home_id")
        if home_id:
            buttons.append(
                MigoResetHeatingCurveButton(
                    coordinator=coordinator,
                    home_id=home_id,
                    device_id=device_id,
                    api=data.api,
                )
            )
        return buttons

    register_dynamic_entities(
        entry,
        coordinator,
        async_add_entities,
        get_current_ids=lambda: get_devices_by_type(coordinator, DEVICE_TYPE_GATEWAY),
        create_entities=_gateway_buttons,
    )


class MigoResetHeatingCurveButton(MigoThermostatHomeControlEntity, ButtonEntity):
    """MiGO Reset heating curve button entity.

    Stays Configuration (unlike the refresh buttons): it directly acts on
    the Heating curve setting, so it belongs grouped with it.

    Not a true "reset to factory default": the API has no such concept for
    this value (`changeheatingcurve` is a plain set, nothing more), and
    nothing this integration calls ever echoes back a per-installation
    default to reset to - it's installation-specific (heating type,
    radiator sizing, ...), confirmed to vary between at least two real
    installations captured during development (1.4 and 2.6). This writes
    `DEFAULT_HEATING_CURVE` (`const.py`), a plain constant - update it there
    to match your own installation's calibrated value if this button's
    result doesn't match what the MiGo app shows.
    """

    _attr_translation_key = "reset_heating_curve"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        home_id: str,
        device_id: str,
        api: MigoApi,
    ) -> None:
        """Initialize the reset heating curve button entity."""
        super().__init__(coordinator, home_id, api)
        self._device_id = device_id
        self._attr_unique_id = generate_unique_id("reset_heating_curve", device_id)

    @override
    async def async_press(self) -> None:
        """Handle the button press - reset heating curve to default."""
        _LOGGER.debug(
            "Resetting heating curve to default (%s) for device %s",
            DEFAULT_HEATING_CURVE,
            self._device_id,
        )
        await self._call_api_optimistically(
            self._api.set_heating_curve,
            cache_key=f"heating_curve_{self._device_id}",
            optimistic_value=DEFAULT_HEATING_CURVE,
            device_id=self._device_id,
            slope=DEFAULT_HEATING_CURVE,
        )
