"""Library to parse payloads from CPT thermometers."""
from enum import Enum


class ProductType(Enum):
    """The type of the product."""

    UNKNOWN = 0
    PREDICTIVE_PROBE = 1
    KITCHEN_TIMER = 2

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


class Colour(Enum):
    """The colour of the thermometer."""

    YELLOW = 0
    GREY = 1
    UNKNOWN = 2

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


class VirtualSensors:
    """The virtual sensors of the thermometer."""

    def __init__(self, core: float, surface: float, ambient: float) -> None:
        """Initialise with the core, surface and ambient temperatures."""
        self.core: float = core
        self.surface: float = surface
        self.ambient: float = ambient


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

    def __str__(self):
        """Return a string representation of the temperatures."""
        return f"t1={self.t1:.2f}, t2={self.t2:.2f}, t3={self.t3:.2f}, t4={self.t4:.2f}, t5={self.t5:.2f}, t6={self.t6:.2f}, t7={self.t7:.2f}, t8={self.t8:.2f}"


def parse_product_type(product_type: int) -> ProductType:
    """Parse the product type from the raw data."""
    if product_type == 0:
        return ProductType.UNKNOWN
    if product_type == 1:
        return ProductType.PREDICTIVE_PROBE
    if product_type == 2:
        return ProductType.KITCHEN_TIMER
    return ProductType.UNKNOWN


def get_serial(raw_serial) -> str:
    """Get the serial number from the raw data."""
    return raw_serial[::-1].hex().upper()


def parse_raw_temp_data(temp_bytes: bytes) -> list[float]:
    """Parse the raw temperature data."""
    temp_bytes = temp_bytes[::-1]  # need to reverse the bytes list
    raw_temps: list[float] = []

    # Add the temperatures in reverse order
    raw_temps.insert(0, ((temp_bytes[0] & 0xFF) << 5) | ((temp_bytes[1] & 0xF8) >> 3))
    raw_temps.insert(
        0,
        ((temp_bytes[1] & 0x07) << 10)
        | ((temp_bytes[2] & 0xFF) << 2)
        | ((temp_bytes[3] & 0xC0) >> 6),
    )
    raw_temps.insert(0, ((temp_bytes[3] & 0x3F) << 7) | ((temp_bytes[4] & 0xFE) >> 1))
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
    raw_temps.insert(0, ((temp_bytes[8] & 0x7F) << 6) | ((temp_bytes[9] & 0xFC) >> 2))
    raw_temps.insert(
        0,
        ((temp_bytes[9] & 0x03) << 11)
        | ((temp_bytes[10] & 0xFF) << 3)
        | ((temp_bytes[11] & 0xE0) >> 5),
    )
    raw_temps.insert(0, ((temp_bytes[11] & 0x1F) << 8) | (temp_bytes[12] & 0xFF))

    temperatures = [temp * 0.05 - 20.0 for temp in raw_temps]
    return temperatures


def parse_virtual_sensors(
    virtual_sensors: int, raw_temps: list[float]
) -> VirtualSensors:
    """Parse the virtual sensors from the raw data."""
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


def parse_colour(colour_id: int) -> Colour:
    """Parse the colour from the raw data."""
    if colour_id == 0:
        return Colour.YELLOW
    if colour_id == 1:
        return Colour.GREY
    return Colour.UNKNOWN


def parse_mode(mode: int) -> Mode:
    """Parse the mode from the raw data."""
    if mode == 0:
        return Mode.NORMAL
    if mode == 1:
        return Mode.INSTANT_READ
    if mode == 2:
        return Mode.RESERVED
    if mode == 3:
        return Mode.ERROR
    raise ValueError("Invalid mode")


def parse_battery_status(status_id: int) -> BatteryStatus:
    """Parse the battery status from the raw data."""
    if status_id == 0:
        return BatteryStatus.OK
    if status_id == 1:
        return BatteryStatus.LOW
    raise ValueError("Invalid battery status")


class CptAdvertisingData:
    """Data advertised from the CPT thermometer."""

    def __init__(self, advertisting_data: bytes) -> None:
        """Initialise from the raw advertising data."""
        if len(advertisting_data) < 20:
            raise ValueError("Invalid advertising data")

        raw_product_type = advertisting_data[0]
        raw_serial_number = advertisting_data[1:5]
        raw_temp_data_bytes = advertisting_data[5:18]
        mode_colour_and_id = advertisting_data[18]
        battery_status_virtual_sensors = advertisting_data[19]

        self.product_type: ProductType = parse_product_type(raw_product_type)
        self.serial: str = get_serial(raw_serial_number)

        raw_temps = parse_raw_temp_data(raw_temp_data_bytes)
        self.raw_temperatures: ProbeTemperatures = ProbeTemperatures(raw_temps)

        MODE_MASK = 0x3
        mode_id = mode_colour_and_id & MODE_MASK
        self.mode: Mode = parse_mode(mode_id)

        COLOUR_MASK = 0x7
        COLOUR_SHIFT = 2
        color_id = (mode_colour_and_id >> COLOUR_SHIFT) & COLOUR_MASK
        self.colour: Colour = parse_colour(color_id)

        ID_MASK = 0x7
        ID_SHIFT = 5
        self.probe_id: int = (mode_colour_and_id >> ID_SHIFT) & ID_MASK

        battery_status = (battery_status_virtual_sensors >> 7) & 0x01

        self.batery_status: BatteryStatus = parse_battery_status(battery_status)

        virtual_sensors = battery_status_virtual_sensors >> 1
        self.virtual_sensors: VirtualSensors = parse_virtual_sensors(
            virtual_sensors, raw_temps
        )

    def __str__(self) -> str:
        """Return a string representation of the thermoeter state."""
        summary = f"Product Type: {self.product_type.name}\n"
        summary += f"Serial Number: {self.serial}\n"
        summary += f"Raw Temperatures: {self.raw_temperatures}\n"
        summary += f"Mode: {self.mode.name}\n"
        summary += f"Colour: {self.colour.name}\n"
        summary += f"Probe ID: {self.probe_id}\n"
        summary += f"Battery Status: {self.batery_status.name}\n"
        return summary

    def get_device_title(self) -> str:
        """Return a nice title for the device."""
        return f"{self.product_type} {self.serial}"


class CPTDevice:
    """A CPT device."""

    def __init__(self, serial: str, product_type: ProductType, colour: Colour) -> None:
        """Initialise the device."""
        self.serial: str = serial
        self.product_type: ProductType = product_type
        self.colour: Colour = colour


class CptAdvertisement:
    """A CPT advertisement."""

    def __init__(self, advertising_data: CptAdvertisingData, mac_addresss: str) -> None:
        """Initialise the advertisement."""
        self.advertising_data: CptAdvertisingData = advertising_data
        self.mac_address: str = mac_addresss
