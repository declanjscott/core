"""Library to parse payloads from CPT thermometers."""
from collections.abc import Callable
from enum import Enum

from bleak import AdvertisementData, BleakClient, BleakGATTCharacteristic
from bleak.backends.device import BLEDevice

COMBUSTION_MANUFACTURER_ID = 2503
PROBE_STATUS_CHARACTERISTIC = "00000101-CAAB-3792-3D44-97AE51C1407A"


class ProductType(Enum):
    """The type of the product."""

    UNKNOWN = 0
    PREDICTIVE_PROBE = 1
    KITCHEN_TIMER = 2

    @staticmethod
    def from_raw_data(product_type_byte: int):
        """Parse the product type from the raw data."""
        if product_type_byte == 0:
            return ProductType.UNKNOWN
        if product_type_byte == 1:
            return ProductType.PREDICTIVE_PROBE
        if product_type_byte == 2:
            return ProductType.KITCHEN_TIMER
        return ProductType.UNKNOWN

    def __str__(self) -> str:
        """Return nice name for the product."""
        if self == ProductType.PREDICTIVE_PROBE:
            return "Predictive Thermometer"
        if self == ProductType.KITCHEN_TIMER:
            return "Timer"
        return "Unknown"


class Mode(Enum):
    """The mode of the thermometer."""

    NORMAL = 0
    INSTANT_READ = 1
    RESERVED = 2
    ERROR = 3
    UNKNOWN = 4

    @staticmethod
    def from_raw_data(mode_colour_and_id: int):
        """Parse the mode from the raw data."""
        _MODE_MASK = 0x3
        mode_id = mode_colour_and_id & _MODE_MASK
        if mode_id == 0:
            return Mode.NORMAL
        if mode_id == 1:
            return Mode.INSTANT_READ
        if mode_id == 2:
            return Mode.RESERVED
        if mode_id == 3:
            return Mode.ERROR
        raise ValueError("Invalid mode")


class Colour(Enum):
    """The colour of the thermometer."""

    YELLOW = 0
    GREY = 1
    UNKNOWN = 2

    @staticmethod
    def from_raw_data(colour_byte: int):
        """Parse the colour from the raw data."""
        if colour_byte == 0:
            return Colour.YELLOW
        if colour_byte == 1:
            return Colour.GREY
        return Colour.UNKNOWN

    def __str__(self) -> str:
        """Return nice name for the colour."""
        if self == Colour.YELLOW:
            return "Yellow"
        if self == Colour.GREY:
            return "Grey"
        return "Unknown"


class BatteryStatus(Enum):
    """Current battery status."""

    OK = 0
    LOW = 1

    @staticmethod
    def from_raw_data(battery_status_and_virtual_sensors: int):
        """Parse the battery status from the raw data."""
        battery_status_int = (battery_status_and_virtual_sensors >> 7) & 0x01
        if battery_status_int == 0:
            return BatteryStatus.OK
        if battery_status_int == 1:
            return BatteryStatus.LOW
        raise ValueError("Invalid battery status")


class VirtualSensors:
    """The virtual sensors of the thermometer."""

    def __init__(self, core: float, surface: float, ambient: float) -> None:
        """Initialise with the core, surface and ambient temperatures."""
        self.core: float = core
        self.surface: float = surface
        self.ambient: float = ambient

    @staticmethod
    def from_raw_data(battery_status_and_virtual_sensors: int, raw_temps: list[float]):
        """Parse the virtual sensors from the raw data."""
        virtual_sensors = battery_status_and_virtual_sensors >> 1

        core_mask = 0x7

        surface_mask = 0x3
        surface_shift = 3

        ambient_mask = 0x3
        ambient_shift = 5

        core_index = virtual_sensors & core_mask
        surface_index = (virtual_sensors >> surface_shift) & surface_mask
        ambient_index = (virtual_sensors >> ambient_shift) & ambient_mask

        core = raw_temps[core_index]
        # surface range is T4 - T7, therefore add 3
        surface = raw_temps[surface_index + 3]
        # ambient range is T5 - T8, therefore add 4
        ambient = raw_temps[ambient_index + 4]
        return VirtualSensors(core, surface, ambient)


