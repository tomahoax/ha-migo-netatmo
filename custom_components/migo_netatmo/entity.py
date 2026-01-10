"""Base entity classes for MiGO integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL_NAME
from .helpers import get_gateway_mac_for_home

if TYPE_CHECKING:
    from .api import MigoApi
    from .coordinator import MigoDataUpdateCoordinator


class MigoApiControlMixin:
    """Mixin providing API control functionality.

    This mixin provides common functionality for entities that need to
    call API methods and refresh the coordinator after changes.
    """

    _api: MigoApi
    coordinator: MigoDataUpdateCoordinator

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


class MigoEntity(CoordinatorEntity["MigoDataUpdateCoordinator"]):
    """Base class for all MiGO entities."""

    _attr_has_entity_name = True

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()


class MigoRoomEntity(MigoEntity):
    """Base class for MiGO room-based entities (climate, room sensors)."""

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
        """Return device info."""
        home_id = self._room_data.get("home_id", "")
        home_name = self._room_data.get("home_name", "MiGO Home")

        info = DeviceInfo(
            identifiers={(DOMAIN, home_id)},
            name=home_name,
            manufacturer=MANUFACTURER,
            model=MODEL_NAME,
        )

        # Add gateway MAC address as connection
        if gateway_mac := get_gateway_mac_for_home(self.coordinator, home_id):
            info["connections"] = {(CONNECTION_NETWORK_MAC, gateway_mac)}

        return info


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
    def _device_data(self) -> dict[str, Any]:
        """Get current device data."""
        return self.coordinator.devices.get(self._device_id, {})

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info with diagnostic information."""
        home_id = self._device_data.get("home_id", "")
        home_data = self.coordinator.homes.get(home_id, {})
        home_name = home_data.get("name", "MiGO Home")

        # Build device info with optional diagnostic fields
        info = DeviceInfo(
            identifiers={(DOMAIN, home_id)},
            name=home_name,
            manufacturer=MANUFACTURER,
            model=MODEL_NAME,
        )

        # Add gateway MAC address as connection
        if gateway_mac := get_gateway_mac_for_home(self.coordinator, home_id):
            info["connections"] = {(CONNECTION_NETWORK_MAC, gateway_mac)}

        # Add diagnostic information if available
        if firmware := self._device_data.get("firmware_revision"):
            info["sw_version"] = str(firmware)
        if hw_version := self._device_data.get("hardware_version"):
            info["hw_version"] = str(hw_version)
        if serial := self._device_data.get("oem_serial"):
            info["serial_number"] = serial

        return info


class MigoHomeEntity(MigoEntity):
    """Base class for MiGO home-based entities (selects for mode/schedule)."""

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
        """Return device info."""
        home_name = self._home_data.get("name", "MiGO Home")

        info = DeviceInfo(
            identifiers={(DOMAIN, self._home_id)},
            name=home_name,
            manufacturer=MANUFACTURER,
            model=MODEL_NAME,
        )

        # Add gateway MAC address as connection
        if gateway_mac := get_gateway_mac_for_home(self.coordinator, self._home_id):
            info["connections"] = {(CONNECTION_NETWORK_MAC, gateway_mac)}

        return info


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
