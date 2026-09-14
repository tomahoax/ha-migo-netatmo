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
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    BOILER_MODE_DHW_ONLY,
    BOILER_MODE_FROST_GUARD,
    BOILER_MODE_NORMAL,
    DEVICE_TYPE_GATEWAY,
    DEVICE_TYPE_THERMOSTAT,
)
from .entity import MigoGatewayEntity, MigoRoomEntity, MigoThermostatEntity
from .helpers import derive_boiler_mode, generate_unique_id, get_devices_by_type, get_rooms_for_home, safe_float

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
    suggested_display_precision: int | None = None


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
        suggested_display_precision=1,
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
        suggested_display_precision=1,
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
    # No firmware_revision sensor here: it duplicates the device page's own
    # "Device info" card, which already shows it as sw_version (see
    # MigoGatewayEntity.device_info in entity.py).
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
        entity_category=EntityCategory.DIAGNOSTIC,
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
    # No firmware_revision sensor here either - same reasoning as the
    # Gateway's, it duplicates the Device info card's sw_version.
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
                MigoGatewaySensor(
                    coordinator=coordinator,
                    device_id=device_id,
                    config=config,
                )
            )

    # Thermostat sensors
    for device_id in get_devices_by_type(coordinator, DEVICE_TYPE_THERMOSTAT):
        for config in THERMOSTAT_SENSORS:
            entities.append(
                MigoThermostatSensor(
                    coordinator=coordinator,
                    device_id=device_id,
                    config=config,
                )
            )

    # Consumption sensors - one per gateway (daily boiler runtime)
    # The boiler is connected to the gateway, so consumption data belongs there
    # Data is now indexed by device_id (gateway) instead of room_id
    for device_id in get_devices_by_type(coordinator, DEVICE_TYPE_GATEWAY):
        entities.append(
            MigoBoilerRuntimeSensor(
                coordinator=coordinator,
                device_id=device_id,
            )
        )

    # Boiler mode sensor - one per gateway
    for device_id in get_devices_by_type(coordinator, DEVICE_TYPE_GATEWAY):
        entities.append(
            MigoBoilerModeSensor(
                coordinator=coordinator,
                device_id=device_id,
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
        if config.suggested_display_precision is not None:
            self._attr_suggested_display_precision = config.suggested_display_precision

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


class _MigoDeviceSensorMixin(SensorEntity):
    """Mixin for device-based sensors with common functionality."""

    _config: SensorConfig
    _device_data: dict[str, Any]

    def _init_sensor(self, device_id: str, config: SensorConfig) -> None:
        """Initialize sensor attributes from config."""
        self._config = config
        self._attr_unique_id = generate_unique_id(config.unique_id_key, device_id)
        self._attr_translation_key = config.translation_key
        self._attr_device_class = config.device_class
        self._attr_state_class = config.state_class
        self._attr_native_unit_of_measurement = config.unit
        self._attr_entity_category = config.entity_category
        if config.icon:
            self._attr_icon = config.icon
        if config.suggested_display_precision is not None:
            self._attr_suggested_display_precision = config.suggested_display_precision

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


class MigoGatewaySensor(MigoGatewayEntity, _MigoDeviceSensorMixin):
    """MiGO gateway sensor entity."""

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
        config: SensorConfig,
    ) -> None:
        """Initialize the gateway sensor."""
        super().__init__(coordinator, device_id)
        self._init_sensor(device_id, config)


class MigoThermostatSensor(MigoThermostatEntity, _MigoDeviceSensorMixin):
    """MiGO thermostat sensor entity."""

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
        config: SensorConfig,
    ) -> None:
        """Initialize the thermostat sensor."""
        super().__init__(coordinator, device_id)
        self._init_sensor(device_id, config)


class MigoBoilerRuntimeSensor(MigoGatewayEntity, SensorEntity):
    """MiGO daily boiler runtime sensor for Energy Dashboard.

    This sensor tracks the daily boiler runtime in seconds,
    which can be used to estimate energy consumption.
    The boiler is connected to the gateway, so this sensor belongs to the Gateway device.
    Data is retrieved using the getmeasure API with device_id and module_id.
    """

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_translation_key = "daily_boiler_runtime"
    _attr_icon = "mdi:fire"
    _attr_suggested_display_precision = 0

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
    ) -> None:
        """Initialize the boiler runtime sensor."""
        super().__init__(coordinator, device_id)
        self._attr_unique_id = generate_unique_id("boiler_runtime", device_id)

    @property
    def native_value(self) -> int | None:
        """Return the daily boiler runtime in seconds."""
        # Consumption data is now indexed by device_id (gateway)
        consumption = self.coordinator.get_consumption(self._device_id)
        if consumption:
            return consumption.get("sum_boiler_on")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        consumption = self.coordinator.get_consumption(self._device_id)
        if consumption:
            return {
                "boiler_off_time": consumption.get("sum_boiler_off"),
                "measurement_timestamp": consumption.get("timestamp"),
            }
        return {}


class MigoBoilerModeSensor(MigoGatewayEntity, SensorEntity):
    """MiGO boiler quick-action mode (Normal / DHW only / Frost guard).

    MiGo does not return this as a single field: it is derived from the
    home's `therm_mode` and its rooms' `therm_setpoint_mode`, see
    `helpers.derive_boiler_mode`. Independent of the Away preset, which the
    app lets you combine with any of these three.
    """

    _attr_translation_key = "boiler_mode"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [BOILER_MODE_NORMAL, BOILER_MODE_DHW_ONLY, BOILER_MODE_FROST_GUARD]
    _attr_icon = "mdi:radiator"

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
    ) -> None:
        """Initialize the boiler mode sensor."""
        super().__init__(coordinator, device_id)
        self._attr_unique_id = generate_unique_id("boiler_mode", device_id)

    @property
    def native_value(self) -> str | None:
        """Return the current boiler mode."""
        home_id = self._device_data.get("home_id")
        if not home_id:
            return None
        home_data = self.coordinator.homes.get(home_id)
        if home_data is None:
            return None

        room_modes = [room.get("therm_setpoint_mode") for room in get_rooms_for_home(self.coordinator, home_id)]
        return derive_boiler_mode(home_data.get("therm_mode"), room_modes)
