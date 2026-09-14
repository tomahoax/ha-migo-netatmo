"""Base entity classes for MiGO integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_TYPE_GATEWAY, DEVICE_TYPE_THERMOSTAT, DOMAIN, MANUFACTURER
from .helpers import get_gateway_mac_for_home, get_thermostat_for_room

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .api import MigoApi
    from .coordinator import MigoDataUpdateCoordinator


def _resolve_via_device_id(
    hass: HomeAssistant | None,
    config_entry_id: str | None,
    gateway_id: str,
) -> str | None:
    """Resolve a gateway's registry-internal device_id, for `via_device_id`.

    `via_device_id` (the replacement for the deprecated `via_device`
    identifiers-tuple form) needs the device registry's own internal ID, not
    the `(DOMAIN, identifier)` tuple used everywhere else in this
    integration - this looks it up by the same identifier the gateway's own
    `DeviceInfo` registers under (`identifiers={(DOMAIN, gateway_id)}`, see
    `MigoGatewayEntity.device_info`), scoped to this entity's own config
    entry via `async_get_device_by_identifier` - `async_get_device` is
    itself deprecated (identifiers are no longer guaranteed unique across
    config entries) and, like `via_device` before it, only warns *unless*
    Home Assistant happens to attribute the call to a core integration
    instead of this custom one, in which case it raises - the exact
    mechanism that broke entity setup live once already (see the CHANGELOG
    entry this helper was introduced for). Returns None if `hass` or
    `config_entry_id` isn't set yet (an entity's `device_info` can in
    principle be read before it's fully added to a platform) or the gateway
    device hasn't been registered yet - in either case, the caller should
    just omit `via_device_id` rather than raise, since a device with no
    parent is still a valid device.
    """
    if hass is None or config_entry_id is None:
        return None
    device = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, gateway_id), config_entry_id)
    return device.id if device else None


def _entity_config_entry_id(entity: object) -> str | None:
    """Return the config entry ID an entity was added under, if it has one yet.

    `Entity.platform` is set (alongside `Entity.hass`) by
    `add_to_platform_start`, before `device_info` is ever read - see
    `entity_platform.py`'s `_async_add_entity`. Guarded defensively anyway,
    since nothing stops `device_info` being read earlier in principle (as
    every device_info test in this file does, none of which set `hass` or
    `platform` at all).
    """
    platform = getattr(entity, "platform", None)
    config_entry = getattr(platform, "config_entry", None) if platform is not None else None
    return config_entry.entry_id if config_entry is not None else None


class MigoApiControlMixin:
    """Mixin providing API control functionality.

    This mixin provides common functionality for entities that need to
    call API methods and refresh the coordinator after changes.
    """

    _api: MigoApi
    coordinator: MigoDataUpdateCoordinator

    if TYPE_CHECKING:
        # Provided by the Entity base class this mixin is always combined
        # with (see MigoGatewayControlEntity etc.) - declared here only so
        # the methods below type-check.
        def async_write_ha_state(self) -> None: ...

    async def _call_api_and_refresh(
        self,
        api_method: Callable[..., Awaitable[Any]],
        **kwargs: Any,
    ) -> None:
        """Call an API method and refresh the coordinator.

        Args:
            api_method: The async API method to call.
            **kwargs: Arguments to pass to the API method.
        """
        await api_method(**kwargs)
        await self.coordinator.async_request_refresh()

    async def _call_api_optimistically(
        self,
        api_method: Callable[..., Awaitable[Any]],
        *,
        cache_key: str,
        optimistic_value: Any,
        on_optimistic: Callable[[], None] | None = None,
        **kwargs: Any,
    ) -> None:
        """Call an API method with immediate optimistic UI feedback.

        Unlike `_call_api_and_refresh`, this writes `optimistic_value` to the
        coordinator's cache and to entity state *before* the API call, so the
        UI reacts immediately instead of waiting for the coordinator's next
        refresh cycle. On success, it requests a refresh and then clears the
        cache entry so API data regains authority - the cache key is not left
        behind to shadow future API values. On failure, the previous cached
        value (or its absence) is restored before the exception propagates.

        `on_optimistic`, if given, runs synchronously right after this
        entity's own optimistic cache/state write, before the API call - the
        one moment where a *different* entity's cache-aware read (e.g.
        `helpers.is_home_away()`) is guaranteed to see this entity's fresh
        optimistic value without also risking a read of stale coordinator
        data. Used by `MigoAwayModeSwitch` to clear and push
        `MigoAwayReturnDateTime`'s value in the same instant, rather than
        only when this entity's own state is written. Not restored on
        failure along with `cache_key` - a rare API failure just leaves the
        dependent entity blank a little longer than strictly necessary,
        until the next real refresh, rather than needing its own rollback.

        Deliberately does *not* write state again right after clearing the
        cache. `async_request_refresh()` goes through the coordinator's
        refresh debouncer (10s cooldown, `immediate=True`): the very first
        call in a while runs the fetch synchronously and pushes state via
        its own `async_update_listeners()` while the cache is still
        populated (showing the optimistic value, correctly) - but any call
        within 10s of a previous refresh (routine background polling, or
        just toggling more than one control in a row) is coalesced and
        returns immediately *without* having fetched anything yet. A write
        here would then render the just-cleared cache against still-stale
        coordinator data, i.e. the UI would revert to the old value and
        only jump back to the new one once the coalesced refresh actually
        completes a few seconds later - a real, reported regression from
        this line's own earlier addition, not a hypothetical. Leaving the
        optimistic value on screen (it already matches what was just
        requested, in the overwhelmingly common case) until the coordinator's
        own next real update is the better trade-off.

        Args:
            api_method: The async API method to call.
            cache_key: The coordinator optimistic-cache key for this entity.
            optimistic_value: The value to show immediately while the call is
                in flight.
            on_optimistic: Optional callback run right after the optimistic
                write above, before the API call.
            **kwargs: Arguments to pass to the API method.
        """
        previous = self.coordinator.get_cached_value(cache_key)
        self.coordinator.set_cached_value(cache_key, optimistic_value)
        self.async_write_ha_state()
        if on_optimistic is not None:
            on_optimistic()

        try:
            await api_method(**kwargs)
        except Exception:
            if previous is None:
                self.coordinator.clear_cached_value(cache_key)
            else:
                self.coordinator.set_cached_value(cache_key, previous)
            self.async_write_ha_state()
            raise

        await self.coordinator.async_request_refresh()
        self.coordinator.clear_cached_value(cache_key)


class MigoEntity(CoordinatorEntity["MigoDataUpdateCoordinator"]):
    """Base class for all MiGO entities."""

    _attr_has_entity_name = True

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()


class MigoRoomEntity(MigoEntity):
    """Base class for MiGO room-based entities (climate, room sensors).

    Room entities are associated with the Thermostat device (NAThermVaillant),
    since the thermostat is the physical device that measures room conditions.
    """

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        room_id: str,
    ) -> None:
        """Initialize the room entity."""
        super().__init__(coordinator)
        self._room_id = room_id

    @property
    def _room_data(self) -> dict[str, Any]:
        """Get current room data."""
        return self.coordinator.rooms.get(self._room_id, {})

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the Thermostat device."""
        home_id = self._room_data.get("home_id", "")
        home_data = self.coordinator.homes.get(home_id, {})
        home_name = home_data.get("name", "MiGO")

        # Find the thermostat ID for this room
        thermostat_id = get_thermostat_for_room(self.coordinator, self._room_id)
        if thermostat_id:
            # Get the thermostat device data from coordinator
            thermostat_data = self.coordinator.devices.get(thermostat_id, {})
            gateway_id = thermostat_data.get("bridge")

            info = DeviceInfo(
                identifiers={(DOMAIN, thermostat_id)},
                name=f"{home_name} Thermostat",
                manufacturer=MANUFACTURER,
                model=DEVICE_TYPE_THERMOSTAT,
            )

            # Link to parent gateway device
            config_entry_id = _entity_config_entry_id(self)
            if gateway_id and (via_device_id := _resolve_via_device_id(self.hass, config_entry_id, gateway_id)):
                info["via_device_id"] = via_device_id

            # Add diagnostic information if available
            if firmware := thermostat_data.get("firmware_revision"):
                info["sw_version"] = str(firmware)

            return info

        # Fallback: use gateway device if no thermostat found
        if gateway_mac := get_gateway_mac_for_home(self.coordinator, home_id):
            return DeviceInfo(
                identifiers={(DOMAIN, gateway_mac)},
                name=f"{home_name} Gateway",
                manufacturer=MANUFACTURER,
                model=DEVICE_TYPE_GATEWAY,
                connections={(CONNECTION_NETWORK_MAC, gateway_mac)},
            )

        # Last resort fallback
        return DeviceInfo(
            identifiers={(DOMAIN, home_id)},
            name=home_name,
            manufacturer=MANUFACTURER,
        )


