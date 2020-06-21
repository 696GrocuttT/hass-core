import logging
import voluptuous                              as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.const import (
    CONF_FILENAME
)
from homeassistant.components.switch import SwitchEntity, DEVICE_CLASS_SWITCH
from .const                           import DOMAIN, CONF_ZONES
from .                                import get_amp, get_device_info
from .ampCtrl                         import *




_LOGGER = logging.getLogger(__name__)



async def async_setup_entry(hass, config_entry, async_add_entities):
    port    = config_entry.data[CONF_FILENAME]
    amp     = get_amp(port)
    devInfo = get_device_info(port, 0)    
    devices = [SpeakerSwitch(amp, devInfo, 0, True),
               SpeakerSwitch(amp, devInfo, 0, False),
               NightModeSwitch(amp, devInfo, 0)]
    async_add_entities(devices, True)
    


class SpeakerSwitch(SwitchEntity):
    def __init__(self, ampCtrl, devInfo, zone, isSpkA):
        self.ampCtrl   = ampCtrl
        self.devInfo   = devInfo
        self.uniqueId  = "speaker_" + ampCtrl.port + "_" + str(zone) + "_" + str(isSpkA)
        self.zone      = zone
        self.isSpkA    = isSpkA
        self.isOn      = False
        
        # Setup the comms with the amp
        pollingCmds = [AmpCmd(PDC_VIRTUAL, SPK_A_STATUS if isSpkA else SPK_B_STATUS)]
        self.ampCtrl.addListener(zone, pollingCmds, lambda x: self.statusListener(x))


    def statusListener(self, cmd):
        unknown = False
        if cmd.pdc == PDC_VIRTUAL_RESPONCE:
            if cmd.cmd == SPK_A_STATUS if self.isSpkA else SPK_B_STATUS:
                _LOGGER.info("Spk status: " + str(cmd)) 
                self.isOn = cmd.value[0] != 0
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
        return self.isOn


    @property
    def unique_id(self):
        """Return the device unique id."""
        return self.uniqueId


    @property
    def device_info(self):
        return self.devInfo

        
    def turn_on(self):
        self.ampCtrl.transmitCmd(AmpCmd(PDC_VIRTUAL, SPK_A if self.isSpkA else SPK_B, [1]))

       
    def turn_off(self):
        self.ampCtrl.transmitCmd(AmpCmd(PDC_VIRTUAL, SPK_A if self.isSpkA else SPK_B, [0]))


    @property
    def device_class(self):
        return DEVICE_CLASS_SWITCH



class NightModeSwitch(SwitchEntity):
    def __init__(self, ampCtrl, devInfo, zone):
        self.ampCtrl   = ampCtrl
        self.devInfo   = devInfo
        self.uniqueId  = "nightMode_" + ampCtrl.port + "_" + str(zone)
        self.zone      = zone
        self.pwrOn     = False
        self.isOn      = False
        
        # Setup the comms with the amp
        nightModeReadCmd       = AmpCmd.AmpMemReadCmd(NIGHT_MODE, 1)
        pollingCmds            = [AmpCmd(PDC_AMP, STATUS_REQ, zone=zone), nightModeReadCmd]
        self.pwrOffInvalidCmds = [nightModeReadCmd]
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
            elif cmd.cmd == MEM_READ and cmd.memAddr() == NIGHT_MODE:
                _LOGGER.info("Night mode: " + str(cmd)) 
                self.isOn = cmd.memData()[0] != 0
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
        return "Sony STR-DA3500ES (zone %d) night mode" % (self.zone) 


    @property
    def is_on(self):
        return self.isOn


    @property
    def unique_id(self):
        """Return the device unique id."""
        return self.uniqueId


    @property
    def device_info(self):
        return self.devInfo

        
    def turn_on(self):
        self.ampCtrl.transmitCmd(AmpCmd.AmpMemWriteCmd(NIGHT_MODE, [1]))

       
    def turn_off(self):
        self.ampCtrl.transmitCmd(AmpCmd.AmpMemWriteCmd(NIGHT_MODE, [0]))


    @property
    def device_class(self):
        return DEVICE_CLASS_SWITCH
