"""Defines a config flow for the Combustion Inc integration."""

import asyncio
import dataclasses
import logging
from typing import Any

from cpt_python import CptAdvertisement, CPTDevice, ProductType
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothScanningMode,
    BluetoothServiceInfo,
    BluetoothServiceInfoBleak,
    async_process_advertisements,
)
from homeassistant.const import (
    ATTR_MANUFACTURER,
    ATTR_MODEL,
    ATTR_NAME,
    ATTR_SERIAL_NUMBER,
    CONF_DEVICE,
    CONF_MAC,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import (
    COMBUSTION_INC,
    COMBUSTION_MANUFACTURER_ID,
    CONF_INCLUDE_PHYSICAL_SENSORS,
    CONF_INCLUDE_VIRTUAL_SENSORS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass
class Discovery:
    """A discovered bluetooth device."""

    title: str
    discovery_info: BluetoothServiceInfo
    device: CPTDevice


class CombustionIncConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for the Combustion Inc integration."""

    # The schema version of the entries that it creates
    # Home Assistant will call this migrate method if the version changes
    VERSION = 1
    MINOR_VERSION = 1
    device_search_task: asyncio.Task | None = None
    SEARCH_DURATION_SECONDS = 2

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_device: Discovery | None = None
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, Discovery] = {}

    def _handle_manual_device_discovery(
        self, service_info: BluetoothServiceInfoBleak
    ) -> bool:
        if service_info.manufacturer_id == COMBUSTION_MANUFACTURER_ID:
            if COMBUSTION_MANUFACTURER_ID not in service_info.manufacturer_data:
                return False
            manufacturer_data = service_info.manufacturer_data.get(
                COMBUSTION_MANUFACTURER_ID
            )
            if manufacturer_data is None:
                return False
            advertising_data: CptAdvertisement = CptAdvertisement(manufacturer_data)
            if advertising_data.device.product_type != ProductType.PREDICTIVE_PROBE:
                return False
            serial = advertising_data.device.serial
            current_serials = self._async_current_ids()
            if serial in current_serials or serial in self._discovered_devices:
                return False
            self._discovered_devices[serial] = Discovery(
                title=_get_device_title(advertising_data.device),
                discovery_info=service_info,
                device=advertising_data.device,
            )
        return False

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfo
    ) -> FlowResult:
        """Thermometer has been discovered, we'll set it up."""
        manufacturer_data = discovery_info.manufacturer_data.get(
            COMBUSTION_MANUFACTURER_ID
        )
        if manufacturer_data is None:
            raise ValueError("Invalid manufacturer data")
        advertising_data: CptAdvertisement = CptAdvertisement(manufacturer_data)
        if advertising_data.device.product_type != ProductType.PREDICTIVE_PROBE:
            return self.async_abort(
                reason=f"Product type {advertising_data.device.product_type} not supported."
            )

        await self.async_set_unique_id(advertising_data.device.serial)
        self._abort_if_unique_id_configured()
        self._discovered_devices[
            advertising_data.device.serial
        ] = advertising_data.device
        self._discovered_device = Discovery(
            title=_get_device_title(advertising_data.device),
            discovery_info=discovery_info,
            device=advertising_data.device,
        )
        self.context["title_placeholders"] = {
            "device_type": str(advertising_data.device.product_type),
            "device_serial": str(advertising_data.device.serial),
        }

        return await self.async_step_bluetooth_confirm()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """User has added the integration."""
        if not self.device_search_task:
            # Start a task to search for CPT devices
            self.device_search_task = self.hass.async_create_task(
                target=async_process_advertisements(
                    hass=self.hass,
                    callback=self._handle_manual_device_discovery,
                    match_dict={
                        "manufacturer_id": COMBUSTION_MANUFACTURER_ID,
                        "connectable": False,
                    },
                    mode=BluetoothScanningMode.PASSIVE,
                    timeout=self.SEARCH_DURATION_SECONDS,
                )
            )
        if not self.device_search_task.done():
            return self.async_show_progress(
                progress_action="searching",
                progress_task=self.device_search_task,
                description_placeholders={
                    "search_duration": str(self.SEARCH_DURATION_SECONDS)
                },
            )
        if self.device_search_task.exception():
            pass
        if len(self._discovered_devices.keys()) == 0:
            return self.async_show_progress_done(next_step_id="no_discovered_devices")
        if len(self._discovered_devices.keys()) == 1:
            # if we only discover one device, go straight to setting it up
            self._discovered_device = list(self._discovered_devices.values())[0]
            await self.async_set_unique_id(
                self._discovered_device.device.serial, raise_on_progress=False
            )
            return self.async_show_progress_done(next_step_id="bluetooth_confirm")
        return self.async_show_progress_done(next_step_id="select_discovered_devices")

    async def async_step_select_discovered_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Shown when we have discovered multiple devices and need the user to choose one."""
        if user_input is not None:
            selected_serial = user_input[CONF_DEVICE]
            discovery_for_serial = self._discovered_devices.get(selected_serial)
            if discovery_for_serial is None:
                return self.async_abort(reason="unknown_error_setting_up")
            self._discovered_device = discovery_for_serial
            self.context["title_placeholders"] = {
                "device_type": str(discovery_for_serial.device.product_type),
                "device_serial": str(discovery_for_serial.device.serial),
            }
            await self.async_set_unique_id(selected_serial)
            return await self.async_step_bluetooth_confirm()

        titles = {
            address: discovery.title
            for (address, discovery) in self._discovered_devices.items()
        }
        return self.async_show_form(
            step_id="select_discovered_devices",
            data_schema=vol.Schema({vol.Required(CONF_DEVICE): vol.In(titles)}),
            description_placeholders={
                "plural_letter": "s" if len(self._discovered_devices) > 1 else "",
                "num_devices": str(len(self._discovered_devices)),
            },
        )

    async def async_step_no_discovered_devices(
        self, user_input: dict[str, Any]
    ) -> FlowResult:
        """Shown when we don't discover any devices."""
        return self.async_abort(reason="no_devices_found")

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """In this step the user must confirm the discovered device."""

        if user_input is None:
            if self._discovered_device is None:
                raise ValueError("No device discovered")
            options_schema = vol.Schema(
                {
                    vol.Required(
                        CONF_INCLUDE_PHYSICAL_SENSORS, default=True
                    ): cv.boolean,
                    vol.Required(
                        CONF_INCLUDE_VIRTUAL_SENSORS, default=True
                    ): cv.boolean,
                }
            )

            return self.async_show_form(
                step_id="bluetooth_confirm",
                data_schema=options_schema,
                description_placeholders={
                    "device_type": str(self._discovered_device.device.product_type),
                    "device_type_with_colour": _get_device_type_with_colour(
                        self._discovered_device.device
                    ),
                    "device_serial": self._discovered_device.device.serial,
                },
            )
        self._set_confirm_only()

        return await self._async_get_or_create_entry(user_input)

    async def _async_get_or_create_entry(
        self, user_input: dict[str, Any]
    ) -> FlowResult:
        if self._discovered_device is None:
            raise ValueError("No device discovered")
        data: dict[str, Any] = {}
        device = self._discovered_device.device
        data[ATTR_NAME] = _get_device_title(device)
        data[ATTR_SERIAL_NUMBER] = device.serial
        data[ATTR_MANUFACTURER] = COMBUSTION_INC
        data[ATTR_MODEL] = str(device.product_type)
        data[CONF_MAC] = self._discovered_device.discovery_info.address

        if entry_id := self.context.get("entry_id"):
            entry = self.hass.config_entries.async_get_entry(entry_id)
            assert entry is not None
            return self.async_update_reload_and_abort(entry, data=data)

        return self.async_create_entry(
            title=_get_device_title(self._discovered_device.device),
            description=_get_device_type_with_colour(self._discovered_device.device),
            data=data,
            options=user_input,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Options Flow Handler for CPT integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        options_schema = vol.Schema(
            {
                vol.Required(
                    CONF_INCLUDE_PHYSICAL_SENSORS,
                    default=self.config_entry.options.get(
                        CONF_INCLUDE_PHYSICAL_SENSORS, True
                    ),
                ): cv.boolean,
                vol.Required(
                    CONF_INCLUDE_VIRTUAL_SENSORS,
                    default=self.config_entry.options.get(
                        CONF_INCLUDE_VIRTUAL_SENSORS, True
                    ),
                ): cv.boolean,
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
        )


def _get_device_title(device: CPTDevice) -> str:
    return f"{device.product_type} {device.serial}"


def _get_device_type_with_colour(device: CPTDevice) -> str:
    if device.product_type == ProductType.PREDICTIVE_PROBE:
        return f"{device.colour} {device.product_type}"
    if device.product_type == ProductType.KITCHEN_TIMER:
        return str(device.product_type)
    return "Unknown Device"
