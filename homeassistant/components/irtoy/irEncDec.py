#!/usr/bin/env python

import sys
import serial
import time
import queue
import threading
import binascii
import argparse
import logging


_LOGGER = logging.getLogger(__name__)

IR_TOY_SAMPLE_PERIOD          = 21.333333333
IR_TOY_WAIT_TIME              = 0.05
CMD_REPEAT_FILTER_TIME        = 1.5
IR_IDLE_DELAY                 = 0.1
IR_RX_TO_TX_DELAY             = 0.05
IR_WATCHDOG_IDLE_COUNT        = 50
# Sony IR constants
SONY_BIT_PERIOD               = 600
SONY_FRAME_REPEAT_SAMPLES     = 40000 / IR_TOY_SAMPLE_PERIOD      
SONY_SAMPLE_DETECT_THRESHOLD  = 6
SONY_NUM_REPEAT_FRAMES        = 3
SONY_SAMPLES_PER_BIT          = SONY_BIT_PERIOD / IR_TOY_SAMPLE_PERIOD
SONY_START_SAMPLES            = SONY_SAMPLES_PER_BIT * 4
SONY_MIN_END_OFF_SAMPLES      = SONY_SAMPLES_PER_BIT * 4
# Humax IR constants
HUMAX_START_ON_SAMPLES        = 418
HUMAX_START_OFF_SAMPLES       = 210
HUMAX_DATA_END_OFF_SAMPLES    = 2236
HUMAX_SAMPLES_PER_BIT         = 26
HUMAX_SAMPLE_DETECT_THRESHOLD = 4
# Raw constants
RAW_DETECT_THRESHOLD          = 4



################################################################################
class IrCmd:
    TYPE_NULL  = "Null"
    TYPE_SONY  = "Sony"
    TYPE_HUMAX = "Humax"
    TYPE_RAW   = "Raw"
    type       = 0
    width      = 0
    data       = 0
    name       = None


    def __init__(self, type=TYPE_NULL, data=0, width=0, name=None):
        self.type      = type
        self.data      = data 
        self.width     = width
        self.name      = name
        self.timeStamp = time.time()
  

    def __str__(self):        
        if self.name:
            result = "%s %s" %(self.type, self.name)
        else:
            result = "type: %s data: %s width: %s" %(self.type, self.data, self.width)
        return result


    def __eq__(self, other): 
        # we don't include the time in either the equal check, as we need 
        # objects from different times to appear the same 
        eq = False
        if isinstance(other, IrCmd):    
            eq = (self.type  == other.type)  and \
                 (self.width == other.width) and \
                 (self.data  == other.data)
        return eq


    def __hash__(self):
        return hash((self.type, self.width, self.data))


    def repeatOf(self, other): 
        return self.__eq__(other) and \
               (self.timeStamp + CMD_REPEAT_FILTER_TIME > other.timeStamp) and \
               (self.timeStamp - CMD_REPEAT_FILTER_TIME < other.timeStamp)


    def encode(self):
        if self.type == IrCmd.TYPE_SONY:        
            encData = self.encodeSony(self.data, self.width)
        elif self.type == IrCmd.TYPE_HUMAX:        
            encData = self.encodeHumax(self.data, self.width)
        elif self.type == IrCmd.TYPE_RAW:        
            encData = self.encodeRaw(self.data)
        else:
            encData = []
            print('Unknown IR command type %s' %self.type)                
        return encData


    def encodeRaw(self, data):
        rawData  = []
        isOnTime = True
        for time in data:
            if isOnTime:
                onTime = time
            else:              
                rawData = self.encodeRawData(rawData, onTime, time)
            isOnTime = not isOnTime;
        return rawData


    def encodeRawData(self, rawData, onTime, offTime ):
        onTime  = int(onTime)
        offTime = int(offTime)
        rawData += binascii.unhexlify('%.2x' %(onTime  >> 8)) 
        rawData += binascii.unhexlify('%.2x' %(onTime  &  0xFF)) 
        rawData += binascii.unhexlify('%.2x' %(offTime >> 8)) 
        rawData += binascii.unhexlify('%.2x' %(offTime &  0xFF)) 
        return rawData


    def encodeSony(self, data, bitCount):
        rawData = []

        # Create the patern at 3 times
        for i in range(0,SONY_NUM_REPEAT_FRAMES):
            # Gerenate the start pulse
            rawData = self.encodeRawData(rawData, SONY_START_SAMPLES, SONY_SAMPLES_PER_BIT)
            
            # output the data
            for curBit in range(0, bitCount):
                if ((data >> curBit) & 1) != 0: 
                    onTime  = SONY_SAMPLES_PER_BIT * 2                    
                else:                           
                    onTime  = SONY_SAMPLES_PER_BIT
                if curBit == (bitCount - 1): 
                    if i == (SONY_NUM_REPEAT_FRAMES - 1):
                        offTime = 0xFFFF
                    else:
                        offTime = SONY_FRAME_REPEAT_SAMPLES
                else:                        
                    offTime = SONY_SAMPLES_PER_BIT
                rawData = self.encodeRawData(rawData, onTime, offTime)

        return rawData


    def encodeHumax(self, data, bitCount):
        rawData = []

        # generate the start pulse
        rawData = self.encodeRawData(rawData, HUMAX_START_ON_SAMPLES, HUMAX_START_OFF_SAMPLES)
        # output the data
        for curBit in range(0, bitCount):
            if ((data >> curBit) & 1) != 0: 
                offTime = HUMAX_SAMPLES_PER_BIT * 3                    
            else:                           
                offTime = HUMAX_SAMPLES_PER_BIT
            rawData = self.encodeRawData(rawData, HUMAX_SAMPLES_PER_BIT, offTime)
        # output the various bits of tail info
        rawData = self.encodeRawData(rawData, HUMAX_SAMPLES_PER_BIT,  HUMAX_DATA_END_OFF_SAMPLES)
        rawData = self.encodeRawData(rawData, HUMAX_START_ON_SAMPLES, (HUMAX_START_OFF_SAMPLES / 2))
        rawData = self.encodeRawData(rawData, HUMAX_SAMPLES_PER_BIT,  0xFFFF)
        return rawData



