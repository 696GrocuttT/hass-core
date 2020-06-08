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
from .const                       import DOMAIN, CONF_IRTOY_EVENT, CONF_IRTOY_EVENT_CMD
from .irEncDec                    import IrEncDec, knownCommands


DEVICES = {}
_LOGGER = logging.getLogger(__name__)
CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.Schema({vol.Required(CONF_FILENAME): cv.isdevice})},
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: dict):
    # Handle starting and stopping of home assistant
    def cleanup_irtoy(event):
        global DEVICES
        for device in DEVICES:
            DEVICES[device].close()
        DEVICES = {}

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, cleanup_irtoy)
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
            manufacturer    = "Dangerous prototypes",
            name            = entry.title,
            model           = "USB Infrared Toy",
        )
        # Connect up the actual interface
        def recievedCmd(cmd):
            hass.bus.async_fire(CONF_IRTOY_EVENT, {CONF_IRTOY_EVENT_CMD: str(cmd), 
                                                   CONF_DEVICE_ID:       device.id})
        irEncDec = IrEncDec(port, recievedCmd)
        # Register the device in our local dict
        DEVICES[port] = irEncDec
        _LOGGER.debug("Created device " + port)
    return ok


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    port = entry.data[CONF_FILENAME]
    ok = port in DEVICES
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


async def async_get_ir_enc_dec(hass: HomeAssistant, device_id: str):
    device_registry = await dr.async_get_registry(hass)
    device = device_registry.async_get(device_id)
    encDec = None
    if device:
        for identifier in device.identifiers:
            if identifier[0] == DOMAIN:
                port = identifier[1]
                encDec = DEVICES[port]
                break
    return encDec
