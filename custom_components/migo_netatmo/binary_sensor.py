"""Binary sensor platform for MiGO integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEVICE_TYPE_GATEWAY, DEVICE_TYPE_THERMOSTAT
from .entity import MigoGatewayEntity, MigoRoomEntity, MigoThermostatEntity
from .helpers import generate_unique_id, get_devices_by_type

if TYPE_CHECKING:
    from . import MigoConfigEntry
    from .coordinator import MigoDataUpdateCoordinator

# Coordinator-driven read-only platform
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class MigoBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a MiGO binary sensor entity.

    The key field is cosmetic; unique_id_key feeds generate_unique_id and
    must never change (users would lose recorder history).
    """

    data_key: str
    unique_id_key: str
    value_fn: Callable[[Any], bool | None] | None = None


# Room-based binary sensor configurations
ROOM_BINARY_SENSORS: tuple[MigoBinarySensorEntityDescription, ...] = ()

# Gateway binary sensor configurations
GATEWAY_BINARY_SENSORS: tuple[MigoBinarySensorEntityDescription, ...] = (
    MigoBinarySensorEntityDescription(
        key="ebus_error",
        data_key="ebus_error",
        unique_id_key="ebus_error",
        translation_key="ebus_error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    MigoBinarySensorEntityDescription(
        key="boiler_error",
        data_key="boiler_error",
        unique_id_key="boiler_error",
        translation_key="boiler_error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda v: bool(v) if v is not None else None,
    ),
)

# Thermostat binary sensor configurations
THERMOSTAT_BINARY_SENSORS: tuple[MigoBinarySensorEntityDescription, ...] = (
    MigoBinarySensorEntityDescription(
        key="boiler_status",
        data_key="boiler_status",
        unique_id_key="boiler_status",
        translation_key="boiler_status",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    MigoBinarySensorEntityDescription(
        key="reachable",
        data_key="reachable",
        unique_id_key="reachable",
        translation_key="reachable",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MigoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MiGO binary sensor entities."""
    coordinator = entry.runtime_data.coordinator

    entities: list[BinarySensorEntity] = []

    # Room-based binary sensors
    for room_id in coordinator.rooms:
        for description in ROOM_BINARY_SENSORS:
            entities.append(
                MigoRoomBinarySensor(
                    coordinator=coordinator,
                    room_id=room_id,
                    description=description,
                )
            )

    # Gateway binary sensors
    for device_id in get_devices_by_type(coordinator, DEVICE_TYPE_GATEWAY):
        for description in GATEWAY_BINARY_SENSORS:
            entities.append(
                MigoGatewayBinarySensor(
                    coordinator=coordinator,
                    device_id=device_id,
                    description=description,
                )
            )

    # Thermostat binary sensors
    for device_id in get_devices_by_type(coordinator, DEVICE_TYPE_THERMOSTAT):
        for description in THERMOSTAT_BINARY_SENSORS:
            entities.append(
                MigoThermostatBinarySensor(
                    coordinator=coordinator,
                    device_id=device_id,
                    description=description,
                )
            )

    async_add_entities(entities)


class MigoRoomBinarySensor(MigoRoomEntity, BinarySensorEntity):
    """MiGO room-based binary sensor described by an entity description."""

    entity_description: MigoBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        room_id: str,
        description: MigoBinarySensorEntityDescription,
    ) -> None:
        """Initialize the room binary sensor."""
        super().__init__(coordinator, room_id)
        self.entity_description = description
        self._attr_unique_id = generate_unique_id(description.unique_id_key, room_id)

    @property
    def is_on(self) -> bool | None:
        """Return True if the sensor is on."""
        value = self._room_data.get(self.entity_description.data_key)
        if self.entity_description.value_fn:
            return self.entity_description.value_fn(value)
        return value


class _MigoDeviceBinarySensorMixin(BinarySensorEntity):
    """Mixin for device-based binary sensors with common functionality."""

    entity_description: MigoBinarySensorEntityDescription
    _device_data: dict[str, Any]

    def _init_binary_sensor(self, device_id: str, description: MigoBinarySensorEntityDescription) -> None:
        """Initialize binary sensor attributes from the entity description."""
        self.entity_description = description
        self._attr_unique_id = generate_unique_id(description.unique_id_key, device_id)

    @property
    def is_on(self) -> bool | None:
        """Return True if the sensor is on."""
        value = self._device_data.get(self.entity_description.data_key)
        if self.entity_description.value_fn:
            return self.entity_description.value_fn(value)
        return value


class MigoGatewayBinarySensor(MigoGatewayEntity, _MigoDeviceBinarySensorMixin):
    """MiGO gateway binary sensor entity."""

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
        description: MigoBinarySensorEntityDescription,
    ) -> None:
        """Initialize the gateway binary sensor."""
        super().__init__(coordinator, device_id)
        self._init_binary_sensor(device_id, description)


class MigoThermostatBinarySensor(MigoThermostatEntity, _MigoDeviceBinarySensorMixin):
    """MiGO thermostat binary sensor entity."""

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
        description: MigoBinarySensorEntityDescription,
    ) -> None:
        """Initialize the thermostat binary sensor."""
        super().__init__(coordinator, device_id)
        self._init_binary_sensor(device_id, description)