################################################################################
# Raw commands that don't have a dedicated decoder, The data is the on/off times 
# of the IR pulses
cmdDenonCdr = IrCmd(IrCmd.TYPE_RAW, (
   11, 36, 11, 37, 12, 36, 11, 87, 11, 36, 12, 37, 11, 86, 11, 86, 12, 86, 11, 36, 10, 37, 12, 86, 11, 86, 11, 36, 12, 35, 12, 2099,
   10, 37, 11, 37, 11, 37, 10, 87, 10, 38, 12, 86, 11, 36, 11, 37, 11, 37, 11, 86, 11, 86, 13, 36, 11, 37, 10, 87, 12, 85, 13, 2099,
   11, 36, 10, 37, 12, 37, 10, 87, 10, 37, 12, 37, 10, 87, 10, 87, 12, 87, 11, 37, 11, 37, 11, 87, 11, 86, 10, 37, 11, 36, 12, 65535))

cmdApplePlay = IrCmd(IrCmd.TYPE_RAW, (
    425, 215, 27, 27, 27, 80, 27, 80, 27, 80, 27, 27, 27, 80, 27, 80, 27, 80, 27, 80, 27, 80, 27, 80, 27, 27, 27, 27, 27, 27, 27, 27, 27, 80, 
    27, 80, 27, 28, 26, 80, 27, 27, 27, 27, 27, 27, 27, 27, 27, 27, 27, 27, 27, 80, 27, 80, 27, 27, 27, 27, 27, 27, 27, 80, 27, 27, 27, 65535))

cmdAppleMenu = IrCmd(IrCmd.TYPE_RAW, (
    426, 215, 27, 27, 27, 80, 27, 80, 27, 80, 27, 27, 27, 80, 27, 80, 27, 80, 27, 80, 27, 81, 26, 80, 27, 27, 27, 27, 27, 27, 27, 27, 27, 80, 
    27, 80, 27, 80, 27, 27, 27, 27, 27, 27, 27, 27, 27, 27, 27, 27, 27, 27, 27, 81, 26, 80, 27, 27, 27, 27, 27, 27, 27, 80, 27, 27, 27, 65535))

