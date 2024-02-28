"""Defines a config flow for the CPT integration."""

import dataclasses
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.bluetooth import BluetoothServiceInfo
from homeassistant.const import (
    ATTR_MANUFACTURER,
    ATTR_MODEL,
    ATTR_NAME,
    ATTR_SERIAL_NUMBER,
)
from homeassistant.data_entry_flow import FlowResult

from .const import COMBUSTION_INC, COMBUSTION_MANUFACTURER_ID, DOMAIN
from .cpt_lib import CptAdvertisingData, CPTDevice, ProductType

_LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass
class Discovery:
    """A discovered bluetooth device."""

    title: str
    discovery_info: BluetoothServiceInfo
    device: CPTDevice


def _get_device_title(device: CPTDevice) -> str:
    return f"{device.product_type} {device.serial}"


def _get_device_type_with_colour(device: CPTDevice) -> str:
    if device.product_type == ProductType.PREDICTIVE_PROBE:
        return f"{device.colour} {device.product_type}"
    if device.product_type == ProductType.KITCHEN_TIMER:
        return str(device.product_type)
    return "Unknown Device"


class CombustionIncConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Example config flow."""

    # The schema version of the entries that it creates
    # Home Assistant will call your migrate method if the version changes
    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_device: CPTDevice | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfo
    ) -> FlowResult:
        """Handle the bluetooth discovery step."""
        manufacturer_data = discovery_info.manufacturer_data.get(
            COMBUSTION_MANUFACTURER_ID
        )
        mac_address = discovery_info.address
        if manufacturer_data is None:
            raise ValueError("Invalid manufacturer data")
        advertising_data: CptAdvertisingData = CptAdvertisingData(manufacturer_data)
        if advertising_data.product_type != ProductType.PREDICTIVE_PROBE:
            return self.async_abort(reason="not_supported")

        await self.async_set_unique_id(mac_address)
        self._abort_if_unique_id_configured()

        device = CPTDevice(
            advertising_data.serial,
            advertising_data.product_type,
            advertising_data.colour,
        )
        self._discovered_device = device

        self.context["title_placeholders"] = {
            "device_type": str(self._discovered_device.product_type),
            "device_serial": str(self._discovered_device.serial),
        }

        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """In this step the user must confirm the discovered device."""

        if user_input is None:
            data_schema = {
                vol.Required("enable_raw_sensors", default=True): bool,
                vol.Required("enable_virtual_sensors", default=True): bool,
            }
            if self._discovered_device is None:
                raise ValueError("No device discovered")

            return self.async_show_form(
                step_id="bluetooth_confirm",
                data_schema=vol.Schema(data_schema),
                description_placeholders={
                    "device_type": str(self._discovered_device.product_type),
                    "device_type_with_colour": _get_device_type_with_colour(
                        self._discovered_device
                    ),
                    "device_serial": self._discovered_device.serial,
                },
            )

        self._set_confirm_only()
        return self._async_get_or_create_entry()

    def _async_get_or_create_entry(self) -> FlowResult:
        if self._discovered_device is None:
            raise ValueError("No device discovered")
        data: dict[str, Any] = {}
        data[ATTR_NAME] = _get_device_title(self._discovered_device)
        data[ATTR_SERIAL_NUMBER] = self._discovered_device.serial
        data[ATTR_MANUFACTURER] = COMBUSTION_INC
        data[ATTR_MODEL] = str(self._discovered_device.product_type)

        if entry_id := self.context.get("entry_id"):
            entry = self.hass.config_entries.async_get_entry(entry_id)
            assert entry is not None
            return self.async_update_reload_and_abort(entry, data=data)

        return self.async_create_entry(
            title=_get_device_title(self._discovered_device),
            description=_get_device_type_with_colour(self._discovered_device),
            data=data,
        )
