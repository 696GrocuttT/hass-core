
from collections import namedtuple
import logging

import voluptuous as vol

from homeassistant.components.media_player import PLATFORM_SCHEMA, MediaPlayerEntity
from homeassistant.components.media_player.const import (
    MEDIA_TYPE_CHANNEL,
    MEDIA_TYPE_MUSIC,
    SUPPORT_NEXT_TRACK,
    SUPPORT_PAUSE,
    SUPPORT_PLAY,
    SUPPORT_PLAY_MEDIA,
    SUPPORT_PREVIOUS_TRACK,
    SUPPORT_SELECT_SOUND_MODE,
    SUPPORT_SELECT_SOURCE,
    SUPPORT_TURN_OFF,
    SUPPORT_TURN_ON,
    SUPPORT_VOLUME_MUTE,
    SUPPORT_VOLUME_SET,
    SUPPORT_VOLUME_STEP,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_HOST,
    CONF_NAME,
    CONF_TIMEOUT,
    CONF_FILENAME,
    CONF_ZONE,
    ENTITY_MATCH_ALL,
    ENTITY_MATCH_NONE,
    STATE_OFF,
    STATE_ON,
    STATE_PAUSED,
    STATE_PLAYING,
)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, CONF_ZONES
from . import get_amp
from .ampCtrl import *

_LOGGER = logging.getLogger(__name__)

ATTR_SOUND_MODE_RAW = "sound_mode_raw"

CONF_INVALID_ZONES_ERR = "Invalid Zone (expected Zone2 or Zone3)"
CONF_SHOW_ALL_SOURCES = "show_all_sources"
CONF_VALID_ZONES = ["Zone2", "Zone3"]


DEFAULT_SHOW_SOURCES = False
DEFAULT_TIMEOUT = 2



DENON_ZONE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ZONE): vol.In(CONF_VALID_ZONES, CONF_INVALID_ZONES_ERR),
        vol.Optional(CONF_NAME): cv.string,
    }
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_HOST): cv.string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_SHOW_ALL_SOURCES, default=DEFAULT_SHOW_SOURCES): cv.boolean,
        vol.Optional(CONF_ZONES): vol.All(cv.ensure_list, [DENON_ZONE_SCHEMA]),
        vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.positive_int,
    }
)



SOURCE_DETAILS = {
"Tuner":                 (INPUT_SEL_CMD_TUNER,    7), 
"CD":                    (INPUT_SEL_CMD_CD,       7), 
"MD":                    (INPUT_SEL_CMD_MD,       7), 
"TAPE":                  (INPUT_SEL_CMD_TAPE,     7), 
"Front AV":              (INPUT_SEL_CMD_FRONT_AV, 7),
"PVR":                   (INPUT_SEL_CMD_PVR,      7), 
"Apple TV (audio only)": (INPUT_SEL_CMD_APPLE_TV, 7), 
"TV":                    (INPUT_SEL_CMD_TV,       1), 
"BD (audio only)":       (INPUT_SEL_CMD_BD,       7), 
"5p1":                   (INPUT_SEL_CMD_5p1_IN,   1), 
"Apple TV (HDMI)":       (INPUT_SEL_CMD_ATV_HDMI, 1), 
"BD (HDMI)":             (INPUT_SEL_CMD_BD_HDMI,  1), 
}

SOUND_MODES = {
"Stereo":          SF_SEL_CMD_2CH_ST,
"Analogue direct": SF_SEL_CMD_A_DIRECT,
"AFD Auto":        SF_SEL_CMD_AFD_AUTO,
"E Surround":      SF_SEL_CMD_ESURROUND,
}



async def async_setup_entry(hass, config_entry, async_add_entities):
    devices = []
    amp     = get_amp(config_entry.data[CONF_FILENAME])
    for zone in range(config_entry.data[CONF_ZONES]):    
        devices.append(SonyDevice(amp, zone))
    async_add_entities(devices)



