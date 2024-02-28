"""Define the sensors for the CPT integration."""
import logging

from homeassistant.components import bluetooth
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_IDENTIFIERS,
    ATTR_MANUFACTURER,
    ATTR_MODEL,
    ATTR_NAME,
    ATTR_SERIAL_NUMBER,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CPTBluetoothCoordinator
from .sensor_definitions import (
    BATTERY_STATUS,
    INSTANT_READ_TEMP,
    RAW_TEMP_ENTITIES,
    VIRTUAL_AMBIENT,
    VIRTUAL_CORE,
    VIRTUAL_SURFACE,
    CombustionIncSensorEntityDescription,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up out device and its entities."""

    device_name = entry.data.get(ATTR_NAME)
    serial = entry.data.get(ATTR_SERIAL_NUMBER)
    manufacturer = entry.data.get(ATTR_MANUFACTURER)
    model = entry.data.get(ATTR_MODEL)

    if serial is None:
        raise ValueError("Serial number is required")
    device = DeviceInfo(
        {
            ATTR_NAME: device_name,
            ATTR_IDENTIFIERS: {(DOMAIN, serial)},
            ATTR_MANUFACTURER: manufacturer,
            ATTR_MODEL: model,
            ATTR_SERIAL_NUMBER: serial,
        }
    )

    device_registry = dr.async_get(hass)

    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers=device[ATTR_IDENTIFIERS],
        manufacturer=device[ATTR_MANUFACTURER],
        name=device[ATTR_NAME],
        model=device[ATTR_MODEL],
    )

    bluetooth_coordinator = CPTBluetoothCoordinator(hass)
    hass.data[DOMAIN][entry.entry_id] = bluetooth_coordinator

    sensors = create_sensor_entities_for_device(device, bluetooth_coordinator)
    async_add_entities(sensors)

    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            bluetooth_coordinator.async_process_advertisement,
            {"manufacturer_id": 2503, "connectable": False},
            bluetooth.BluetoothScanningMode.PASSIVE,
        )
    )


def create_sensor_entities_for_device(
    device: DeviceInfo, coordinator: CPTBluetoothCoordinator
):
    """Create sensor entities for the device."""
    sensor_descriptions = [
        INSTANT_READ_TEMP,
        BATTERY_STATUS,
        VIRTUAL_AMBIENT,
        VIRTUAL_CORE,
        VIRTUAL_SURFACE,
    ] + RAW_TEMP_ENTITIES
    sensors = [
        CPTSensor(device, entity_description=sensor, coordinator=coordinator)
        for sensor in sensor_descriptions
    ]
    return sensors


class CPTSensor(SensorEntity, CoordinatorEntity):
    """CPT Sensor."""

    def __init__(
        self,
        device: DeviceInfo,
        entity_description: CombustionIncSensorEntityDescription,
        coordinator: CPTBluetoothCoordinator,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_device_info = device
        self._attr_unique_id = f"{device[ATTR_IDENTIFIERS]}_{entity_description.key}"
        self.entity_description = entity_description

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.entity_description.key not in self.coordinator.data:
            return
        self._attr_native_value = self.coordinator.data.get(self.entity_description.key)
        self.async_write_ha_state()