class ProbeTemperatures:
    """The 7 temperatures from the probe."""

    def __init__(self, temperatures: list[float]) -> None:
        """Initialise the temps with a list."""
        self.temperatures = temperatures
        self.t1: float = temperatures[0]
        self.t2: float = temperatures[1]
        self.t3: float = temperatures[2]
        self.t4: float = temperatures[3]
        self.t5: float = temperatures[4]
        self.t6: float = temperatures[5]
        self.t7: float = temperatures[6]
        self.t8: float = temperatures[7]

    @staticmethod
    def from_raw_data(temp_bytes: bytes):
        """Parse the raw temperature data."""
        temp_bytes = temp_bytes[::-1]  # need to reverse the bytes list
        raw_temps: list[float] = []

        # Add the temperatures in reverse order
        raw_temps.insert(
            0, ((temp_bytes[0] & 0xFF) << 5) | ((temp_bytes[1] & 0xF8) >> 3)
        )
        raw_temps.insert(
            0,
            ((temp_bytes[1] & 0x07) << 10)
            | ((temp_bytes[2] & 0xFF) << 2)
            | ((temp_bytes[3] & 0xC0) >> 6),
        )
        raw_temps.insert(
            0, ((temp_bytes[3] & 0x3F) << 7) | ((temp_bytes[4] & 0xFE) >> 1)
        )
        raw_temps.insert(
            0,
            ((temp_bytes[4] & 0x01) << 12)
            | ((temp_bytes[5] & 0xFF) << 4)
            | ((temp_bytes[6] & 0xF0) >> 4),
        )
        raw_temps.insert(
            0,
            ((temp_bytes[6] & 0x0F) << 9)
            | ((temp_bytes[7] & 0xFF) << 1)
            | ((temp_bytes[8] & 0x80) >> 7),
        )
        raw_temps.insert(
            0, ((temp_bytes[8] & 0x7F) << 6) | ((temp_bytes[9] & 0xFC) >> 2)
        )
        raw_temps.insert(
            0,
            ((temp_bytes[9] & 0x03) << 11)
            | ((temp_bytes[10] & 0xFF) << 3)
            | ((temp_bytes[11] & 0xE0) >> 5),
        )
        raw_temps.insert(0, ((temp_bytes[11] & 0x1F) << 8) | (temp_bytes[12] & 0xFF))

        temperatures = [temp * 0.05 - 20.0 for temp in raw_temps]

        return ProbeTemperatures(temperatures)

    def __str__(self):
        """Return a string representation of the temperatures."""
        return f"t1={self.t1:.2f}, t2={self.t2:.2f}, t3={self.t3:.2f}, t4={self.t4:.2f}, t5={self.t5:.2f}, t6={self.t6:.2f}, t7={self.t7:.2f}, t8={self.t8:.2f}"


class CPTDevice:
    """A CPT device."""

    def __init__(self, serial: str, product_type: ProductType, colour: Colour) -> None:
        """Initialise the device."""
        self.serial: str = serial
        self.product_type: ProductType = product_type
        self.colour: Colour = colour

    @staticmethod
    def _get_serial(raw_serial) -> str:
        """Get the serial number from the raw data."""
        return raw_serial[::-1].hex().upper()

    @staticmethod
    def from_raw_data(
        raw_serial: bytes, raw_product_type: int, mode_colour_and_id: int
    ):
        """Parse the device from the raw data."""
        product_type: ProductType = ProductType.from_raw_data(raw_product_type)
        serial: str = CPTDevice._get_serial(raw_serial)
        COLOUR_MASK = 0x7
        COLOUR_SHIFT = 2
        color_id = (mode_colour_and_id >> COLOUR_SHIFT) & COLOUR_MASK
        colour: Colour = Colour.from_raw_data(color_id)
        return CPTDevice(serial, product_type, colour)