class MigoDeviceEntity(MigoEntity):
    """Base class for MiGO device-based entities (gateway/thermostat sensors, switch).

    This base class uses the device_id as identifier. Subclasses (MigoGatewayEntity,
    MigoThermostatEntity) override device_info for device-specific information.
    """

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
    ) -> None:
        """Initialize the device entity."""
        super().__init__(coordinator)
        self._device_id = device_id

    @property
    def _device_data(self) -> dict[str, Any]:
        """Get current device data."""
        return self.coordinator.devices.get(self._device_id, {})

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info with diagnostic information.

        Note: Subclasses should override this for device-specific info.
        """
        home_id = self._device_data.get("home_id", "")
        home_data = self.coordinator.homes.get(home_id, {})
        home_name = home_data.get("name", "MiGO")

        # Build device info using device_id as identifier
        info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=f"{home_name} Device",
            manufacturer=MANUFACTURER,
        )

        # Add diagnostic information if available
        if firmware := self._device_data.get("firmware_revision"):
            info["sw_version"] = str(firmware)
        if hw_version := self._device_data.get("hardware_version"):
            info["hw_version"] = str(hw_version)
        if serial := self._device_data.get("oem_serial"):
            info["serial_number"] = serial

        return info


class MigoGatewayEntity(MigoDeviceEntity):
    """Base class for MiGO gateway/boiler entities (NAVaillant).

    Gateway entities are associated with the physical gateway device
    and include sensors like WiFi strength, outdoor temperature, boiler errors.
    """

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the gateway."""
        home_id = self._device_data.get("home_id", "")
        home_data = self.coordinator.homes.get(home_id, {})
        home_name = home_data.get("name", "MiGO")

        info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=f"{home_name} Gateway",
            manufacturer=MANUFACTURER,
            model=DEVICE_TYPE_GATEWAY,
            connections={(CONNECTION_NETWORK_MAC, self._device_id)},
        )

        # Add diagnostic information if available
        if firmware := self._device_data.get("firmware_revision"):
            info["sw_version"] = str(firmware)
        if hw_version := self._device_data.get("hardware_version"):
            info["hw_version"] = str(hw_version)
        if serial := self._device_data.get("oem_serial"):
            info["serial_number"] = serial

        return info


