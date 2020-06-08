import logging
import voluptuous as vol
from .const import CONF_EVENTS
from homeassistant.components.irtoy.IrMan import IrMan
import queue


from homeassistant.const import EVENT_HOMEASSISTANT_START, EVENT_HOMEASSISTANT_STOP
from homeassistant.components.binary_sensor import PLATFORM_SCHEMA, BinarySensorEntity
from homeassistant.const import CONF_FILENAME
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)
_rxCmdQueue = queue.Queue()


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_FILENAME): cv.isdevice,
        vol.Required(CONF_EVENTS): vol.Schema({cv.string: cv.string}),
    }
)


def setup_platform(hass, config, add_entities, discovery_info=None):
    def cleanup_irtoy(event):
        global _irToy
        _irToy.close()

    def prepare_irtoy(event):
        global _irToy
        global _rxCmdQueue
        _irToy = IrMan(config.get(CONF_FILENAME), _rxCmdQueue)
        hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, cleanup_irtoy)

    hass.bus.listen_once(EVENT_HOMEASSISTANT_START, prepare_irtoy)

    binary_sensors = []
    events = config.get(CONF_EVENTS)
    for name, ir_cmd_str in events.items():
        binary_sensors.append(IrManBinarySensor(name, ir_cmd_str))
    add_entities(binary_sensors, True)


class IrManBinarySensor(BinarySensorEntity):
    def __init__(self, name, ir_cmd_str):
        self._name = name or DEVICE_DEFAULT_NAME
        self._ir_cmd_str = ir_cmd_str
        self._state = None

    @property
    def should_poll(self):
        """No polling needed."""
        return True

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def is_on(self):
        """Return the state of the entity."""
        return self._state

    def update(self):
        """Update the GPIO state."""
        if not _rxCmdQueue.empty():
            event = _rxCmdQueue.get()
            self._state = True
        else:
            self._state = False
