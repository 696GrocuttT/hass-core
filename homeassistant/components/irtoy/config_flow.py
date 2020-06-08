import logging
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant import config_entries, core, exceptions
from homeassistant.const import CONF_FILENAME, CONF_NAME
from .const import DOMAIN


_LOGGER = logging.getLogger(__name__)


# TODO adjust the data schema to the data that you need
DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default="IRToy"): str,
        vol.Required(CONF_FILENAME, default="/dev/ttyACM0"): str,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                cv.isdevice(user_input[CONF_FILENAME])
                return self.async_create_entry(
                    title=user_input[CONF_NAME], data=user_input
                )
            except vol.error.Invalid:
                errors["base"] = "no_dev_found"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )
