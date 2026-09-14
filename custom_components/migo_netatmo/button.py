"""Button platform for MiGO integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_HEATING_CURVE, DEVICE_TYPE_GATEWAY, DEVICE_TYPE_THERMOSTAT, MODE_AWAY
from .entity import MigoGatewayControlEntity, MigoGatewayEntity, MigoThermostatHomeControlEntity
from .helpers import generate_unique_id, get_devices_by_type, is_home_away

if TYPE_CHECKING:
    from . import MigoConfigEntry
    from .api import MigoApi
    from .coordinator import MigoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MigoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MiGO button entities."""
    data = entry.runtime_data
    coordinator = data.coordinator

    entities: list[ButtonEntity] = []

    # Create refresh button for each gateway
    for device_id in get_devices_by_type(coordinator, DEVICE_TYPE_GATEWAY):
        entities.append(
            MigoGatewayRefreshButton(
                coordinator=coordinator,
                device_id=device_id,
            )
        )

    # Create refresh button for each thermostat
    for device_id in get_devices_by_type(coordinator, DEVICE_TYPE_THERMOSTAT):
        device_data = coordinator.devices.get(device_id, {})
        home_id = device_data.get("home_id")
        if home_id:
            entities.append(
                MigoThermostatRefreshButton(
                    coordinator=coordinator,
                    home_id=home_id,
                    device_id=device_id,
                )
            )

    # Create reset heating curve button for each gateway
    for device_id in get_devices_by_type(coordinator, DEVICE_TYPE_GATEWAY):
        device_data = coordinator.devices.get(device_id, {})
        home_id = device_data.get("home_id")
        if home_id:
            entities.append(
                MigoResetHeatingCurveButton(
                    coordinator=coordinator,
                    home_id=home_id,
                    device_id=device_id,
                    api=data.api,
                )
            )

    # Create reset away-until button for each gateway
    for device_id in get_devices_by_type(coordinator, DEVICE_TYPE_GATEWAY):
        entities.append(
            MigoResetAwayUntilButton(
                coordinator=coordinator,
                device_id=device_id,
                api=data.api,
            )
        )

    async_add_entities(entities)


class MigoGatewayRefreshButton(MigoGatewayEntity, ButtonEntity):
    """MiGO Refresh button entity for Gateway device.

    No entity_category: kept in the primary "Controls" card - it's a quick
    action a user reaches for directly, not a background maintenance detail.
    """

    _attr_translation_key = "refresh"
    _attr_icon = "mdi:refresh"

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
    ) -> None:
        """Initialize the refresh button entity."""
        super().__init__(coordinator, device_id)
        self._attr_unique_id = generate_unique_id("refresh_gateway", device_id)

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.debug("Manual refresh requested from gateway %s", self._device_id)
        await self.coordinator.async_request_refresh()


class MigoThermostatRefreshButton(MigoThermostatHomeControlEntity, ButtonEntity):
    """MiGO Refresh button entity for Thermostat device.

    No entity_category - see MigoGatewayRefreshButton.
    """

    _attr_translation_key = "refresh"
    _attr_icon = "mdi:refresh"

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        home_id: str,
        device_id: str,
    ) -> None:
        """Initialize the refresh button entity."""
        # MigoThermostatHomeControlEntity needs home_id and api, but we don't need api for refresh
        super().__init__(coordinator, home_id, api=None)  # type: ignore[arg-type]
        self._device_id = device_id
        self._attr_unique_id = generate_unique_id("refresh_thermostat", device_id)

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.debug("Manual refresh requested from thermostat %s", self._device_id)
        await self.coordinator.async_request_refresh()


class MigoResetHeatingCurveButton(MigoThermostatHomeControlEntity, ButtonEntity):
    """MiGO Reset heating curve button entity.

    Stays Configuration (unlike the refresh buttons): it directly acts on
    the Heating curve setting, so it belongs grouped with it.
    """

    _attr_translation_key = "reset_heating_curve"
    _attr_icon = "mdi:chart-bell-curve"
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


class MigoResetAwayUntilButton(MigoGatewayControlEntity, ButtonEntity):
    """MiGO button to clear the Away return time.

    `datetime.py`'s `MigoAwayReturnDateTime` has no clear affordance of its
    own - Home Assistant's `datetime` platform requires a value, its
    more-info dialog cannot set one back to empty. This button is the only
    deliberate, discoverable way to reset it (toggling `switch.away_mode`
    also clears it as a side effect, but that's incidental to what the
    switch is for).

    `therm_mode_endtime` is confirmed to persist server-side (see
    `MigoAwayReturnDateTime`'s docstring), so a purely local clear is not
    enough while still Away: `native_value`'s API fallback would just read
    the same stale value back on the next refresh. If currently Away, this
    also calls `set_home_therm_mode` with `endtime=None` to clear it
    server-side too, staying Away with no return time; if not Away, there
    is nothing meaningful server-side to clear, so it only touches the
    local cache and pushes the change to the datetime entity directly via
    `coordinator.async_update_listeners()` rather than a pointless refresh.
    """

    _attr_translation_key = "reset_away_until"
    _attr_icon = "mdi:calendar-remove"

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
        api: MigoApi,
    ) -> None:
        """Initialize the reset away-until button entity."""
        super().__init__(coordinator, device_id, api)
        self._attr_unique_id = generate_unique_id("reset_away_until", device_id)

    async def async_press(self) -> None:
        """Handle the button press - clear the cached and, if relevant, server-side return time."""
        cache_key = f"away_until_{self._device_id}"
        home_id = self._device_data.get("home_id")

        # is_home_away() checks the switch's optimistic cache before falling
        # back to raw coordinator data, so this doesn't act on a stale Away
        # state right after the switch was just toggled (see helpers.is_home_away).
        if home_id and is_home_away(self.coordinator, self._device_id, self._device_data):
            _LOGGER.debug("Clearing away-until return time server-side for home %s", home_id)
            # Clear and push before the API call/refresh, not after: the
            # refresh's own listener push can otherwise fire while the cache
            # is still populated, briefly re-rendering the stale value.
            self.coordinator.clear_cached_value(cache_key)
            self.coordinator.async_update_listeners()
            await self._call_api_and_refresh(
                self._api.set_home_therm_mode,
                home_id=home_id,
                mode=MODE_AWAY,
                endtime=None,
            )
        else:
            _LOGGER.debug("Clearing away-until return time locally for device %s", self._device_id)
            self.coordinator.clear_cached_value(cache_key)
            self.coordinator.async_update_listeners()
