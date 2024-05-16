"""Coordinates communication with the CPT therometer."""
import logging

from bleak import BleakClient, BleakGATTCharacteristic

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_ble_device_from_address,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    COMBUSTION_INC,
    COMBUSTION_MANUFACTURER_ID,
    PROBE_STATUS_CHARACTERISTIC,
)
from .cpt_lib import BatteryStatus, CptAdvertisingData, Mode
from .sensor_definitions import (
    BATTERY_STATUS,
    INSTANT_READ_TEMP,
    RAW_TEMP_ENTITIES,
    VIRTUAL_AMBIENT,
    VIRTUAL_CORE,
    VIRTUAL_SURFACE,
)

_LOGGER = logging.getLogger(__name__)


class CPTBluetoothCoordinator(DataUpdateCoordinator):
    """Class to coordinate data updates from the CPT."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=COMBUSTION_INC,
        )
        self.is_subscribed_to_notifications = False
        self._maybe_client: None | BleakClient = None

    def _get_battery_status_text(self, advertising_data: CptAdvertisingData) -> str:
        """Get the battery status."""
        battery_status = advertising_data.battery_status
        if battery_status == BatteryStatus.OK:
            return "OK"
        if battery_status == BatteryStatus.LOW:
            return "Low"
        return "Unknown"

    def _get_data_from_advertisement(
        self,
        advertising_data: CptAdvertisingData,
    ) -> dict[str, (str | float)]:
        """Turn an advertisements into data to send to the sensor entities."""
        data: dict[str, (str | float)] = {}

        # Mode
        if advertising_data.mode == Mode.INSTANT_READ:
            data[INSTANT_READ_TEMP.key] = advertising_data.raw_temperatures.t1
        else:
            # Raw Temperatures
            for entity in RAW_TEMP_ENTITIES:
                temp_attribute = entity.key.replace("_temperature", "")
                data[entity.key] = getattr(
                    advertising_data.raw_temperatures, temp_attribute
                )

            # Virtual Core
            data[VIRTUAL_CORE.key] = advertising_data.virtual_sensors.core

            # Virtual Ambient
            data[VIRTUAL_AMBIENT.key] = advertising_data.virtual_sensors.ambient

            # Virtual Surface
            data[VIRTUAL_SURFACE.key] = advertising_data.virtual_sensors.surface

        # Battery Status
        data[BATTERY_STATUS.key] = self._get_battery_status_text(advertising_data)

        return data

    def maybe_disconnect_bt_client(self):
        """Disconnect the active client if there is one."""
        if self._maybe_client is not None and self._maybe_client.is_connected:
            self._maybe_client.disconnect()

    async def _maybe_subscribe_to_notifications(
        self, service_info: BluetoothServiceInfoBleak
    ):
        if self.is_subscribed_to_notifications:
            return
        self.is_subscribed_to_notifications = True
        _LOGGER.info("Subscribing to notifications")
        # exchange our passive device for a connectable one
        if service_info.connectable:
            connectable_device = service_info.device
        elif device := async_ble_device_from_address(
            self.hass, service_info.device.address, True
        ):
            connectable_device = device
        else:
            # We have no Bluetooth controller that is in range of
            # the device to poll it
            raise RuntimeError(
                f"No connectable device found for {service_info.device.address}"
            )
        client = BleakClient(connectable_device)
        await client.connect()

        def notification_callback(sender: BleakGATTCharacteristic, data: bytearray):
            _LOGGER.info("Got notification from connected sensor!")

        await client.start_notify(PROBE_STATUS_CHARACTERISTIC, notification_callback)

    @callback
    def async_process_advertisement(
        self, service_info: BluetoothServiceInfoBleak, change: bluetooth.BluetoothChange
    ) -> None:
        """Turn an advertisement into parsed CPT data."""
        advertisement = self._extract_advertisement(service_info)
        data = self._get_data_from_advertisement(advertisement)
        self.async_set_updated_data(data)
        self.hass.loop.create_task(self._maybe_subscribe_to_notifications(service_info))

    def _extract_advertisement(
        self, service_info: BluetoothServiceInfoBleak
    ) -> CptAdvertisingData:
        raw_advertisement_data = service_info.advertisement.manufacturer_data.get(
            COMBUSTION_MANUFACTURER_ID
        )
        if raw_advertisement_data is None:
            raise (ValueError("Invalid manufacturer data"))
        parsed = CptAdvertisingData(raw_advertisement_data)
        return parsed
