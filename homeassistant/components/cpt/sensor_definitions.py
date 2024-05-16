"""Defines sensor entities for the CPT integration."""
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfTemperature

from .const import BATTERY_STATE_LOW, BATTERY_STATE_OK, BATTERY_STATE_UNKNOWN


@dataclass(frozen=True)
class CombustionIncSensorEntityDescription(SensorEntityDescription):
    """Class to describe a CPT sensor entity."""

    name: str
    suggested_display_precision: int = 1


RAW_TEMP_ENTITIES = [
    CombustionIncSensorEntityDescription(
        key=f"t{i}_temperature",
        name=f"T{i} Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        icon=f"mdi:numeric-{i}",
    )
    for i in range(1, 8)
]

BATTERY_STATUS = CombustionIncSensorEntityDescription(
    key="battery_status",
    name="Battery Status",
    device_class=SensorDeviceClass.ENUM,
    options=[BATTERY_STATE_OK, BATTERY_STATE_LOW, BATTERY_STATE_UNKNOWN],
    icon="mdi:battery",
)

VIRTUAL_CORE = CombustionIncSensorEntityDescription(
    key="core_temperature",
    name="Core Temperature",
    device_class=SensorDeviceClass.TEMPERATURE,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    state_class=SensorStateClass.MEASUREMENT,
    icon="mdi:thermometer-probe",
)

VIRTUAL_SURFACE = CombustionIncSensorEntityDescription(
    key="surface_temperature",
    name="Surface Temperature",
    device_class=SensorDeviceClass.TEMPERATURE,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    state_class=SensorStateClass.MEASUREMENT,
    icon="mdi:thermometer-probe",
)

VIRTUAL_AMBIENT = CombustionIncSensorEntityDescription(
    key="ambient_temperature",
    name="Ambient Temperature",
    device_class=SensorDeviceClass.TEMPERATURE,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    state_class=SensorStateClass.MEASUREMENT,
    icon="mdi:thermometer-probe",
)

INSTANT_READ_TEMP = CombustionIncSensorEntityDescription(
    key="instant_read_temp",
    name="Instant Read Temperature",
    device_class=SensorDeviceClass.TEMPERATURE,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    state_class=SensorStateClass.MEASUREMENT,
    icon="mdi:thermometer-probe",
)
