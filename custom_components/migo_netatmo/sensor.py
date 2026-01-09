"""Sensor platform for MiGO integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEVICE_TYPE_GATEWAY, DEVICE_TYPE_THERMOSTAT
from .entity import MigoDeviceEntity, MigoRoomEntity
from .helpers import generate_unique_id, get_devices_by_type, safe_float

if TYPE_CHECKING:
    from . import MigoConfigEntry
    from .coordinator import MigoDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class SensorConfig:
    """Configuration for a sensor entity."""

    data_key: str
    unique_id_key: str
    translation_key: str
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None
    unit: str | None = None
    entity_category: EntityCategory | None = None
    icon: str | None = None
    value_fn: Callable[[Any], Any] | None = None
    extra_attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


# Room-based sensor configurations
ROOM_SENSORS: tuple[SensorConfig, ...] = (
    SensorConfig(
        data_key="therm_measured_temperature",
        unique_id_key="temp",
        translation_key="room_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        unit=UnitOfTemperature.CELSIUS,
        value_fn=safe_float,
    ),
    SensorConfig(
        data_key="humidity",
        unique_id_key="humidity",
        translation_key="room_humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        unit=PERCENTAGE,
        value_fn=safe_float,
    ),
)

# Gateway sensor configurations
GATEWAY_SENSORS: tuple[SensorConfig, ...] = (
    SensorConfig(
        data_key="outdoor_temperature",
        unique_id_key="outdoor_temp",
        translation_key="outdoor_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        unit=UnitOfTemperature.CELSIUS,
        value_fn=safe_float,
    ),
    SensorConfig(
        data_key="wifi_strength",
        unique_id_key="wifi",
        translation_key="wifi_strength",
        state_class=SensorStateClass.MEASUREMENT,
        unit=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:wifi",
    ),
    SensorConfig(
        data_key="firmware_revision",
        unique_id_key="gateway_firmware",
        translation_key="gateway_firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda v: str(v) if v is not None else None,
    ),
    SensorConfig(
        data_key="heating_type",
        unique_id_key="heating_type",
        translation_key="heating_type",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:radiator",
        value_fn=lambda v: v if v else "unknown",
    ),
)


def _battery_extra_attrs(data: dict[str, Any]) -> dict[str, Any]:
    """Extract battery extra state attributes."""
    attrs = {}
    if (level := data.get("battery_level")) is not None:
        attrs["battery_level_mv"] = level
    if (state := data.get("battery_state")) is not None:
        attrs["battery_state"] = state
    return attrs


# Thermostat sensor configurations
THERMOSTAT_SENSORS: tuple[SensorConfig, ...] = (
    SensorConfig(
        data_key="battery_percent",
        unique_id_key="battery",
        translation_key="battery",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        unit=PERCENTAGE,
        extra_attrs_fn=_battery_extra_attrs,
    ),
    SensorConfig(
        data_key="rf_strength",
        unique_id_key="rf",
        translation_key="rf_strength",
        state_class=SensorStateClass.MEASUREMENT,
        unit=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:signal",
    ),
    SensorConfig(
        data_key="firmware_revision",
        unique_id_key="thermostat_firmware",
        translation_key="thermostat_firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda v: str(v) if v is not None else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MigoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MiGO sensor entities."""
    coordinator = entry.runtime_data.coordinator

    entities: list[SensorEntity] = []

    # Room-based sensors
    for room_id, room_data in coordinator.rooms.items():
        for config in ROOM_SENSORS:
            # Only add humidity sensor if humidity data is available
            if config.data_key == "humidity" and "humidity" not in room_data:
                continue
            entities.append(
                MigoRoomSensor(
                    coordinator=coordinator,
                    room_id=room_id,
                    config=config,
                )
            )

    # Gateway sensors
    for device_id in get_devices_by_type(coordinator, DEVICE_TYPE_GATEWAY):
        for config in GATEWAY_SENSORS:
            entities.append(
                MigoDeviceSensor(
                    coordinator=coordinator,
                    device_id=device_id,
                    config=config,
                )
            )

    # Thermostat sensors
    for device_id in get_devices_by_type(coordinator, DEVICE_TYPE_THERMOSTAT):
        for config in THERMOSTAT_SENSORS:
            entities.append(
                MigoDeviceSensor(
                    coordinator=coordinator,
                    device_id=device_id,
                    config=config,
                )
            )

    async_add_entities(entities)


class MigoRoomSensor(MigoRoomEntity, SensorEntity):
    """MiGO room-based sensor using configuration."""

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        room_id: str,
        config: SensorConfig,
    ) -> None:
        """Initialize the room sensor."""
        super().__init__(coordinator, room_id)
        self._config = config
        self._attr_unique_id = generate_unique_id(config.unique_id_key, room_id)
        self._attr_translation_key = config.translation_key
        self._attr_device_class = config.device_class
        self._attr_state_class = config.state_class
        self._attr_native_unit_of_measurement = config.unit
        self._attr_entity_category = config.entity_category
        if config.icon:
            self._attr_icon = config.icon

    @property
    def translation_placeholders(self) -> dict[str, str]:
        """Return translation placeholders."""
        room_name = self._room_data.get("name", f"Room {self._room_id}")
        return {"room_name": room_name}

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        value = self._room_data.get(self._config.data_key)
        if self._config.value_fn:
            return self._config.value_fn(value)
        return value


class MigoDeviceSensor(MigoDeviceEntity, SensorEntity):
    """MiGO device-based sensor using configuration."""

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
        config: SensorConfig,
    ) -> None:
        """Initialize the device sensor."""
        super().__init__(coordinator, device_id)
        self._config = config
        self._attr_unique_id = generate_unique_id(config.unique_id_key, device_id)
        self._attr_translation_key = config.translation_key
        self._attr_device_class = config.device_class
        self._attr_state_class = config.state_class
        self._attr_native_unit_of_measurement = config.unit
        self._attr_entity_category = config.entity_category
        if config.icon:
            self._attr_icon = config.icon

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        value = self._device_data.get(self._config.data_key)
        if self._config.value_fn:
            return self._config.value_fn(value)
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if self._config.extra_attrs_fn:
            return self._config.extra_attrs_fn(self._device_data)
        return {}
