"""Provides device automations for IRToy Remote."""

import logging
import voluptuous                              as vol
import homeassistant.helpers.config_validation as cv
from typing              import List, Optional
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_TYPE
from homeassistant.core  import Context, HomeAssistant
from .                   import valid_type, async_get_ir_enc_dec
from .const              import DOMAIN
from .irEncDec           import  knownCommands


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
    config          = ACTION_SCHEMA(config)
    type            = config[CONF_TYPE]
    _LOGGER.debug('Performing action "' + type + '"')
    matchingCommand = next(filter(lambda x: str(x) == type, knownCommands))
    irEncDec        = await async_get_ir_enc_dec(hass, config[CONF_DEVICE_ID])
    irEncDec.transmitCmd(matchingCommand)
    
    
    

