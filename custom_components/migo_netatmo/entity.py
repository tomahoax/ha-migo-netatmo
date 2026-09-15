"""Base entity classes for MiGO integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_TYPE_THERMOSTAT
from .entity_device_info import (
    build_gateway_device_info,
    build_home_fallback_device_info,
    build_thermostat_device_info,
)
from .entity_mixin import MigoApiControlMixin
from .helpers import get_gateway_mac_for_home, get_thermostat_for_room
from .models import HomeConfig, ModuleData, RoomData

if TYPE_CHECKING:
    from .api import MigoApi
    from .coordinator import MigoDataUpdateCoordinator


class MigoEntity(CoordinatorEntity["MigoDataUpdateCoordinator"]):
    """Base class for all MiGO entities."""

    _attr_has_entity_name = True

    # Connectivity diagnostics (the "reachable" binary sensor) set this to
    # True so they stay available while reporting the device as unreachable
    _ignore_reachable = False


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
    def _room_data(self) -> RoomData:
        """Get current room data."""
        return self.coordinator.rooms.get(self._room_id, {})

    @property
    @override
    def available(self) -> bool:
        """Return False when the room's thermostat is unreachable."""
        if not super().available:
            return False
        if self._ignore_reachable:
            return True
        return self._room_data.get("reachable") is not False

    @property
    @override
    def device_info(self) -> DeviceInfo:
        """Return device info for the Thermostat device."""
        home_id = self._room_data.get("home_id", "")

        if thermostat_id := get_thermostat_for_room(self.coordinator, self._room_id):
            return build_thermostat_device_info(self.coordinator, thermostat_id, home_id)

        # Fallback: use gateway device if no thermostat found
        if gateway_mac := get_gateway_mac_for_home(self.coordinator, home_id):
            return build_gateway_device_info(self.coordinator, gateway_mac, home_id)

        return build_home_fallback_device_info(self.coordinator, home_id)


class MigoDeviceEntity(MigoEntity):
    """Base class for MiGO device-based entities (gateway/thermostat sensors, switch)."""

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
    ) -> None:
        """Initialize the device entity."""
        super().__init__(coordinator)
        self._device_id = device_id

    @property
    def _device_data(self) -> ModuleData:
        """Get current device data."""
        return self.coordinator.devices.get(self._device_id, {})

    @property
    def _home_id(self) -> str:
        """Get the home ID this device belongs to."""
        return self._device_data.get("home_id", "")

    @property
    @override
    def available(self) -> bool:
        """Return False when the device reports itself unreachable."""
        if not super().available:
            return False
        if self._ignore_reachable:
            return True
        return self._device_data.get("reachable") is not False


class MigoGatewayEntity(MigoDeviceEntity):
    """Base class for MiGO gateway/boiler entities (NAVaillant).

    Gateway entities are associated with the physical gateway device
    and include sensors like WiFi strength, outdoor temperature, boiler errors.
    """

    @property
    @override
    def device_info(self) -> DeviceInfo:
        """Return device info for the gateway."""
        return build_gateway_device_info(self.coordinator, self._device_id, self._home_id)


class MigoThermostatEntity(MigoDeviceEntity):
    """Base class for MiGO thermostat entities (NAThermVaillant).

    Thermostat entities are associated with the physical thermostat device
    and include sensors like battery, RF strength, temperature offset.
    The thermostat is connected via the gateway (via_device - see
    entity_device_info.build_thermostat_device_info's docstring for why
    not via_device_id).
    """

    @property
    @override
    def device_info(self) -> DeviceInfo:
        """Return device info for the thermostat."""
        return build_thermostat_device_info(self.coordinator, self._device_id, self._home_id)


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
    def _home_data(self) -> HomeConfig:
        """Get current home data."""
        return self.coordinator.homes.get(self._home_id, {})

    @property
    @override
    def device_info(self) -> DeviceInfo:
        """Return device info for the Gateway device."""
        if gateway_mac := get_gateway_mac_for_home(self.coordinator, self._home_id):
            return build_gateway_device_info(self.coordinator, gateway_mac, self._home_id)

        return build_home_fallback_device_info(self.coordinator, self._home_id)


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


class MigoThermostatHomeEntity(MigoEntity):
    """Base class for home-level entities assigned to the Thermostat device.

    Used for settings like anticipation, manual setpoint duration, hysteresis
    that are conceptually home/thermostat settings but should appear on the
    Thermostat device in Home Assistant.
    """

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        home_id: str,
    ) -> None:
        """Initialize the thermostat home entity."""
        super().__init__(coordinator)
        self._home_id = home_id

    @property
    def _home_data(self) -> HomeConfig:
        """Get current home data."""
        return self.coordinator.homes.get(self._home_id, {})

    @property
    @override
    def device_info(self) -> DeviceInfo:
        """Return device info for the Thermostat device."""
        # Find the thermostat for this home
        for device_id, device_data in self.coordinator.devices.items():
            if device_data.get("type") == DEVICE_TYPE_THERMOSTAT and device_data.get("home_id") == self._home_id:
                return build_thermostat_device_info(self.coordinator, device_id, self._home_id)

        # Fallback to gateway if no thermostat found
        if gateway_mac := get_gateway_mac_for_home(self.coordinator, self._home_id):
            return build_gateway_device_info(self.coordinator, gateway_mac, self._home_id)

        return build_home_fallback_device_info(self.coordinator, self._home_id)


class MigoThermostatHomeControlEntity(MigoThermostatHomeEntity, MigoApiControlMixin):
    """Home-level entity on the Thermostat device, with API control."""

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        home_id: str,
        api: MigoApi,
    ) -> None:
        """Initialize the thermostat home control entity."""
        super().__init__(coordinator, home_id)
        self._api = api


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
