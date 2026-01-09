"""Binary sensor platform for MiGO integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEVICE_TYPE_GATEWAY, DEVICE_TYPE_THERMOSTAT
from .entity import MigoDeviceEntity, MigoRoomEntity
from .helpers import generate_unique_id, get_devices_by_type

if TYPE_CHECKING:
    from . import MigoConfigEntry
    from .coordinator import MigoDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class BinarySensorConfig:
    """Configuration for a binary sensor entity."""

    data_key: str
    unique_id_key: str
    translation_key: str
    device_class: BinarySensorDeviceClass | None = None
    entity_category: EntityCategory | None = None
    value_fn: Callable[[Any], bool | None] | None = None


# Room-based binary sensor configurations
ROOM_BINARY_SENSORS: tuple[BinarySensorConfig, ...] = (
    BinarySensorConfig(
        data_key="anticipating",
        unique_id_key="anticipating",
        translation_key="anticipating",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
)

# Gateway binary sensor configurations
GATEWAY_BINARY_SENSORS: tuple[BinarySensorConfig, ...] = (
    BinarySensorConfig(
        data_key="ebus_error",
        unique_id_key="ebus_error",
        translation_key="ebus_error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorConfig(
        data_key="boiler_error",
        unique_id_key="boiler_error",
        translation_key="boiler_error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda v: bool(v) if v is not None else None,
    ),
)

# Thermostat binary sensor configurations
THERMOSTAT_BINARY_SENSORS: tuple[BinarySensorConfig, ...] = (
    BinarySensorConfig(
        data_key="boiler_status",
        unique_id_key="boiler_status",
        translation_key="boiler_status",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    BinarySensorConfig(
        data_key="reachable",
        unique_id_key="reachable",
        translation_key="reachable",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
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
        for config in ROOM_BINARY_SENSORS:
            entities.append(
                MigoRoomBinarySensor(
                    coordinator=coordinator,
                    room_id=room_id,
                    config=config,
                )
            )

    # Gateway binary sensors
    for device_id in get_devices_by_type(coordinator, DEVICE_TYPE_GATEWAY):
        for config in GATEWAY_BINARY_SENSORS:
            entities.append(
                MigoDeviceBinarySensor(
                    coordinator=coordinator,
                    device_id=device_id,
                    config=config,
                )
            )

    # Thermostat binary sensors
    for device_id in get_devices_by_type(coordinator, DEVICE_TYPE_THERMOSTAT):
        for config in THERMOSTAT_BINARY_SENSORS:
            entities.append(
                MigoDeviceBinarySensor(
                    coordinator=coordinator,
                    device_id=device_id,
                    config=config,
                )
            )

    async_add_entities(entities)


class MigoRoomBinarySensor(MigoRoomEntity, BinarySensorEntity):
    """MiGO room-based binary sensor using configuration."""

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        room_id: str,
        config: BinarySensorConfig,
    ) -> None:
        """Initialize the room binary sensor."""
        super().__init__(coordinator, room_id)
        self._config = config
        self._attr_unique_id = generate_unique_id(config.unique_id_key, room_id)
        self._attr_translation_key = config.translation_key
        self._attr_device_class = config.device_class
        self._attr_entity_category = config.entity_category

    @property
    def is_on(self) -> bool | None:
        """Return True if the sensor is on."""
        value = self._room_data.get(self._config.data_key)
        if self._config.value_fn:
            return self._config.value_fn(value)
        return value


class MigoDeviceBinarySensor(MigoDeviceEntity, BinarySensorEntity):
    """MiGO device-based binary sensor using configuration."""

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
        config: BinarySensorConfig,
    ) -> None:
        """Initialize the device binary sensor."""
        super().__init__(coordinator, device_id)
        self._config = config
        self._attr_unique_id = generate_unique_id(config.unique_id_key, device_id)
        self._attr_translation_key = config.translation_key
        self._attr_device_class = config.device_class
        self._attr_entity_category = config.entity_category

    @property
    def is_on(self) -> bool | None:
        """Return True if the sensor is on."""
        value = self._device_data.get(self._config.data_key)
        if self._config.value_fn:
            return self._config.value_fn(value)
        return value