class CptAdvertisement:
    """Data advertised from the CPT thermometer."""

    def __init__(self, advertisting_data: bytes) -> None:
        """Initialise from the raw advertising data."""
        if len(advertisting_data) < 20:
            raise ValueError("Invalid advertising data")

        raw_product_type = advertisting_data[0]
        raw_serial_number = advertisting_data[1:5]
        raw_temp_data_bytes = advertisting_data[5:18]
        mode_colour_and_id = advertisting_data[18]
        battery_status_and_virtual_sensors = advertisting_data[19]

        self.raw_temperatures: ProbeTemperatures = ProbeTemperatures.from_raw_data(
            raw_temp_data_bytes
        )
        self.device = CPTDevice.from_raw_data(
            raw_serial_number, raw_product_type, mode_colour_and_id
        )
        self.mode: Mode = Mode.from_raw_data(mode_colour_and_id)
        self.probe_id = CptAdvertisement._get_probe_id(mode_colour_and_id)
        self.battery_status: BatteryStatus = BatteryStatus.from_raw_data(
            battery_status_and_virtual_sensors
        )
        self.virtual_sensors: VirtualSensors = VirtualSensors.from_raw_data(
            battery_status_and_virtual_sensors, self.raw_temperatures.temperatures
        )

    def __str__(self) -> str:
        """Return a string representation of the thermoeter state."""
        summary = f"Product Type: {self.device.product_type.name}\n"
        summary += f"Serial Number: {self.device.serial}\n"
        summary += f"Raw Temperatures: {self.raw_temperatures}\n"
        summary += f"Mode: {self.mode.name}\n"
        summary += f"Colour: {self.device.colour.name}\n"
        summary += f"Probe ID: {self.probe_id}\n"
        summary += f"Battery Status: {self.battery_status.name}\n"
        return summary

    def get_device_title(self) -> str:
        """Return a nice title for the device."""
        return f"{self.device.product_type} {self.device.serial}"

    @staticmethod
    def _get_probe_id(mode_colour_and_id: int) -> int:
        ID_MASK = 0x7
        ID_SHIFT = 5
        return (mode_colour_and_id >> ID_SHIFT) & ID_MASK


class PredictionMode(Enum):
    """CPT Prediction Mode."""

    NONE = 0
    TIME_TO_REMOVAL = 1
    REMOVAL_AND_RESTING = 2
    UNKNOWN = 3

    @staticmethod
    def from_raw_data(prediction_status_bytes: bytes):
        """Parse the prediction mode from the raw data."""
        PREDICTION_MODE_MASK = 0x3
        prediction_mode = (prediction_status_bytes[0] >> 4) & PREDICTION_MODE_MASK
        if prediction_mode == 0:
            return PredictionMode.NONE
        if prediction_mode == 1:
            return PredictionMode.TIME_TO_REMOVAL
        if prediction_mode == 2:
            return PredictionMode.REMOVAL_AND_RESTING
        return PredictionMode.UNKNOWN


class PredictionType(Enum):
    """CPT Prediction Type."""

    NONE = 0
    REMOVAL = 1
    RESTING = 2
    UNKNOWN = 3

    @staticmethod
    def from_raw_data(prediction_status_bytes: bytes):
        """Parse the prediction type from the raw data."""
        PREDICTION_TYPE_MASK = 0x3
        prediction_type = (prediction_status_bytes[0] >> 6) & PREDICTION_TYPE_MASK
        if prediction_type == 0:
            return PredictionType.NONE
        if prediction_type == 1:
            return PredictionType.REMOVAL
        if prediction_type == 2:
            return PredictionType.RESTING
        return PredictionType.UNKNOWN


