"""Provides device automations for irtoy."""

import logging
import voluptuous                                as vol
import homeassistant.components.automation.event as event
from homeassistant.components.device_automation  import TRIGGER_BASE_SCHEMA
from homeassistant.const                         import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE, CONF_DEVICE
from homeassistant.core                          import HomeAssistant, callback
from homeassistant.helpers                       import config_validation as cv
from typing                                      import List
from .const                                      import DOMAIN, CONF_IRTOY_EVENT, CONF_IRTOY_EVENT_CMD
from .irEncDec                                   import knownCommands
from .                                           import valid_type


_LOGGER        = logging.getLogger(__name__)
TRIGGER_SCHEMA = TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): valid_type
    }
)


async def async_get_triggers(hass: HomeAssistant, device_id: str) -> List[dict]:
    def create_trigger(command):
        return {
            CONF_PLATFORM:  CONF_DEVICE,
            CONF_DEVICE_ID: device_id,
            CONF_DOMAIN:    DOMAIN,
            CONF_TYPE:      str(command)
        }

    return map(create_trigger, knownCommands)


async def async_attach_trigger(hass, config, action, automation_info):
    type = config[CONF_TYPE]
    _LOGGER.debug('Adding trigger "' + type + '" to "' + automation_info["name"] + '"')
    event_config = event.TRIGGER_SCHEMA({
        event.CONF_PLATFORM:   "event",
        event.CONF_EVENT_TYPE: CONF_IRTOY_EVENT,
        event.CONF_EVENT_DATA: {CONF_IRTOY_EVENT_CMD: type,
                                CONF_DEVICE_ID:       config[CONF_DEVICE_ID]}
    })

    return await event.async_attach_trigger(
        hass, event_config, action, automation_info, platform_type=CONF_DEVICE
    )