class MigoThermostatEntity(MigoDeviceEntity):
    """Base class for MiGO thermostat entities (NAThermVaillant).

    Thermostat entities are associated with the physical thermostat device
    and include sensors like battery, RF strength, temperature offset.
    The thermostat is connected via the gateway (via_device_id).
    """

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the thermostat."""
        home_id = self._device_data.get("home_id", "")
        home_data = self.coordinator.homes.get(home_id, {})
        home_name = home_data.get("name", "MiGO")

        # Get the gateway ID (bridge) for via_device_id
        gateway_id = self._device_data.get("bridge")

        info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=f"{home_name} Thermostat",
            manufacturer=MANUFACTURER,
            model=DEVICE_TYPE_THERMOSTAT,
        )

        # Add MAC address connection if device_id looks like a MAC address
        if ":" in self._device_id and len(self._device_id) == 17:
            info["connections"] = {(CONNECTION_NETWORK_MAC, self._device_id)}

        # Link to parent gateway device
        config_entry_id = _entity_config_entry_id(self)
        if gateway_id and (via_device_id := _resolve_via_device_id(self.hass, config_entry_id, gateway_id)):
            info["via_device_id"] = via_device_id

        # Add diagnostic information if available
        if firmware := self._device_data.get("firmware_revision"):
            info["sw_version"] = str(firmware)

        return info


class MigoGatewayControlEntity(MigoGatewayEntity, MigoApiControlMixin):
    """Base class for gateway entities that control the device via API.

    Used for controls like DHW temperature, DHW boost, hysteresis.
    """

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
        api: MigoApi,
    ) -> None:
        """Initialize the gateway control entity."""
        super().__init__(coordinator, device_id)
        self._api = api


class MigoThermostatControlEntity(MigoThermostatEntity, MigoApiControlMixin):
    """Base class for thermostat entities that control the device via API.

    Used for controls like temperature offset, manual setpoint duration, anticipation.
    """

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
        api: MigoApi,
    ) -> None:
        """Initialize the thermostat control entity."""
        super().__init__(coordinator, device_id)
        self._api = api


class MigoHomeEntity(MigoEntity):
    """Base class for MiGO home-based entities (selects for mode/schedule).

    Home entities are associated with the Gateway device (NAVaillant),
    since the gateway is the central hub that controls home-level settings.
    """

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        home_id: str,
    ) -> None:
        """Initialize the home entity."""
        super().__init__(coordinator)
        self._home_id = home_id

    @property
    def _home_data(self) -> dict[str, Any]:
        """Get current home data."""
        return self.coordinator.homes.get(self._home_id, {})

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the Gateway device."""
        home_name = self._home_data.get("name", "MiGO")

        # Use gateway as the device for home-level entities
        if gateway_mac := get_gateway_mac_for_home(self.coordinator, self._home_id):
            # Get gateway device data for additional info
            gateway_data = self.coordinator.devices.get(gateway_mac, {})

            info = DeviceInfo(
                identifiers={(DOMAIN, gateway_mac)},
                name=f"{home_name} Gateway",
                manufacturer=MANUFACTURER,
                model=DEVICE_TYPE_GATEWAY,
                connections={(CONNECTION_NETWORK_MAC, gateway_mac)},
            )

            # Add diagnostic information if available
            if firmware := gateway_data.get("firmware_revision"):
                info["sw_version"] = str(firmware)
            if hw_version := gateway_data.get("hardware_version"):
                info["hw_version"] = str(hw_version)
            if serial := gateway_data.get("oem_serial"):
                info["serial_number"] = serial

            return info

        # Fallback if no gateway found
        return DeviceInfo(
            identifiers={(DOMAIN, self._home_id)},
            name=home_name,
            manufacturer=MANUFACTURER,
        )