class PredictionState(Enum):
    """CPT Prediction State."""

    PROBE_NOT_INSERTED = 0
    PROBE_INSERTED = 1
    WARMING = 2
    PREDICTING = 3
    REMOVAL_PREDICTION_DONE = 4
    RESERVED_STATE_5 = 5
    RESERVED_STATE_6 = 6
    RESERVED_STATE_7 = 7
    RESERVED_STATE_8 = 8
    RESERVED_STATE_9 = 9
    RESERVED_STATE_10 = 10
    RESERVED_STATE_11 = 11
    RESERVED_STATE_12 = 12
    RESERVED_STATE_13 = 13
    RESERVED_STATE_14 = 14
    UNKNOWN = 15

    @staticmethod
    def from_raw_data(prediction_status_bytes: bytes):
        """Parse the prediction state from the raw data."""
        PREDICTION_STATE_MASK = 0xF
        prediction_state = prediction_status_bytes[0] & PREDICTION_STATE_MASK
        if prediction_state == 0:
            return PredictionState.PROBE_NOT_INSERTED
        if prediction_state == 1:
            return PredictionState.PROBE_INSERTED
        if prediction_state == 2:
            return PredictionState.WARMING
        if prediction_state == 3:
            return PredictionState.PREDICTING
        if prediction_state == 4:
            return PredictionState.REMOVAL_PREDICTION_DONE
        return PredictionState.UNKNOWN


class PredictionStatus:
    """CPT Prediction Status."""

    def __init__(
        self,
        mode: PredictionMode,
        prediction_type: PredictionType,
        state: PredictionState,
        prediction_set_point_temperature: float,
        heat_start_temperature: float,
        prediction_value_seconds: int,
        estimated_core_temp: float,
    ) -> None:
        """Initialise the prediction status."""
        self.mode: PredictionMode = mode
        self.prediction_type: PredictionType = prediction_type
        self.state: PredictionState = state
        self.prediction_set_point_temperature: float = prediction_set_point_temperature
        self.heat_start_temperature: float = heat_start_temperature
        self.prediction_value_seconds: int = prediction_value_seconds
        self.estimated_core_temp: float = estimated_core_temp
        self.pecentage_to_removal: float | None = None
        if mode != PredictionMode.NONE:
            self.pecentage_to_removal = (
                estimated_core_temp - heat_start_temperature
            ) / (prediction_set_point_temperature - heat_start_temperature)

    @staticmethod
    def from_raw_data(raw_bytes: bytes):
        """Parse the prediction status from the raw data."""
        state = PredictionState.from_raw_data(raw_bytes)
        mode = PredictionMode.from_raw_data(raw_bytes)
        prediction_type = PredictionType.from_raw_data(raw_bytes)

        # 10 bit field
        raw_set_point = int(raw_bytes[2] & 0x03) << 8 | int(raw_bytes[1])
        set_point = float(raw_set_point) * 0.1

        # 10 bit field
        raw_heat_start = int(raw_bytes[3] & 0x0F) << 6 | int(raw_bytes[2] & 0xFC) >> 2
        heat_start = float(raw_heat_start) * 0.1

        seconds = (
            (int(raw_bytes[5] & 0x1F) << 12)
            | (int(raw_bytes[4]) << 4)
            | (int(raw_bytes[3] & 0xF0) >> 4)
        )

        # 11 bit field
        raw_core = int(raw_bytes[6]) << 3 | int(raw_bytes[5] & 0xE0) >> 5
        estimated_core = (float(raw_core) * 0.1) - 20.0
        return PredictionStatus(
            mode, prediction_type, state, set_point, heat_start, seconds, estimated_core
        )


