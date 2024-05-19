"""Coordinates communication with the Combustion Inc therometer."""
import logging

from cpt_python import (
    BatteryStatus,
    CptAdvertisement,
    CPTConnectionManager,
    CptProbeStatus,
    Mode,
    PredictionMode,
    PredictionState,
    ProductType,
)

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_ble_device_from_address,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    COMBUSTION_INC,
    PREDICTION_STATE_INSERTED,
    PREDICTION_STATE_NOT_INSERTED,
    PREDICTION_STATE_NOT_PREDICTING,
    PREDICTION_STATE_OTHER,
    PREDICTION_STATE_PENDING,
    PREDICTION_STATE_PREDICTING,
    PREDICTION_STATE_READY,
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

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=COMBUSTION_INC,
        )
        self.cpt_connection_manager = CPTConnectionManager()

    def _get_battery_status_text(self, advertising_data: CptAdvertisement) -> str:
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

    def _convert_advertisement_to_sensor_updates(
        self,
        advertising_data: CptAdvertisement,
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

    async def maybe_disconnect_bt_client(self) -> None:
        """Disconnect the active client if there is one."""
        await self.cpt_connection_manager.maybe_disconnect_from_client()

    async def _maybe_subscribe_to_notifications(
        self, service_info: BluetoothServiceInfoBleak
    ) -> None:
        if (
            self.cpt_connection_manager.is_subscribed_to_notifications
            or self.cpt_connection_manager.is_currently_subscribing
        ):
            return
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

        def process_probe_status_notification(probe_status: CptProbeStatus) -> None:
            sensor_updates = self._get_data_from_probe_status_notification(probe_status)
            self.async_set_updated_data(sensor_updates)

        await self.cpt_connection_manager.maybe_subscribe_to_notifications(
            connectable_device, process_probe_status_notification
        )

    @callback
    def async_process_advertisement(
        self, service_info: BluetoothServiceInfoBleak, change: bluetooth.BluetoothChange
    ) -> None:
        """Turn an advertisement into parsed CPT data."""
        advertisement = self.cpt_connection_manager.parse_raw_cpt_advertisement(
            service_info.advertisement
        )
        if advertisement.device.product_type != ProductType.PREDICTIVE_PROBE:
            _LOGGER.debug(
                "Ignoring advertisement from device with product type %s",
                advertisement.device.product_type,
            )
            return
        sensor_updates = self._convert_advertisement_to_sensor_updates(advertisement)
        self.async_set_updated_data(sensor_updates)

        if service_info.connectable:
            self.hass.loop.create_task(
                self._maybe_subscribe_to_notifications(service_info)
            )
        else:
            _LOGGER.info("Received a non-connectable probe advertisement")