class MigoControlEntity(MigoDeviceEntity, MigoApiControlMixin):
    """Base class for entities that control the device via API.

    This class provides common functionality for entities that need to
    call API methods and refresh the coordinator after changes.
    """

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
        api: MigoApi,
    ) -> None:
        """Initialize the control entity.

        Args:
            coordinator: The data update coordinator.
            device_id: The device ID this entity controls.
            api: The API client for making control calls.
        """
        super().__init__(coordinator, device_id)
        self._api = api


class MigoHomeControlEntity(MigoHomeEntity, MigoApiControlMixin):
    """Base class for home-based entities that control the device via API."""

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        home_id: str,
        api: MigoApi,
    ) -> None:
        """Initialize the home control entity.

        Args:
            coordinator: The data update coordinator.
            home_id: The home ID this entity controls.
            api: The API client for making control calls.
        """
        super().__init__(coordinator, home_id)
        self._api = api


class MigoThermostatHomeControlEntity(MigoEntity, MigoApiControlMixin):
    """Base class for home-level entities assigned to the Thermostat device.

    Used for settings like anticipation, manual setpoint duration, hysteresis
    that are conceptually home/thermostat settings but should appear on the
    Thermostat device in Home Assistant.
    """

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        home_id: str,
        api: MigoApi,
    ) -> None:
        """Initialize the thermostat home control entity."""
        super().__init__(coordinator)
        self._home_id = home_id
        self._api = api

    @property
    def _home_data(self) -> dict[str, Any]:
        """Get current home data."""
        return self.coordinator.homes.get(self._home_id, {})

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the Thermostat device."""
        home_name = self._home_data.get("name", "MiGO")

        # Find the thermostat for this home
        for device_id, device_data in self.coordinator.devices.items():
            if device_data.get("type") == DEVICE_TYPE_THERMOSTAT and device_data.get("home_id") == self._home_id:
                gateway_id = device_data.get("bridge")

                info = DeviceInfo(
                    identifiers={(DOMAIN, device_id)},
                    name=f"{home_name} Thermostat",
                    manufacturer=MANUFACTURER,
                    model=DEVICE_TYPE_THERMOSTAT,
                )

                # Add MAC address connection if device_id looks like a MAC address
                if ":" in device_id and len(device_id) == 17:
                    info["connections"] = {(CONNECTION_NETWORK_MAC, device_id)}

                config_entry_id = _entity_config_entry_id(self)
                if gateway_id and (via_device_id := _resolve_via_device_id(self.hass, config_entry_id, gateway_id)):
                    info["via_device_id"] = via_device_id

                if firmware := device_data.get("firmware_revision"):
                    info["sw_version"] = str(firmware)

                return info

        # Fallback to gateway if no thermostat found
        if gateway_mac := get_gateway_mac_for_home(self.coordinator, self._home_id):
            return DeviceInfo(
                identifiers={(DOMAIN, gateway_mac)},
                name=f"{home_name} Gateway",
                manufacturer=MANUFACTURER,
                model=DEVICE_TYPE_GATEWAY,
            )

        return DeviceInfo(
            identifiers={(DOMAIN, self._home_id)},
            name=home_name,
            manufacturer=MANUFACTURER,
        )


class MigoRoomControlEntity(MigoRoomEntity, MigoApiControlMixin):
    """Base class for room-based entities that control the device via API.

    This is used by climate entities that need both room data access
    and API control capabilities.
    """

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        room_id: str,
        api: MigoApi,
    ) -> None:
        """Initialize the room control entity.

        Args:
            coordinator: The data update coordinator.
            room_id: The room ID this entity controls.
            api: The API client for making control calls.
        """
        super().__init__(coordinator, room_id)
        self._api = api