cmdAppleDown = IrCmd(IrCmd.TYPE_RAW, (
    426, 215, 26, 27, 27, 80, 27, 80, 27, 80, 26, 28, 27, 81, 26, 80, 27, 80, 27, 80, 27, 80, 26, 81, 26, 28, 26, 28, 26, 27, 27, 28, 26, 80, 
    27, 27, 27, 27, 27, 80, 27, 80, 27, 27, 27, 28, 26, 27, 27, 27, 27, 27, 26, 81, 27, 80, 27, 28, 26, 27, 27, 27, 27, 80, 27, 27, 27, 65535))

cmdAppleUp = IrCmd(IrCmd.TYPE_RAW, (
    425, 215, 26, 28, 26, 80, 27, 81, 26, 81, 27, 28, 27, 80, 26, 81, 27, 80, 26, 81, 26, 81, 26, 81, 26, 28, 27, 27, 27, 28, 26, 28, 26, 81, 
    26, 28, 26, 81, 26, 27, 26, 81, 26, 28, 26, 28, 26, 28, 26, 27, 27, 28, 27, 80, 27, 80, 26, 28, 26, 28, 27, 28, 26, 82, 26, 28, 26, 65535))

cmdAppleLeft = IrCmd(IrCmd.TYPE_RAW, (
    425, 216, 26, 29, 25, 82, 26, 81, 26, 81, 26, 27, 26, 81, 26, 81, 26, 81, 27, 80, 27, 80, 26, 81, 26, 27, 26, 29, 26, 27, 26, 28, 26, 81, 
    26, 81, 27, 28, 26, 29, 26, 82, 26, 28, 27, 28, 26, 28, 26, 28, 27, 28, 26, 80, 26, 81, 26, 28, 26, 28, 26, 27, 26, 81, 26, 28, 26, 65535))

cmdAppleRight = IrCmd(IrCmd.TYPE_RAW, (
    425, 216, 26, 28, 26, 81, 27, 80, 27, 81, 27, 27, 26, 81, 27, 80, 26, 81, 26, 81, 26, 81, 26, 81, 26, 28, 26, 28, 26, 28, 26, 28, 26, 81, 
    26, 28, 26, 81, 26, 81, 26, 28, 26, 28, 26, 28, 27, 27, 26, 28, 27, 27, 26, 81, 26, 81, 27, 27, 27, 27, 26, 28, 27, 80, 27, 27, 26, 65535))

# This list contains all the raw commands that the system can listen for
rawCommands = [cmdDenonCdr, cmdApplePlay, cmdAppleMenu, cmdAppleDown, 
               cmdAppleUp, cmdAppleLeft, cmdAppleRight]

knownCommands = [
    IrCmd(IrCmd.TYPE_SONY,  2226,       12, "CD Play"),
    IrCmd(IrCmd.TYPE_SONY,  2232,       12, "CD Stop"),
    IrCmd(IrCmd.TYPE_SONY,  2233,       12, "CD Pause"),
    IrCmd(IrCmd.TYPE_SONY,  2225,       12, "CD Next Track"),
    IrCmd(IrCmd.TYPE_SONY,  2224,       12, "CD Pervious Track"),
    IrCmd(IrCmd.TYPE_SONY,  929050,     20, "Blue-ray Play"),
    IrCmd(IrCmd.TYPE_SONY,  929070,     20, "Blue-ray On"),
    IrCmd(IrCmd.TYPE_SONY,  929071,     20, "Blue-ray Off"),
    IrCmd(IrCmd.TYPE_SONY,  174,        12, "TV On"),
    IrCmd(IrCmd.TYPE_SONY,  175,        12, "TV Off"),
    IrCmd(IrCmd.TYPE_SONY,  3418,       15, "TV Input HDMI1"),
    IrCmd(IrCmd.TYPE_SONY,  3419,       15, "TV Input HDMI2"),
    IrCmd(IrCmd.TYPE_SONY,  3420,       15, "TV Input HDMI3"),
    IrCmd(IrCmd.TYPE_SONY,  3421,       15, "TV Input HDMI4"),
    IrCmd(IrCmd.TYPE_SONY,  22560,      15, "Reciever Night Mode"),
    IrCmd(IrCmd.TYPE_SONY,  6165,       15, "Reciever Power"),
    IrCmd(IrCmd.TYPE_HUMAX, 4077654016, 32, "PVR On"),
    IrCmd(IrCmd.TYPE_HUMAX, 3960672256, 32, "PVR OK")
]



