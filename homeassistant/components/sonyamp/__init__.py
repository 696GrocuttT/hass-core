"""The irtoy integration."""

import asyncio
import queue
import logging
import voluptuous                              as vol
import homeassistant.helpers.config_validation as cv
from typing                       import Any
from homeassistant.config_entries import ConfigEntry
from homeassistant.core           import HomeAssistant, callback
from homeassistant.const          import CONF_DEVICE_ID, CONF_FILENAME, CONF_NAME, EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers        import device_registry as dr
from homeassistant.loader         import bind_hass
from .const                       import DOMAIN
from .ampCtrl                     import AmpCtrl


DEVICES   = {}
PLATFORMS = ["media_player", "switch"]
_LOGGER   = logging.getLogger(__name__)
CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.Schema({vol.Required(CONF_FILENAME): cv.isdevice})},
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: dict):
    # Handle starting and stopping of home assistant
    def cleanup_sonyamp(event):
        global DEVICES
        for device in DEVICES:
            DEVICES[device].close()
        DEVICES = {}

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, cleanup_sonyamp)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    port = entry.data[CONF_FILENAME]
    ok = not port in DEVICES
    if ok:
        # Connect up the actual interface
        amp = AmpCtrl(False, port)
        # Register the device in our local dict
        DEVICES[port] = amp
        _LOGGER.debug("Created device " + port)
        
    for component in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component)
        )        
    return ok


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in PLATFORMS
            ]
        )
    )
    port = entry.data[CONF_FILENAME]
    ok   = ok and port in DEVICES
    if ok:
        device = DEVICES[port]
        del DEVICES[port]
        device.close()
        _LOGGER.debug("Removed device " + port)
    return ok


def get_amp(port):
    return DEVICES[port]


def get_device_info(port, zone):
    return {
        "name":         "Sony STR-DA3500ES (zone %d)" % zone,
        "identifiers":  {(DOMAIN, port + "_" + str(zone))},
        "model":        "STR-DA3500ES",
        "manufacturer": "Sony",
    }