class CptProbeStatus:
    """Data from the CPT thermometer."""

    def __init__(self, advertisting_data: bytes) -> None:
        """Initialise from the raw Probe Status Data data."""
        if len(advertisting_data) < 20:
            raise ValueError("Invalid advertising data")

        # log_range = advertisting_data[0:8]
        raw_temp_data_bytes = advertisting_data[8:21]
        mode_colour_and_id = advertisting_data[21]
        battery_status_and_virtual_sensors = advertisting_data[22]
        prediction_status = advertisting_data[23:30]
        # food_safe_data = advertisting_data[30:40]
        # food_safe_status = advertisting_data[40:44]

        self.prediction_status = PredictionStatus.from_raw_data(prediction_status)
        self.raw_temperatures: ProbeTemperatures = ProbeTemperatures.from_raw_data(
            raw_temp_data_bytes
        )
        self.mode = Mode.from_raw_data(mode_colour_and_id)
        self.colour = Mode.from_raw_data(mode_colour_and_id)
        self.id = CptProbeStatus._get_probe_id(mode_colour_and_id)
        self.battery_status = BatteryStatus.from_raw_data(
            battery_status_and_virtual_sensors
        )
        self.virtual_sensors: VirtualSensors = VirtualSensors.from_raw_data(
            battery_status_and_virtual_sensors, self.raw_temperatures.temperatures
        )

    def __str__(self) -> str:
        """Return a string representation of the thermometer state."""
        summary = f"Raw Temperatures: {self.raw_temperatures}\n"
        summary += f"Mode: {self.mode.name}\n"
        summary += f"Prediction State: {self.prediction_status.state.name}\n"
        summary += f"Prediction Mode: {self.prediction_status.mode.name}\n"
        summary += f"Prediction Type: {self.prediction_status.prediction_type.name}\n"
        summary += f"Set point temp: {self.prediction_status.prediction_set_point_temperature}\n"
        summary += f"Heat start temp: {self.prediction_status.heat_start_temperature}\n"
        summary += f"Estimated Core: {self.prediction_status.estimated_core_temp}\n"
        summary += (
            f"Seconds remaining: {self.prediction_status.prediction_value_seconds}\n"
        )
        if self.prediction_status.pecentage_to_removal is not None:
            summary += f"Percentage to removal: {self.prediction_status.pecentage_to_removal:.2f}\n"
        else:
            summary += "Percentage to removal: N/A\n"
        return summary

    @staticmethod
    def _get_probe_id(mode_colour_and_id: int) -> int:
        ID_MASK = 0x7
        ID_SHIFT = 5
        return (mode_colour_and_id >> ID_SHIFT) & ID_MASK


class CPTConnectionManager:
    """Manages communication with the CPT probe."""

    def _get_is_subscribed(self):
        return self._maybe_client is not None and self._maybe_client.is_connected

    is_subscribed_to_notifications = property(_get_is_subscribed)

    def __init__(self) -> None:
        """Construct a CPTConnectionManager."""
        self._maybe_client: None | BleakClient = None
        self.is_currently_subscribing = False

    async def maybe_subscribe_to_notifications(
        self,
        device_to_subscribe_to: BLEDevice,
        callback: Callable[[CptProbeStatus], None],
    ):
        """Subscribe to notifications for a device if not already subscribed."""
        if self.is_subscribed_to_notifications or self.is_currently_subscribing:
            return
        self.is_currently_subscribing = True
        self._maybe_client = BleakClient(device_to_subscribe_to)
        await self._maybe_client.connect()

        def notification_callback(sender: BleakGATTCharacteristic, data: bytearray):
            probe_status = CptProbeStatus(data)
            callback(probe_status)

        await self._maybe_client.start_notify(
            PROBE_STATUS_CHARACTERISTIC, notification_callback
        )

        self.is_currently_subscribing = False

    def parse_raw_cpt_advertisement(
        self, advertisement: AdvertisementData
    ) -> CptAdvertisement:
        """Extract the CPT advertisement body from a raw advertisement."""
        raw_advertisement_data = advertisement.manufacturer_data.get(
            COMBUSTION_MANUFACTURER_ID
        )
        if raw_advertisement_data is None:
            raise (
                ValueError(
                    f"Manufacturer data for {COMBUSTION_MANUFACTURER_ID} not present in advertisement"
                )
            )
        parsed = CptAdvertisement(raw_advertisement_data)
        return parsed

    def maybe_disconnect_from_client(self):
        """Disconnect the bluetooth client if active."""
        if self._maybe_client is not None and self._maybe_client.is_connected:
            self._maybe_client.disconnect()
