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


DEVICES = {}
_LOGGER = logging.getLogger(__name__)
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
        # Create the device representation in the UI
        device_registry = await dr.async_get_registry(hass)
        device = device_registry.async_get_or_create(
            config_entry_id = entry.entry_id,
            identifiers     = {(DOMAIN, port)},
            manufacturer    = "Sony",
            name            = entry.title,
            model           = "AV reciever",
        )
        # Connect up the actual interface
        amp = AmpCtrl(False, port)
        # Register the device in our local dict
        DEVICES[port] = amp
        _LOGGER.debug("Created device " + port)
        
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "media_player")        
    )
    return ok


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    ok   = await hass.config_entries.async_forward_entry_unload(entry, "media_player")
    port = entry.data[CONF_FILENAME]
    ok   = ok and port in DEVICES
    if ok:
        device = DEVICES[port]
        del DEVICES[port]
        device.close()
        _LOGGER.debug("Removed device " + port)
    return ok


def valid_type(value: Any) -> str:
    strVal = cv.string(value)
    if not strVal in map(lambda x: str(x), knownCommands):
        raise vol.Invalid("invalid type")
    return strVal


async def async_get_amp(hass: HomeAssistant, device_id: str):
    device_registry = await dr.async_get_registry(hass)
    device = device_registry.async_get(device_id)
    amp = None
    if device:
        for identifier in device.identifiers:
            if identifier[0] == DOMAIN:
                port = identifier[1]
                amp  = DEVICES[port]
                break
    return amp


def get_amp(port):
    return DEVICES[port]
