"""Sensor platform for MiGO integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfEnergy, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEVICE_TYPE_GATEWAY, DEVICE_TYPE_THERMOSTAT, WH_PER_KWH
from .entity import MigoGatewayEntity, MigoRoomEntity, MigoThermostatEntity, register_dynamic_entities
from .helpers import generate_unique_id, get_devices_by_type, safe_float
from .models import ConsumptionData, ModuleData

if TYPE_CHECKING:
    from . import MigoConfigEntry
    from .coordinator import MigoDataUpdateCoordinator

# Coordinator-driven read-only platform
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class MigoSensorEntityDescription(SensorEntityDescription):
    """Describes a MiGO sensor entity.

    The key field is cosmetic; unique_id_key feeds generate_unique_id and
    must never change (users would lose recorder history).
    """

    data_key: str
    unique_id_key: str
    value_fn: Callable[[Any], Any] | None = None
    extra_attrs_fn: Callable[[ModuleData], dict[str, Any]] | None = None


# Room-based sensor configurations
ROOM_SENSORS: tuple[MigoSensorEntityDescription, ...] = (
    MigoSensorEntityDescription(
        key="temp",
        data_key="therm_measured_temperature",
        unique_id_key="temp",
        translation_key="room_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=safe_float,
        suggested_display_precision=1,
    ),
    MigoSensorEntityDescription(
        key="humidity",
        data_key="humidity",
        unique_id_key="humidity",
        translation_key="room_humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=safe_float,
    ),
)

# Gateway sensor configurations
GATEWAY_SENSORS: tuple[MigoSensorEntityDescription, ...] = (
    MigoSensorEntityDescription(
        key="outdoor_temp",
        data_key="outdoor_temperature",
        unique_id_key="outdoor_temp",
        translation_key="outdoor_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=safe_float,
        suggested_display_precision=1,
    ),
    MigoSensorEntityDescription(
        key="wifi",
        data_key="wifi_strength",
        unique_id_key="wifi",
        translation_key="wifi_strength",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    MigoSensorEntityDescription(
        key="gateway_firmware",
        data_key="firmware_revision",
        unique_id_key="gateway_firmware",
        translation_key="gateway_firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda v: str(v) if v is not None else None,
        entity_registry_enabled_default=False,
    ),
)


def _battery_extra_attrs(data: ModuleData) -> dict[str, Any]:
    """Extract battery extra state attributes."""
    attrs: dict[str, Any] = {}
    if (level := data.get("battery_level")) is not None:
        attrs["battery_level_mv"] = level
    if (state := data.get("battery_state")) is not None:
        attrs["battery_state"] = state
    return attrs


# Thermostat sensor configurations
THERMOSTAT_SENSORS: tuple[MigoSensorEntityDescription, ...] = (
    MigoSensorEntityDescription(
        key="battery",
        data_key="battery_percent",
        unique_id_key="battery",
        translation_key="battery",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        extra_attrs_fn=_battery_extra_attrs,
    ),
    MigoSensorEntityDescription(
        key="rf",
        data_key="rf_strength",
        unique_id_key="rf",
        translation_key="rf_strength",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        # Noisy and of no use to most users: a thermostat is not a device for
        # measuring radio signal strength. Matches wifi_strength on the gateway.
        entity_registry_enabled_default=False,
    ),
    MigoSensorEntityDescription(
        key="thermostat_firmware",
        data_key="firmware_revision",
        unique_id_key="thermostat_firmware",
        translation_key="thermostat_firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda v: str(v) if v is not None else None,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MigoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MiGO sensor entities."""
    coordinator = entry.runtime_data.coordinator

    def _room_sensors(room_id: str) -> list[SensorEntity]:
        room_data = coordinator.rooms.get(room_id, {})
        sensors: list[SensorEntity] = []
        for description in ROOM_SENSORS:
            # Only add humidity sensor if humidity data is available. Gated
            # on data content, not on the room id: a room that gains
            # humidity reporting later does not get this sensor added
            # retroactively (dynamic-devices targets new ids, not new
            # capabilities on an id already known).
            if description.data_key == "humidity" and "humidity" not in room_data:
                continue
            sensors.append(MigoRoomSensor(coordinator=coordinator, room_id=room_id, description=description))
        return sensors

    register_dynamic_entities(
        entry,
        coordinator,
        async_add_entities,
        get_current_ids=lambda: coordinator.rooms,
        create_entities=_room_sensors,
    )

    # Gateway sensors + consumption (daily boiler runtime): same id-space
    # (device_id via get_devices_by_type(GATEWAY)), created together.
    register_dynamic_entities(
        entry,
        coordinator,
        async_add_entities,
        get_current_ids=lambda: get_devices_by_type(coordinator, DEVICE_TYPE_GATEWAY),
        create_entities=lambda device_id: [
            *(
                MigoGatewaySensor(coordinator=coordinator, device_id=device_id, description=description)
                for description in GATEWAY_SENSORS
            ),
            MigoBoilerRuntimeSensor(coordinator=coordinator, device_id=device_id),
            *(
                MigoEnergySensor(coordinator=coordinator, device_id=device_id, description=description)
                for description in ENERGY_SENSORS
            ),
        ],
    )

    register_dynamic_entities(
        entry,
        coordinator,
        async_add_entities,
        get_current_ids=lambda: get_devices_by_type(coordinator, DEVICE_TYPE_THERMOSTAT),
        create_entities=lambda device_id: [
            MigoThermostatSensor(coordinator=coordinator, device_id=device_id, description=description)
            for description in THERMOSTAT_SENSORS
        ],
    )