class SonyDevice(MediaPlayerEntity):
    def __init__(self, ampCtrl, zone):
        self.ampCtrl   = ampCtrl
        self.zone      = zone
        self.curState  = STATE_OFF
        self.mute      = False
        self.rawVolume = -32768 # Smallest 16bit number
        self.curSource = "Unknown"
        self.soundMode = "Unknown"
        
        # Create a structures for sources / sound fields etc
        self.sourceCmdDict  = {}
        self.sourceNameDict = {}
        for source in SOURCE_DETAILS:
            if SOURCE_DETAILS[source][1] & (1 << zone) != 0:
                value = SOURCE_DETAILS[source][0]
                self.sourceNameDict[value] = source
                self.sourceCmdDict[source] = value
        self.soundModeNameDict = {}
        for mode in SOUND_MODES:
            self.soundModeNameDict[SOUND_MODES[mode]] = mode
        
        # Setup the comms with the amp
        pollingCmds = [AmpCmd(PDC_AMP, STATUS_REQ,     zone=zone), 
                       AmpCmd(PDC_AMP, VOL_STATUS_REQ, zone=zone)]
        if zone == 0:
            pollingCmds.append(AmpCmd(PDC_SOUND_ADAPTOR, SF_STATUS_REQ_CMD))
        ampCtrl.addListener(zone, pollingCmds, lambda x: self.statusListener(x))
        
        
    def statusListener(self, cmd):
        unknown = False
        if cmd.pdc == PDC_AMP_RESPONCE:
            if cmd.cmd == STATUS_REQ:
                _LOGGER.info("Amp status: " + str(cmd)) 
                self.curState  = STATE_ON if (cmd.value[2] & 1) != 0 else STATE_OFF
                self.muted     = (cmd.value[2] & 2) != 0
                self.curSource = self.sourceNameDict.get(cmd.value[0],"Unknown")
            elif cmd.cmd == VOL_STATUS_REQ:
                _LOGGER.info("Amp vol status: " + str(cmd)) 
                value          = cmd.value[1] << 8 | cmd.value[2]
                value          = (value & 0x7fff) - (value & 0x8000) # sign extend
                self.rawVolume = value / 256.0
            else:
                unknown = True
        elif cmd.pdc == PDC_SOUND_ADAPTOR_RESPONCE:
            if cmd.cmd == SF_STATUS_REQ_CMD:
                _LOGGER.info("SF status: " + str(cmd))
                self.soundMode = self.soundModeNameDict.get(cmd.value[0],"Unknown")
            else:
                unknown = True
        else:
            unknown = True
        
        if unknown:
            _LOGGER.warn("Unknown command recieved: " + str(cmd)) 
        self.schedule_update_ha_state()


    async def async_added_to_hass(self):
        """Register signal handler."""
        self.async_on_remove(
            async_dispatcher_connect(self.hass, DOMAIN, self.signal_handler)
        )

    def signal_handler(self, data):
        """Handle domain-specific signal by calling appropriate method."""
        # entity_ids = data[ATTR_ENTITY_ID]

        # if entity_ids == ENTITY_MATCH_NONE:
            # return

        # if entity_ids == ENTITY_MATCH_ALL or self.entity_id in entity_ids:
            # params = {
                # key: value
                # for key, value in data.items()
                # if key not in ["entity_id", "method"]
            # }
            # getattr(self, data["method"])(**params)


    @property
    def should_poll(self):
        """No polling needed."""
        return False

    def update(self):
        # No polling required
        pass

    @property
    def name(self):
        """Return the name of the device."""
        return "Sony STR-DA3500ES (zone %d)" % self.zone

    @property
    def state(self):
        """Return the state of the device."""
        return self.curState

    @property
    def is_volume_muted(self):
        return self.muted

    @property
    def volume_level(self):
        """Volume level of the media player (0..1)."""
        scaledVol = (self.rawVolume + 92) / 92
        return min(1, max(0, scaledVol))

    @property
    def source(self):
        return self.curSource 

    @property
    def source_list(self):
        return [*self.sourceCmdDict]

    @property
    def sound_mode(self):
        return self.soundMode

    @property
    def sound_mode_list(self):
        return [*SOUND_MODES]

    @property
    def supported_features(self):
        features = SUPPORT_TURN_ON | SUPPORT_TURN_OFF | SUPPORT_SELECT_SOURCE 
        if self.zone == 0:
            features = features | SUPPORT_SELECT_SOUND_MODE | SUPPORT_VOLUME_MUTE | SUPPORT_VOLUME_SET
        return features

    @property
    def device_state_attributes(self):
        """Return device specific state attributes."""
        attributes = {}
        #if (
         #   self._sound_mode_raw is not None
          #  and self._sound_mode_support
          #  and self._power == "ON"
       # ):
        #    attributes[ATTR_SOUND_MODE_RAW] = self._sound_mode_raw
        return attributes

    # @property
    # def device_info(self):
        # """Return information about the device."""
        # print("get device info called")
        # return {
            # "name": "aoeu",
            # "identifiers": {(DOMAIN, self.name)},
            # "model": self.name,
            # "manufacturer": "Sony",
        # }

    def select_source(self, source):
        selValue = self.sourceCmdDict[source]
        self.ampCtrl.transmitCmd(AmpCmd(PDC_AMP, INPUT_SEL_CMD, [selValue], [OK_RESP], self.zone))
        
    def select_sound_mode(self, sound_mode):
        selValue = SOUND_MODES[sound_mode]
        self.ampCtrl.transmitCmd(AmpCmd(PDC_SOUND_ADAPTOR, SF_SEL_CMD, [selValue], [OK_RESP]))
        
    def turn_on(self):
        self.ampCtrl.transmitCmd(AmpCmd(PDC_AMP, PWR_CTRL_CMD, [1], [OK_RESP], self.zone))
       
    def turn_off(self):
        self.ampCtrl.transmitCmd(AmpCmd(PDC_AMP, PWR_CTRL_CMD, [0], [OK_RESP], self.zone))
       
    def set_volume_level(self, volume):
        """Set volume level, range 0..1."""
        volume    = min(1, max(0, volume))
        rawVolume = int(((volume * 92) - 92) * 256)
        data      = [1, (rawVolume >> 8) & 0xFF, rawVolume & 0xFF]
        self.ampCtrl.transmitCmd(AmpCmd(PDC_AMP, VOL_SET, data, [OK_RESP], self.zone))

    def mute_volume(self, mute):
        self.ampCtrl.transmitCmd(AmpCmd(PDC_AMP, MUTE_CMD, [1 if mute else 0], [OK_RESP], self.zone))
        

    