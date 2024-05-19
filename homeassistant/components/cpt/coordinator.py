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
    PREDICTION_STATE_INSERTED,
    PREDICTION_STATE_NOT_INSERTED,
    PREDICTION_STATE_NOT_PREDICTING,
    PREDICTION_STATE_OTHER,
    PREDICTION_STATE_PENDING,
    PREDICTION_STATE_PREDICTING,
    PREDICTION_STATE_READY,
    PROBE_STATUS_CHARACTERISTIC,
)
from .cpt_lib import (
    BatteryStatus,
    CptAdvertisingData,
    CptProbeStatus,
    Mode,
    PredictionMode,
    PredictionState,
    ProductType,
)
from .sensor_definitions import (
    BATTERY_STATUS,
    COOKING_TO_TEMP,
    INSTANT_READ_TEMP,
    PERCENT_THROUGH_COOK,
    PREDICTION_STATUS,
    RAW_TEMP_ENTITIES,
    READY_IN_TIME,
    VIRTUAL_AMBIENT,
    VIRTUAL_CORE,
    VIRTUAL_SURFACE,
)

_LOGGER = logging.getLogger(__name__)


class CPTBluetoothCoordinator(DataUpdateCoordinator):
    """Class to coordinate data updates from the CPT."""

    def _get_is_subscribed(self):
        return self._maybe_client is not None and self._maybe_client.is_connected

    is_subscribed_to_notifications = property(_get_is_subscribed)

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=COMBUSTION_INC,
        )
        self._maybe_client: None | BleakClient = None
        self.is_currently_subscribing = False

    def _get_battery_status_text(self, advertising_data: CptAdvertisingData) -> str:
        """Get the battery status."""
        battery_status = advertising_data.battery_status
        if battery_status == BatteryStatus.OK:
            return "OK"
        if battery_status == BatteryStatus.LOW:
            return "Low"
        return "Unknown"

    def _get_data_from_probe_status_notification(
        self,
        probe_status: CptProbeStatus,
    ) -> dict[str, (str | float | None)]:
        """Turn a probe status notification into data to send to the sensor entities."""
        data: dict[str, (str | float | None)] = {}

        if probe_status.prediction_status.mode == PredictionMode.TIME_TO_REMOVAL:
            data[
                COOKING_TO_TEMP.key
            ] = probe_status.prediction_status.prediction_set_point_temperature
            data[PERCENT_THROUGH_COOK.key] = (
                probe_status.prediction_status.pecentage_to_removal * 100
            )
            data[READY_IN_TIME.key] = None
            if probe_status.prediction_status.state == PredictionState.PREDICTING:
                data[
                    READY_IN_TIME.key
                ] = probe_status.prediction_status.prediction_value_seconds
                data[PREDICTION_STATUS.key] = PREDICTION_STATE_PREDICTING
            elif (
                probe_status.prediction_status.state
                == PredictionState.PROBE_NOT_INSERTED
            ):
                data[PREDICTION_STATUS.key] = PREDICTION_STATE_NOT_INSERTED
            elif probe_status.prediction_status.state == PredictionState.WARMING:
                data[PREDICTION_STATUS.key] = PREDICTION_STATE_PENDING
            elif probe_status.prediction_status.state == PredictionState.PROBE_INSERTED:
                data[PREDICTION_STATUS.key] = PREDICTION_STATE_INSERTED
            elif (
                probe_status.prediction_status.state
                == PredictionState.REMOVAL_PREDICTION_DONE
            ):
                data[PREDICTION_STATUS.key] = PREDICTION_STATE_READY
            else:
                data[PREDICTION_STATUS.key] = PREDICTION_STATE_OTHER
        else:
            # if we're not in time to removal, set the prediction values to none:
            data[READY_IN_TIME.key] = None
            data[PERCENT_THROUGH_COOK.key] = None
            data[COOKING_TO_TEMP.key] = None
            data[PREDICTION_STATUS.key] = PREDICTION_STATE_NOT_PREDICTING
        return data

    def _get_data_from_advertisement(
        self,
        advertising_data: CptAdvertisingData,
    ) -> dict[str, (str | float | None)]:
        """Turn an advertisement into data to send to the sensor entities."""
        data: dict[str, (str | float | None)] = {}

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

    async def maybe_disconnect_bt_client(self):
        """Disconnect the active client if there is one."""
        if self._maybe_client is not None and self._maybe_client.is_connected:
            await self._maybe_client.disconnect()

    async def _maybe_subscribe_to_notifications(
        self, service_info: BluetoothServiceInfoBleak
    ):
        if self.is_subscribed_to_notifications or self.is_currently_subscribing:
            return
        self.is_currently_subscribing = True
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
        self._maybe_client = BleakClient(connectable_device)
        await self._maybe_client.connect()

        def notification_callback(sender: BleakGATTCharacteristic, data: bytearray):
            probe_status = CptProbeStatus(data)
            data_from_probe_status = self._get_data_from_probe_status_notification(
                probe_status
            )
            self.async_set_updated_data(data_from_probe_status)

        await self._maybe_client.start_notify(
            PROBE_STATUS_CHARACTERISTIC, notification_callback
        )
        self.is_currently_subscribing = False

    @callback
    def async_process_advertisement(
        self, service_info: BluetoothServiceInfoBleak, change: bluetooth.BluetoothChange
    ) -> None:
        """Turn an advertisement into parsed CPT data."""
        advertisement = self._extract_advertisement(service_info)
        if advertisement.device.product_type != ProductType.PREDICTIVE_PROBE:
            _LOGGER.debug(
                "Ignoring advertisement from device with product type %s",
                advertisement.device.product_type,
            )
            return
        data = self._get_data_from_advertisement(advertisement)
        self.async_set_updated_data(data)
        if service_info.connectable:
            self.hass.loop.create_task(
                self._maybe_subscribe_to_notifications(service_info)
            )
        else:
            _LOGGER.info("Received a non-connectable probe advertisement")

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