class MigoRoomSensor(MigoRoomEntity, SensorEntity):
    """MiGO room-based sensor described by an entity description."""

    entity_description: MigoSensorEntityDescription

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        room_id: str,
        description: MigoSensorEntityDescription,
    ) -> None:
        """Initialize the room sensor."""
        super().__init__(coordinator, room_id)
        self.entity_description = description
        self._attr_unique_id = generate_unique_id(description.unique_id_key, room_id)
        room_name = self._room_data.get("name", f"Room {self._room_id}")
        self._attr_translation_placeholders = {"room_name": room_name}

    @property
    @override
    def native_value(self) -> Any:
        """Return the sensor value."""
        value = self._room_data.get(self.entity_description.data_key)
        if self.entity_description.value_fn:
            return self.entity_description.value_fn(value)
        return value


class _MigoDeviceSensorMixin(SensorEntity):
    """Mixin for device-based sensors with common functionality."""

    entity_description: MigoSensorEntityDescription

    @property
    def _device_data(self) -> ModuleData:
        """Get current device data.

        Read-only stub: the concrete entity's MRO always resolves this to
        MigoDeviceEntity._device_data (see MigoGatewaySensor/MigoThermostatSensor
        below). Declared here, matching that base's read-only property, so
        static type checkers accept the multiple inheritance.
        """
        raise NotImplementedError

    def _init_sensor(self, device_id: str, description: MigoSensorEntityDescription) -> None:
        """Initialize sensor attributes from the entity description."""
        self.entity_description = description
        self._attr_unique_id = generate_unique_id(description.unique_id_key, device_id)

    @property
    @override
    def native_value(self) -> Any:
        """Return the sensor value."""
        value = self._device_data.get(self.entity_description.data_key)
        if self.entity_description.value_fn:
            return self.entity_description.value_fn(value)
        return value

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if self.entity_description.extra_attrs_fn:
            return self.entity_description.extra_attrs_fn(self._device_data)
        return {}


class MigoGatewaySensor(MigoGatewayEntity, _MigoDeviceSensorMixin):
    """MiGO gateway sensor entity."""

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
        description: MigoSensorEntityDescription,
    ) -> None:
        """Initialize the gateway sensor."""
        super().__init__(coordinator, device_id)
        self._init_sensor(device_id, description)


class MigoThermostatSensor(MigoThermostatEntity, _MigoDeviceSensorMixin):
    """MiGO thermostat sensor entity."""

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
        description: MigoSensorEntityDescription,
    ) -> None:
        """Initialize the thermostat sensor."""
        super().__init__(coordinator, device_id)
        self._init_sensor(device_id, description)


@dataclass(frozen=True, kw_only=True)
class MigoEnergyEntityDescription(SensorEntityDescription):
    """Describes a MiGO energy sensor read from the consumption record.

    value_fn rather than a key string on purpose: a literal key keeps the
    TypedDict access statically checked, where a dynamic key would degrade to
    object and need a cast at every read.
    """

    value_fn: Callable[[ConsumptionData], float | None]
    unique_id_key: str