################################################################################
class IrEncDec(threading.Thread):
    prevIntData      = 0
    rawByteCount     = 0
    sonyData         = 0
    sonyBitCount     = 0
    sonyPrevData     = 0
    sonyPrevBitCount = 0
    sonyError        = True
    sonyEndOfBurst   = False
    humaxData        = 0
    humaxBitCount    = 0
    humaxState       = 0
    rawBitPossition  = 0
    rawCandidateCmds = []
    idleCount        = 0
    prevRxCmd        = IrCmd()
    irToy            = None


    def processCommand(self, type, data, width):
        cmd = IrCmd(type, data, width)
        # skip repeated commands
        if not self.prevRxCmd.repeatOf( cmd ):
            # If the command is one of the known commands, update the name accordingly
            matchingCommands = list(filter(lambda x: x == cmd, knownCommands))
            if matchingCommands:
                cmd.name = matchingCommands[0].name
            _LOGGER.info("RX: " + str(cmd))
            self.recieveCmd(cmd)
                
        self.prevRxCmd = cmd


    def decodeRaw(self, time):
        # If this is the first possition 
        if self.rawBitPossition == 0:
            # go through all the available commands adding any that match the 
            # first bit to the candidate array.
            for cmd in rawCommands: 
                if (time >= (cmd.data[self.rawBitPossition] - RAW_DETECT_THRESHOLD)) and \
                   (time <= (cmd.data[self.rawBitPossition] + RAW_DETECT_THRESHOLD)):
                    self.rawCandidateCmds.append(cmd);
        else:
            # go through the candidates checking if have completed a match, or 
            # don't match and should be removed
            for cmd in self.rawCandidateCmds: 
                removeCmd = True;
                # check the command is long enough
                if len(cmd.data) > (self.rawBitPossition + 1):
                    # does the pulse match the current candidate
                    if (time >= (cmd.data[self.rawBitPossition] - RAW_DETECT_THRESHOLD)) and \
                       (time <= (cmd.data[self.rawBitPossition] + RAW_DETECT_THRESHOLD)):
                        # This is a complete match if the next pulse in the command is the end
                        if cmd.data[self.rawBitPossition + 1] == 0xFFFF:
                            self.processCommand(IrCmd.TYPE_RAW, cmd.data, 0)
                        else:
                            removeCmd = False;

                # remove the candidate if its not valid any more                    
                if removeCmd:
                    self.rawCandidateCmds.remove(cmd)

        self.rawBitPossition = self.rawBitPossition + 1
        # if we recieve the end of packet indicator reset the bit possition
        if time == 0xFFFF:
            self.rawCandidateCmds = []
            self.rawBitPossition  = 0;


    def decodeHumax(self, onTime, offTime):
        if self.humaxState == 0: # looking for start bit
            if (onTime  >= (HUMAX_START_ON_SAMPLES  - HUMAX_SAMPLE_DETECT_THRESHOLD)) and \
               (onTime  <= (HUMAX_START_ON_SAMPLES  + HUMAX_SAMPLE_DETECT_THRESHOLD)) and \
               (offTime >= (HUMAX_START_OFF_SAMPLES - HUMAX_SAMPLE_DETECT_THRESHOLD)) and \
               (offTime <= (HUMAX_START_OFF_SAMPLES + HUMAX_SAMPLE_DETECT_THRESHOLD)):
                self.humaxState   += 1
                self.humaxData     = 0
                self.humaxBitCount = 0
        elif self.humaxState == 1: # recieving data
            # calculate some interesting times
            isOnTime1T  = (onTime  >= ( HUMAX_SAMPLES_PER_BIT      - HUMAX_SAMPLE_DETECT_THRESHOLD)) and \
                          (onTime  <= ( HUMAX_SAMPLES_PER_BIT      + HUMAX_SAMPLE_DETECT_THRESHOLD))
            isOffTime1T = (offTime >= ( HUMAX_SAMPLES_PER_BIT      - HUMAX_SAMPLE_DETECT_THRESHOLD)) and \
                          (offTime <= ( HUMAX_SAMPLES_PER_BIT      + HUMAX_SAMPLE_DETECT_THRESHOLD))
            isOffTime3T = (offTime >= ((HUMAX_SAMPLES_PER_BIT * 3) - HUMAX_SAMPLE_DETECT_THRESHOLD)) and \
                          (offTime <= ((HUMAX_SAMPLES_PER_BIT * 3) + HUMAX_SAMPLE_DETECT_THRESHOLD))
            # check the on pulse width
            if not isOnTime1T: 
                self.humaxState = 0;
            # if the time is a valid bit then add it to the data
            elif isOffTime1T or isOffTime3T:
                self.humaxData      |= int(isOffTime3T) << self.humaxBitCount
                self.humaxBitCount  += 1
            elif (offTime >= (HUMAX_DATA_END_OFF_SAMPLES - HUMAX_SAMPLE_DETECT_THRESHOLD)) and \
                 (offTime <= (HUMAX_DATA_END_OFF_SAMPLES + HUMAX_SAMPLE_DETECT_THRESHOLD)):
                self.humaxState += 1;
            else:
                self.humaxState = 0;
        elif self.humaxState == 2: # recieving tail 1
            if (onTime  >= ( HUMAX_START_ON_SAMPLES       - HUMAX_SAMPLE_DETECT_THRESHOLD)) and \
               (onTime  <= ( HUMAX_START_ON_SAMPLES       + HUMAX_SAMPLE_DETECT_THRESHOLD)) and \
               (offTime >= ((HUMAX_START_OFF_SAMPLES / 2) - HUMAX_SAMPLE_DETECT_THRESHOLD)) and \
               (offTime <= ((HUMAX_START_OFF_SAMPLES / 2) + HUMAX_SAMPLE_DETECT_THRESHOLD)):
                self.humaxState += 1;
            else:
                self.humaxState = 0;
        elif self.humaxState == 3: # recieving tail 2
            if (onTime >= (HUMAX_SAMPLES_PER_BIT - HUMAX_SAMPLE_DETECT_THRESHOLD)) and \
               (onTime <= (HUMAX_SAMPLES_PER_BIT + HUMAX_SAMPLE_DETECT_THRESHOLD)):                
                self.processCommand(IrCmd.TYPE_HUMAX, self.humaxData, self.humaxBitCount)
            self.humaxState = 0;
        else: # default case, go back to idle
            self.humaxState = 0


    def decodeSony(self, onTime, offTime):
        foundStart  = False
        isOffTime1T = (offTime >= (SONY_SAMPLES_PER_BIT - SONY_SAMPLE_DETECT_THRESHOLD)) and \
                      (offTime <= (SONY_SAMPLES_PER_BIT + SONY_SAMPLE_DETECT_THRESHOLD))
        # what type of pulse is it, first we look at the off time to work out if 
        if (onTime >= (SONY_START_SAMPLES - SONY_SAMPLE_DETECT_THRESHOLD)) and \
           (onTime <= (SONY_START_SAMPLES + SONY_SAMPLE_DETECT_THRESHOLD)) and isOffTime1T:
            self.sonyEndOfBurst = not self.sonyError
            foundStart          = True            
        elif not self.sonyError:
            # expecting a data bit, so process it whilst checking for errors
            isOnTime1T = (onTime >= ( SONY_SAMPLES_PER_BIT      - SONY_SAMPLE_DETECT_THRESHOLD)) and \
                         (onTime <= ( SONY_SAMPLES_PER_BIT      + SONY_SAMPLE_DETECT_THRESHOLD))
            isOnTime2T = (onTime >= ((SONY_SAMPLES_PER_BIT * 2) - SONY_SAMPLE_DETECT_THRESHOLD)) and \
                         (onTime <= ((SONY_SAMPLES_PER_BIT * 2) + SONY_SAMPLE_DETECT_THRESHOLD))
            self.sonyEndOfBurst = offTime >= SONY_MIN_END_OFF_SAMPLES
            self.sonyError      = self.sonyError  or \
                                  not(isOffTime1T or self.sonyEndOfBurst) or \
                                  not(isOnTime1T  or isOnTime2T)            
            self.sonyData      |= int(isOnTime2T) << self.sonyBitCount
            self.sonyBitCount  += 1
        else:
            # shouldn't get here unless its going wrong
            self.sonyError = True

        # if this is the end of a burst process the data we've collected
        if self.sonyEndOfBurst:
            if not self.sonyError:
                # sony commands are only valid if we see the same thing at 
                # least twice
                if (self.sonyPrevData     == self.sonyData) and \
                   (self.sonyPrevBitCount == self.sonyBitCount):
                    self.processCommand(IrCmd.TYPE_SONY, self.sonyData, self.sonyBitCount)
                # rotate the vars
                self.sonyPrevData     = self.sonyData      
                self.sonyPrevBitCount = self.sonyBitCount
            # We set the error flag so we don't do anything else until we've 
            # seen a start
            self.sonyError = True

        # If we found a start pulse then setup for a new burst
        if foundStart:
            self.sonyError    = False
            self.sonyData     = 0    
            self.sonyBitCount = 0


    def decodeRawData(self, rawData):
        # Go through the sample data in pairs, as they are actually the upper and 
        # lower halfs of a 16 bit number, then alternate sameples are the on and off 
        # times of the IR pulse.
        for i in range(0,rawData.__len__()):
            intData = rawData[i]

            newByteCount = self.rawByteCount + 1
            if self.rawByteCount == 0:
                self.onTime = intData << 8
            elif self.rawByteCount == 1:
                self.onTime |= intData 
                self.decodeRaw(self.onTime)            
            elif self.rawByteCount == 2:
                self.offTime = intData << 8
            else:
                self.offTime |= intData 
                newByteCount = 0
                self.decodeRaw(self.offTime)            
                self.decodeSony(self.onTime, self.offTime)
                self.decodeHumax(self.onTime, self.offTime)            

            # just to make sure things stay in sync, if we find 255, 255 in the 
            # timing sequence then it must be the end of a burst, so make sure 
            # we've got a 0 byte count so we're ready for the start of the next
            if (self.prevIntData == 0xFF) and (intData == 0xFF):
                newByteCount = 0

            # variable rotation
            self.rawByteCount = newByteCount
            self.prevIntData  = intData 
        return
  

    def _irToyInit(self):
        self.irToy.write(b'\0\0\0\0\0')
        time.sleep(IR_TOY_WAIT_TIME)
        # put the ir toy into sample mode
        self.irToy.write(b'S')
        # now wait for the protocol responce to arrive then flush the buffers
        self.irToy.read(3)
        self.irToy.flushInput()
        self.rawByteCount = 0
       

    def recieveData(self):
        waitingBytes = self.irToy.inWaiting()
        dataRead     = waitingBytes != 0
        if dataRead:
            data = self.irToy.read(waitingBytes)
            self.decodeRawData(data)
        return dataRead


    def sendData(self):
        dataWrite = False
        while not self.irTxCmdQueue.empty():
            dataWrite = True
            # get the data to transmit 
            cmd = self.irTxCmdQueue.get()            
            _LOGGER.info("TX: " + str(cmd))
            # encode the data and add on the transmit command header
            data = cmd.encode()            
            self.sendBurst(data);
        return dataWrite    


    def sendBurst(self, data):    
        # we try to send the command a few times before giving up
        for retryCount in range(0,5):
            # Reset the device then enable handshaking, tx reports, etc finally
            # put the usb toy into transmit mode
            self._irToyInit()
            self.irToy.write(b'\x26\x25\x24\x03')             
            self.irToy.read(1) # handshake

            bytesWritten = 0           
            # 31 * 2 bytes = max of 62 bytes in the buffer.  31 hangs so using 32, strange.
            maxWriteSize = 32
            for idx in range(0, len(data), maxWriteSize):
                segmentWritten = self.irToy.write(data[idx:idx+maxWriteSize])
                bytesWritten  += segmentWritten
                # recieve the handshake byte, this causes a wait and prevents 
                # buffer overflow
                self.irToy.read(1)
                    
            # get the transmit report
            txReport = self.irToy.read(4)            
            
            # This seams to be required to keep the device working
            self._irToyInit()
            time.sleep(0.05);
            if (bytesWritten == len(data)) and (txReport[3] == 67):
                break

        # Flush out any stuff thats ended up in the rx buffer
        self.rawByteCount = 0
        self.irToy.flushInput()


    def __init__(self, port, recieveCmd):
        threading.Thread.__init__(self, name="IrEncDec")
        self.port         = port
        self.recieveCmd   = recieveCmd
        self.irTxCmdQueue = queue.Queue()
        self.running      = True
        self.start()

    
    # entry point to event pump thread
    def run(self):
        try:
            _LOGGER.debug("Starting interface thread for " + self.port)        
            self.irToy = serial.Serial(self.port)
            lastRxTime = 0
            self._irToyInit()  
            while self.running:
                # process any RX data that has arrived
                busy    = self.recieveData();
                curTime = time.time()
                if busy:
                    lastRxTime = curTime
                
                # Now try to do a TX, NOTE: we only do this if the IR has been quiet 
                # for a while, this helps prevent collisions
                if curTime >= (lastRxTime + IR_RX_TO_TX_DELAY):
                    busy = self.sendData(); 

                # if we havn't done anything go to sleep for a bit
                if busy:
                    self.idleCount = 0
                else:
                    time.sleep(IR_IDLE_DELAY);
                    # in a sort of watchdog style, reset the link if we've had a
                    # while of inactivity
                    self.idleCount += 1
                    if self.idleCount > IR_WATCHDOG_IDLE_COUNT:
                        self.idleCount = 0
                        self._irToyInit()

            self.irToy.flushInput()
        except Exception: 
            _LOGGER.exception("Unexpected exception")
        
        _LOGGER.debug("Killed interface thread for " + self.port)                    
        if self.irToy != None:
            self.irToy.close()
        return 
        
 
    def transmitCmd(self, cmd):
        self.irTxCmdQueue.put(cmd)
 
 
    def close(self):
        self.running = False



