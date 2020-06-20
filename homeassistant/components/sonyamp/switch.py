import logging
import voluptuous                              as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.const import (
    CONF_FILENAME
)
from homeassistant.components.switch import SwitchEntity, DEVICE_CLASS_SWITCH
from .const                           import DOMAIN, CONF_ZONES
from .                                import get_amp
from .ampCtrl                         import *




_LOGGER = logging.getLogger(__name__)



async def async_setup_entry(hass, config_entry, async_add_entities):
    amp     = get_amp(config_entry.data[CONF_FILENAME])
    devices = [SpeakerSwitch(amp, 0, True),
               SpeakerSwitch(amp, 0, False)]
    async_add_entities(devices, True)
    


class SpeakerSwitch(SwitchEntity):
    def __init__(self, ampCtrl, zone, isSpkA):
        self.ampCtrl   = ampCtrl
        self.uniqueId  = ampCtrl.port + "_" + str(zone) + "_" + str(isSpkA)
        self.zone      = zone
        self.isSpkA    = isSpkA
        self.pwrOn     = False
        self.isOn      = False
        
        # Setup the comms with the amp
        volStatusCmd           = AmpCmd(PDC_AMP, VOL_STATUS_REQ, zone=zone)
        pollingCmds            = [AmpCmd(PDC_AMP, STATUS_REQ, zone=zone),
                                  volStatusCmd]
        self.pwrOffInvalidCmds = [volStatusCmd]
        self.updateCmdMasking()
        self.ampCtrl.addListener(zone, pollingCmds, lambda x: self.statusListener(x))


    def updateCmdMasking(self):
        for cmd in self.pwrOffInvalidCmds:
            cmd.okToSend = self.pwrOn
            
        
    def statusListener(self, cmd):
        unknown = False
        if cmd.pdc == PDC_AMP_RESPONCE:
            if cmd.cmd == STATUS_REQ:
                _LOGGER.info("Amp status: " + str(cmd)) 
                self.pwrOn  = (cmd.value[2] & 1) != 0
                self.updateCmdMasking()
            else:
                unknown = True
        else:
            unknown = True
        
        if unknown:
            _LOGGER.warn("Unknown command recieved: " + str(cmd)) 
        if self.hass:
            self.schedule_update_ha_state()


    @property
    def should_poll(self):
        """No polling needed."""
        return False


    def update(self):
        # No polling required
        pass


    async def async_update(self):
        pass


    @property
    def name(self):
        """Return the name of the device."""
        return "Sony STR-DA3500ES (zone %d) speaker %s" % (self.zone, "A" if self.isSpkA else "B") 


    @property
    def is_on(self):
        """Return true if switch is on."""
        return self.isOn


    @property
    def unique_id(self):
        """Return the device unique id."""
        return self.uniqueId


    @property
    def device_info(self):
        return {
            "name":         "Sony STR-DA3500ES (zone %d)" % self.zone,
            "identifiers":  {(DOMAIN, self.ampCtrl.port + "_" + str(self.zone))},
            "model":        "STR-DA3500ES",
            "manufacturer": "Sony",
        }

        
    def turn_on(self):
        pass
        self.isOn = True
        #self.ampCtrl.transmitCmd(AmpCmd(PDC_AMP, PWR_CTRL_CMD, [1], [OK_RESP], self.zone))

       
    def turn_off(self):
        pass
        self.isOn = False
        #self.ampCtrl.transmitCmd(AmpCmd(PDC_AMP, PWR_CTRL_CMD, [0], [OK_RESP], self.zone))


    @property
    def device_class(self):
        return DEVICE_CLASS_SWITCH
