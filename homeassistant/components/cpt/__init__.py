"""The CPT integration."""

import logging

from homeassistant.components.bluetooth import async_rediscover_address
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_MAC, Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import CPTBluetoothCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Forward any setups to the sensor platform."""
    hass.data[DOMAIN] = {}
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Disconnect bluetooth
    coordinator: CPTBluetoothCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.maybe_disconnect_bt_client()
    # Unload the platforms
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    # Mark the mac address as rediscoverable
    async_rediscover_address(hass, address=entry.data[CONF_MAC])
    _LOGGER.info("Unload result: %s", unload_ok)
    return unload_ok