################################################################################
if __name__ == "__main__":
    # get the args 
    parser = argparse.ArgumentParser(description='IR code transmitter')
    parser.add_argument('-t', '--type', dest='type', action='store', default='Sony',
                        type=str, help='The IR protocol type')
    parser.add_argument('-c', '--cmd', dest='data', action='store', default='0',
                        type=int, help='The IR command to send')
    parser.add_argument('-w', '--width', dest='width', action='store', default='0',
                        type=int, help='The number of bits in the command to send')
    parser.add_argument('-l', '--listen', action="store_true",
                        help='Gets the IRToy to listen for IR commands')
    parser.add_argument('-i', '--irToy', dest='irToyPort', action='store',
                        default='/dev/ttyACM0', help='Serial port for the USB IR TOY')
    args = parser.parse_args()

    # create the queues we use to connect the different threads
    rxCmdQueue = queue.Queue()
    # new create the components
    def recievedCmd(cmd):
        rxCmdQueue.put(cmd)
    irEncDec = IrEncDec(args.irToyPort, recievedCmd)
    if args.width > 0:
        irEncDec.transmitCmd(IrCmd(args.type, args.data, args.width))

    # should we try and recieve a command
    if args.listen:
        print(rxCmdQueue.get())

    time.sleep(0.5)
    irEncDec.close()
