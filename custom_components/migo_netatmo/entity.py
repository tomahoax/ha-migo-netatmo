"""Base entity classes for MiGO integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import MigoApiError, MigoAuthError, MigoConnectionError
from .const import DEVICE_TYPE_GATEWAY, DEVICE_TYPE_THERMOSTAT, DOMAIN, MANUFACTURER
from .helpers import get_gateway_mac_for_home, get_thermostat_for_room

if TYPE_CHECKING:
    from .api import MigoApi
    from .coordinator import MigoDataUpdateCoordinator


def _home_name(coordinator: MigoDataUpdateCoordinator, home_id: str) -> str:
    """Return the display name of a home."""
    return coordinator.homes.get(home_id, {}).get("name", "MiGO")


def build_gateway_device_info(
    coordinator: MigoDataUpdateCoordinator,
    gateway_id: str,
    home_id: str,
) -> DeviceInfo:
    """Build the DeviceInfo for a gateway (NAVaillant) device.

    Single source of truth: every entity attached to the gateway device
    must produce exactly this structure.
    """
    device_data = coordinator.devices.get(gateway_id, {})
    info = DeviceInfo(
        identifiers={(DOMAIN, gateway_id)},
        name=f"{_home_name(coordinator, home_id)} Gateway",
        manufacturer=MANUFACTURER,
        model=DEVICE_TYPE_GATEWAY,
        connections={(CONNECTION_NETWORK_MAC, gateway_id)},
    )
    if firmware := device_data.get("firmware_revision"):
        info["sw_version"] = str(firmware)
    if hw_version := device_data.get("hardware_version"):
        info["hw_version"] = str(hw_version)
    if serial := device_data.get("oem_serial"):
        info["serial_number"] = serial
    return info


def build_thermostat_device_info(
    coordinator: MigoDataUpdateCoordinator,
    thermostat_id: str,
    home_id: str,
) -> DeviceInfo:
    """Build the DeviceInfo for a thermostat (NAThermVaillant) device.

    Single source of truth: every entity attached to the thermostat
    device must produce exactly this structure.
    """
    device_data = coordinator.devices.get(thermostat_id, {})
    info = DeviceInfo(
        identifiers={(DOMAIN, thermostat_id)},
        name=f"{_home_name(coordinator, home_id)} Thermostat",
        manufacturer=MANUFACTURER,
        model=DEVICE_TYPE_THERMOSTAT,
    )

    # Add MAC address connection if the device_id looks like a MAC address
    if ":" in thermostat_id and len(thermostat_id) == 17:
        info["connections"] = {(CONNECTION_NETWORK_MAC, thermostat_id)}

    # Link to the parent gateway device.
    # via_device is deprecated for HA 2026.8 (via_device_id, compat until
    # 2027.8); migrating requires a device registry lookup and is planned
    # for a later release.
    if gateway_id := device_data.get("bridge"):
        info["via_device"] = (DOMAIN, gateway_id)

    if firmware := device_data.get("firmware_revision"):
        info["sw_version"] = str(firmware)
    return info


def build_home_fallback_device_info(
    coordinator: MigoDataUpdateCoordinator,
    home_id: str,
) -> DeviceInfo:
    """Build the last-resort DeviceInfo when no physical device is known."""
    return DeviceInfo(
        identifiers={(DOMAIN, home_id)},
        name=_home_name(coordinator, home_id),
        manufacturer=MANUFACTURER,
    )


class MigoApiControlMixin:
    """Mixin providing API control functionality.

    This mixin provides common functionality for entities that need to
    call API methods and refresh the coordinator after changes.
    """

    _api: MigoApi
    coordinator: MigoDataUpdateCoordinator

    async def _call_api(
        self,
        api_method: Callable[..., Awaitable[Any]],
        **kwargs: Any,
    ) -> Any:
        """Call an API method, translating failures into UI-visible errors.

        Args:
            api_method: The async API method to call.
            **kwargs: Arguments to pass to the API method.

        Raises:
            HomeAssistantError: On any API failure, with a translated message.
        """
        try:
            return await api_method(**kwargs)
        except MigoAuthError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="auth_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        except MigoConnectionError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"error": str(err)},
            ) from err
        except MigoApiError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="api_error",
                translation_placeholders={"error": str(err)},
            ) from err

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
        await self._call_api(api_method, **kwargs)
        await self.coordinator.async_request_refresh()


class MigoEntity(CoordinatorEntity["MigoDataUpdateCoordinator"]):
    """Base class for all MiGO entities."""

    _attr_has_entity_name = True


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
    def _device_data(self) -> dict[str, Any]:
        """Get current device data."""
        return self.coordinator.devices.get(self._device_id, {})

    @property
    def _home_id(self) -> str:
        """Get the home ID this device belongs to."""
        return self._device_data.get("home_id", "")


class MigoGatewayEntity(MigoDeviceEntity):
    """Base class for MiGO gateway/boiler entities (NAVaillant).

    Gateway entities are associated with the physical gateway device
    and include sensors like WiFi strength, outdoor temperature, boiler errors.
    """

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the gateway."""
        return build_gateway_device_info(self.coordinator, self._device_id, self._home_id)


class MigoThermostatEntity(MigoDeviceEntity):
    """Base class for MiGO thermostat entities (NAThermVaillant).

    Thermostat entities are associated with the physical thermostat device
    and include sensors like battery, RF strength, temperature offset.
    The thermostat is connected via the gateway (via_device).
    """

    @property
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
    def _home_data(self) -> dict[str, Any]:
        """Get current home data."""
        return self.coordinator.homes.get(self._home_id, {})

    @property
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
    def _home_data(self) -> dict[str, Any]:
        """Get current home data."""
        return self.coordinator.homes.get(self._home_id, {})

    @property
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
