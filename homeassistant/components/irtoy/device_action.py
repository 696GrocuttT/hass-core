"""Provides device automations for IRToy Remote."""

import logging
from typing import List, Optional

import voluptuous as vol

from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_TYPE,
)
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import entity_registry
import homeassistant.helpers.config_validation as cv
from .                                           import valid_type
from .const import DOMAIN
from .irEncDec                    import  knownCommands





_LOGGER       = logging.getLogger(__name__)
ACTION_SCHEMA = cv.DEVICE_ACTION_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): valid_type
    }
)


async def async_get_actions(hass: HomeAssistant, device_id: str) -> List[dict]:
    def create_action(command):
        return {
            CONF_DEVICE_ID: device_id,
            CONF_DOMAIN:    DOMAIN,
            CONF_TYPE:      str(command)
        }

    return map(create_action, knownCommands)


async def async_call_action_from_config(
    hass: HomeAssistant, config: dict, variables: dict, context: Optional[Context]
) -> None:
    type = config[CONF_TYPE]
    _LOGGER.debug('Performing action "' + type + '"')
    
    config = ACTION_SCHEMA(config)
    print(config)
    print(variables)
    print(context)
    