# Energy actually measured by the boiler, not estimated. These are what the
# Energy dashboard accepts directly: device_class energy in kWh.
#
# The API reports Wh at whole-kWh resolution, split heating vs domestic hot water
# for both gas and electricity, which is exactly the breakdown the MiGO app shows.
ENERGY_SENSORS: tuple[MigoEnergyEntityDescription, ...] = (
    MigoEnergyEntityDescription(
        key="energy_gas_heating",
        unique_id_key="energy_gas_heating",
        translation_key="energy_gas_heating",
        value_fn=lambda c: c.get("sum_energy_gaz_heating"),
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=0,
    ),
    MigoEnergyEntityDescription(
        key="energy_gas_hot_water",
        unique_id_key="energy_gas_hot_water",
        translation_key="energy_gas_hot_water",
        value_fn=lambda c: c.get("sum_energy_gaz_hot_water"),
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=0,
    ),
    MigoEnergyEntityDescription(
        key="energy_elec_heating",
        unique_id_key="energy_elec_heating",
        translation_key="energy_elec_heating",
        value_fn=lambda c: c.get("sum_energy_elec_heating"),
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=0,
    ),
    MigoEnergyEntityDescription(
        key="energy_elec_hot_water",
        unique_id_key="energy_elec_hot_water",
        translation_key="energy_elec_hot_water",
        value_fn=lambda c: c.get("sum_energy_elec_hot_water"),
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=0,
    ),
)


class MigoEnergySensor(MigoGatewayEntity, SensorEntity):
    """Daily energy measured by the boiler, in kWh.

    Unlike the runtime sensor beside it, this is directly usable as an Energy
    dashboard source: device_class energy in kWh is accepted both under Gas
    consumption and under Individual devices.

    total_increasing is correct despite the daily reset: Home Assistant handles a
    counter that returns to zero, and the API reports a per-day total.
    """

    entity_description: MigoEnergyEntityDescription

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
        description: MigoEnergyEntityDescription,
    ) -> None:
        """Initialize the energy sensor."""
        super().__init__(coordinator, device_id)
        self.entity_description = description
        self._attr_unique_id = generate_unique_id(description.unique_id_key, device_id)

    @property
    @override
    def native_value(self) -> float | None:
        """Return today's energy in kWh, or None when the API reported nothing.

        The API reports Wh. Dividing loses no precision, since the values are
        always whole kWh.
        """
        consumption = self.coordinator.get_consumption(self._device_id)
        if consumption is None:
            return None
        watt_hours = self.entity_description.value_fn(consumption)
        if watt_hours is None:
            return None
        return watt_hours / WH_PER_KWH


class MigoBoilerRuntimeSensor(MigoGatewayEntity, SensorEntity):
    """MiGO daily boiler runtime sensor.

    Reports the daily boiler runtime in seconds. Deliberately NOT eligible for the
    Energy dashboard, and it cannot be made so: that dashboard needs a gas source
    with device_class gas (volume) or energy (kWh), and the API reports how long
    the boiler ran, not how much gas it burned. Users convert runtime to energy
    with a template sensor; see the README.

    total_increasing is still correct here: it gives long-term statistics and
    handles the daily reset.
    The boiler is connected to the gateway, so this sensor belongs to the Gateway device.
    Data is retrieved using the getmeasure API with device_id and module_id.
    """

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_translation_key = "daily_boiler_runtime"
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
    @override
    def native_value(self) -> float | None:
        """Return the daily boiler runtime in seconds.

        Typed float, not int: the value is unpacked straight out of a JSON array
        whose element type the API does not pin down.
        """
        # Consumption data is now indexed by device_id (gateway)
        consumption = self.coordinator.get_consumption(self._device_id)
        if consumption:
            return consumption.get("sum_boiler_on")
        return None

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        consumption = self.coordinator.get_consumption(self._device_id)
        if consumption:
            return {
                "boiler_off_time": consumption.get("sum_boiler_off"),
                "measurement_timestamp": consumption.get("timestamp"),
            }
        return {}
