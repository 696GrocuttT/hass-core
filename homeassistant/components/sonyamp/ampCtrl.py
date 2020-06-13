#! /usr/bin/python

import serial
import time
import queue
import threading
import argparse

# General constants
RETRY_LIMIT             = 5
CMD_FAIL_RECOVERY_TIME  = 2
IDLE_DELAY              = 0.1
# constands for the STR-DA3500ES in my setup
NUM_ZONES               = 3
OK_RESP                 = 0xFD
# commands and values for the DSP functions, No zone is specified for these commands
PDC_SOUND_ADAPTOR       = 0xA3
SF_SEL_CMD              = 0x42
SF_SEL_CMD_2CH_ST       = 0x0
SF_SEL_CMD_A_DIRECT     = 0x2
SF_SEL_CMD_AFD_AUTO     = 0x21
SF_SEL_CMD_ESURROUND    = 0x32
# commands and values for the basic AMP functions. These commands require the zone to be specified
PDC_AMP                 = 0xA0
PDC_AMP_RESPONCE        = 0xA8
PWR_CTRL_CMD            = 0x60
MUTE_CMD                = 0x53
STATUS_REQ              = 0x82
INPUT_SEL_CMD           = 0x42
INPUT_SEL_CMD_TUNER     = 0x0
INPUT_SEL_CMD_PHONO     = 0x1
INPUT_SEL_CMD_CD        = 0x2
INPUT_SEL_CMD_MD        = 0x4
INPUT_SEL_CMD_SOURCE    = 0xF
INPUT_SEL_CMD_TAPE      = 0x10
INPUT_SEL_CMD_FRONT_AV  = 0x11
INPUT_SEL_CMD_PVR       = 0x16
INPUT_SEL_CMD_APPLE_TV  = 0x19
INPUT_SEL_CMD_TV        = 0x1A
INPUT_SEL_CMD_BD        = 0x1B
INPUT_SEL_CMD_5p1_IN    = 0x20
INPUT_SEL_CMD_ATV_HDMI  = 0x21
INPUT_SEL_CMD_BD_HDMI   = 0x22
TRIG_12V_CMD            = 0x43
MEM_WRITE               = 0xC1
MEM_READ                = 0xC2
GUI_SET                 = 0x6A
GUI_SET_GUI_TOGGLE      = 0x2A
GUI_SET_CURSOR_UP       = 0x30
GUI_SET_CURSOR_DOWN     = 0x31
GUI_SET_CURSOR_RIGHT    = 0x32
GUI_SET_CURSOR_LEFT     = 0x33
GUI_SET_ENTER           = 0x34
# Memory mapped settings
SYSTEM_ADDR_SPACE       = 2
SPEAKER_SEL_ADDR        = 575
SPEAKER_SEL_NONE        = 1
SPEAKER_SEL_A           = 2
SPEAKER_SEL_B           = 3
SPEAKER_SEL_AB          = 4
NIGHT_MODE              = 572



################################################################################
class AmpCmd:
    zoneCommands = {PDC_AMP:          [STATUS_REQ, PWR_CTRL_CMD, MUTE_CMD, INPUT_SEL_CMD],
                    PDC_AMP_RESPONCE: [STATUS_REQ]}
                    
                    
    def __init__(self, pdc, cmd, value=None, expResp=[], zone=None):
        self.pdc     = pdc
        self.cmd     = cmd
        self.value   = value
        self.expResp = expResp
        self.zone    = zone


    @staticmethod
    def AmpCmdFromData(data):
        data   = list(data)
        length = len(data)
        cmd    = None
        if length > 3:
            pdc      = data[0]
            cmd      = data[1]    
            bodyData = data[:length-1]
            if AmpCmd.genCrc(bodyData) == data[length-1]:
                # Now we have an array of numbers, we can interpret the command
                zone = None
                if pdc in AmpCmd.zoneCommands:
                    if cmd in AmpCmd.zoneCommands[pdc]:
                        zone = bodyData.pop(2)
                cmd = AmpCmd(pdc, cmd, bodyData[2:], zone=zone)
        return cmd


    @staticmethod
    def AmpMemWriteCmd(addr, value):
        data = [SYSTEM_ADDR_SPACE, addr >> 8, addr & 0xff, len(value)]
        data.extend(value)
        return AmpCmd(PDC_AMP, MEM_WRITE, data)


    @staticmethod
    def AmpMemReadCmd(addr, size):
        data = [SYSTEM_ADDR_SPACE, addr >> 8, addr & 0xff, size]
        return AmpCmd(PDC_AMP, MEM_READ, data)

    @staticmethod
    def genCrc(data):
        checkSum = len(data)
        for x in data:
            checkSum = checkSum + x
        return (256 - checkSum) & 0xFF


    def data(self):
        if self.zone == None:
            data = [self.pdc, self.cmd]
        else:
            data = [self.pdc, self.cmd, self.zone]
        if self.value:
            data.extend(self.value)

        bytes = b'\x02' + len(data).to_bytes(1, byteorder="little")
        for x in data:
            bytes = bytes + x.to_bytes(1, byteorder="little")
        return bytes + AmpCmd.genCrc(data).to_bytes(1, byteorder="little")


    def isMemRead(self):
        return self.pdc in [PDC_AMP, PDC_AMP_RESPONCE] and self.cmd == MEM_READ


    def isMemWrite(self):
        return self.pdc in [PDC_AMP, PDC_AMP_RESPONCE] and self.cmd == MEM_WRITE


    def memAddrSpace(self):
        assert(self.isMemWrite() or self.isMemRead())
        return self.value[0]


    def memAddr(self):
        assert(self.isMemWrite() or self.isMemRead())
        return self.value[1] << 8 | self.value[2]


    def memData(self):
        assert(self.isMemWrite() or self.isMemRead())
        return self.value[4:]


    def __eq__(self, other):
        eq = False
        if isinstance(other, AmpCmd):
            eq = (self.pdc     == other.pdc)     and \
                 (self.cmd     == other.cmd)     and \
                 (self.value   == other.value)   and \
                 (self.expResp == other.expResp) and \
                 (self.zone    == other.zone)
        return eq


    def __hash__(self):
        return hash((self.pdc, self.cmd, tuple(self.value), tuple(self.expResp), self.zone))


    def __str__(self):
        if self.isMemRead() or self.isMemWrite():
            result = "AMP pdc: 0x{0:02X} cmd: 0x{1:02X} addr_space: 0x{2:02X} addr: 0x{3:04X} data: {4}".format( \
                     self.pdc, self.cmd, self.memAddrSpace(), self.memAddr(), self.memData())
        else:
            result = "AMP pdc: 0x{0:02X} cmd: 0x{1:02X} value: {2} expResp: {3} zone: {4}".format( \
                     self.pdc, self.cmd, self.value, self.expResp, self.zone)
        return result



################################################################################
cmdAmpZone1On        = AmpCmd(PDC_AMP,           PWR_CTRL_CMD,  [1],                      [OK_RESP], 0)
cmdAmpZone1Off       = AmpCmd(PDC_AMP,           PWR_CTRL_CMD,  [0],                      [OK_RESP], 0)
cmdAmpZone2On        = AmpCmd(PDC_AMP,           PWR_CTRL_CMD,  [1],                      [OK_RESP], 1)
cmdAmpZone2Off       = AmpCmd(PDC_AMP,           PWR_CTRL_CMD,  [0],                      [OK_RESP], 1)
cmdAmpZone3On        = AmpCmd(PDC_AMP,           PWR_CTRL_CMD,  [1],                      [OK_RESP], 2)
cmdAmpZone3Off       = AmpCmd(PDC_AMP,           PWR_CTRL_CMD,  [0],                      [OK_RESP], 2)
cmdAmpZone1MuteOff   = AmpCmd(PDC_AMP,           MUTE_CMD,      [0],                      [OK_RESP], 0)
cmdAmpZone1SelCD     = AmpCmd(PDC_AMP,           INPUT_SEL_CMD, [INPUT_SEL_CMD_CD],       [OK_RESP], 0)
cmdAmpZone1SelBD     = AmpCmd(PDC_AMP,           INPUT_SEL_CMD, [INPUT_SEL_CMD_BD],       [OK_RESP], 0)
cmdAmpZone1SelTV     = AmpCmd(PDC_AMP,           INPUT_SEL_CMD, [INPUT_SEL_CMD_TV],       [OK_RESP], 0)
cmdAmpZone1SelATv    = AmpCmd(PDC_AMP,           INPUT_SEL_CMD, [INPUT_SEL_CMD_APPLE_TV], [OK_RESP], 0)
cmdAmpZone1SelATvHd  = AmpCmd(PDC_AMP,           INPUT_SEL_CMD, [INPUT_SEL_CMD_ATV_HDMI], [OK_RESP], 0)
cmdAmpZone2SelATv    = AmpCmd(PDC_AMP,           INPUT_SEL_CMD, [INPUT_SEL_CMD_APPLE_TV], [OK_RESP], 1)
cmdAmpZone12ChSt     = AmpCmd(PDC_SOUND_ADAPTOR, SF_SEL_CMD,    [SF_SEL_CMD_2CH_ST],      [OK_RESP])
cmdAmpZone1ADirect   = AmpCmd(PDC_SOUND_ADAPTOR, SF_SEL_CMD,    [SF_SEL_CMD_A_DIRECT],    [OK_RESP])
cmdAmpZone1AfdAuto   = AmpCmd(PDC_SOUND_ADAPTOR, SF_SEL_CMD,    [SF_SEL_CMD_AFD_AUTO],    [OK_RESP])
cmdAmpZone1ESurround = AmpCmd(PDC_SOUND_ADAPTOR, SF_SEL_CMD,    [SF_SEL_CMD_ESURROUND],   [OK_RESP])
cmdAmpAuxOn          = AmpCmd(PDC_AMP,           TRIG_12V_CMD,  [0,1],                    [OK_RESP])
cmdAmpAuxOff         = AmpCmd(PDC_AMP,           TRIG_12V_CMD,  [0,0],                    [OK_RESP])
cmdAmpGuiToggle      = AmpCmd(PDC_AMP,           GUI_SET,       [GUI_SET_GUI_TOGGLE],     [OK_RESP], 0)
cmdAmpGuiUp          = AmpCmd(PDC_AMP,           GUI_SET,       [GUI_SET_CURSOR_UP],      [OK_RESP], 0)
cmdAmpGuiDown        = AmpCmd(PDC_AMP,           GUI_SET,       [GUI_SET_CURSOR_DOWN],    [OK_RESP], 0)
cmdAmpGuiLeft        = AmpCmd(PDC_AMP,           GUI_SET,       [GUI_SET_CURSOR_LEFT],    [OK_RESP], 0)
cmdAmpGuiRight       = AmpCmd(PDC_AMP,           GUI_SET,       [GUI_SET_CURSOR_RIGHT],   [OK_RESP], 0)
cmdAmpGuiEnter       = AmpCmd(PDC_AMP,           GUI_SET,       [GUI_SET_ENTER],          [OK_RESP], 0)
cmdAmpSpkNone        = AmpCmd.AmpMemWriteCmd(SPEAKER_SEL_ADDR, [SPEAKER_SEL_NONE])
cmdAmpSpkA           = AmpCmd.AmpMemWriteCmd(SPEAKER_SEL_ADDR, [SPEAKER_SEL_A])
cmdAmpSpkB           = AmpCmd.AmpMemWriteCmd(SPEAKER_SEL_ADDR, [SPEAKER_SEL_B])
cmdAmpSpkAB          = AmpCmd.AmpMemWriteCmd(SPEAKER_SEL_ADDR, [SPEAKER_SEL_AB])
cmdAmpNightOff       = AmpCmd.AmpMemWriteCmd(NIGHT_MODE, [0])
cmdAmpNightOn        = AmpCmd.AmpMemWriteCmd(NIGHT_MODE, [1])



################################################################################
class AmpCtrl(threading.Thread):
    def genCrc(self, data):
        checkSum = len(data)
        for x in data:
            checkSum = checkSum + x
        return (256 - checkSum) & 0xFF


    def sendCmd(self, cmd):
        expectedResp = cmd.expResp        
        cmdData      = cmd.data()
        if self.verbose:
            print(":".join("{0:x}".format(c) for c in cmdData))
        # keep trying to write out the command until we get the expected
        # responce
        for i in range(RETRY_LIMIT):
            self.amp.write(cmdData)
            # if there is an expected responce, check that we recieved it
            ok = True
            expectedRespLen = len(expectedResp)
            if expectedRespLen != 0:
                resp = self.amp.read(expectedRespLen)
                ok   = bytes(expectedResp) == resp
                if self.verbose and not ok:
                    print("invalid responce " + (":".join("{0:x}".format(c) for c in resp)))
            # if everything is ok then get out of this retry loop now, if
            # not then we sleep for a bit to let any other responce data
            # come back and then flush it as it's not what we excepted and
            # we don't know its length. This leaves the buffer clean for the
            # next try.
            if ok:
                break
            else:
                time.sleep(CMD_FAIL_RECOVERY_TIME)
                self.amp.flushInput()


    def recieveData(self, txCmd):
        # keep trying to write out the command until we get the expected
        # responce
        rxCmd = None
        for i in range(RETRY_LIMIT):
            # request the status from the amp, then read the responce
            self.sendCmd(txCmd)
            # read in the header
            resp   = self.amp.read(2)
            ok     = len(resp) == 2
            if ok:
                ok     = ok and (resp[0] == 2)
                length = resp[1]
            # now read in the rest of the message now that we have the length
            # from the header
            if ok:
                byteData = self.amp.read(length + 1)
                ok       = length == (len(byteData) - 1)
                if ok:
                    rxCmd = AmpCmd.AmpCmdFromData(byteData)
                    ok    = rxCmd != None
                
            # if still ok break out of the retry look, otherwise wait for a bit,
            # flush the buffer and try again.
            if ok:
                break
            else:
                time.sleep(CMD_FAIL_RECOVERY_TIME)
                self.amp.flushInput()
        return rxCmd
   

    def pollStatus(self):
        # get the data for all zones
        for curZone in range(0, NUM_ZONES):
            txCmd = AmpCmd(PDC_AMP, STATUS_REQ, zone=curZone)
            rxCmd = self.recieveData(txCmd)
            fix_me
            if (len(data) == 7) and (data[2] == curZone):
                # Do we have valid data to compare against
                newPwr = data[5] & 1
                if self.statusDataValid[curZone]:
                    prevPwr = self.prevStatData[curZone][5] & 1
                    sendCmd = newPwr != prevPwr
                else:
                    sendCmd = True
                if sendCmd:
                    cmd = AmpCmd(PDC_AMP, PWR_CTRL_CMD, [newPwr], [OK_RESP], curZone)
                    self.rxCmdQueue.put(cmd)

                self.prevStatData[curZone]    = data
                self.statusDataValid[curZone] = True


    def __init__(self, verbose, port, rxCmdQueue, txCmdQueue, run=True):
        threading.Thread.__init__(self)
        self.verbose         = verbose
        self.port            = port
        self.rxCmdQueue      = rxCmdQueue
        self.txCmdQueue      = txCmdQueue
        self.running         = True
        self.statusDataValid = []
        self.prevStatData    = []
        self.amp             = serial.Serial(port=self.port, timeout=1, baudrate=9600)
        for curZone in range(0, NUM_ZONES):
            self.prevStatData.append([])
            self.statusDataValid.append(False)
        if run:
            self.start()


    def run(self):
        while self.running:
            if not self.txCmdQueue.empty():
                cmd = self.txCmdQueue.get()
                self.sendCmd(cmd)
            else:
                time.sleep(IDLE_DELAY);
            self.pollStatus()

        self.amp.close()


    def close(self):
        self.running = False



################################################################################
if __name__ == "__main__":
    # get the args
    def autoInt(x):
        return int(x, 0)
    parser = argparse.ArgumentParser(description='Sony AV reciever controller')
    parser.add_argument('-P', '--port', dest='port', action='store',
                        default='/dev/ttyUSB0', help='Serial port the amp')
    parser.add_argument('-d', '--dump', action="store_true",
                        help='Dumps the internal memory values of the amp')
    parser.add_argument('-a', '--addr', action='store', default='-1',
                        type=autoInt, help='The memory address to read or write to')
    parser.add_argument('-v', '--val', action='store', default='-1',
                        type=autoInt, help='The value to write to a register or to memory. If this argument is not specified the address is read from.')
    parser.add_argument('-p', '--pdc', action='store', default='-1',
                        type=autoInt, help='The register PDC to read or write from.')
    parser.add_argument('-c', '--cmd', action='store', default='-1',
                        type=autoInt, help='The register command to read or write from.')
    parser.add_argument('-z', '--zone', action='store', default=None,
                        type=autoInt, help='The zone to use with a register access')

    args = parser.parse_args()

    # create the queues we use to connect the different threads
    rxCmdQueue = queue.Queue()
    txCmdQueue = queue.Queue()

    # new create the components
    amp = AmpCtrl(True, args.port, rxCmdQueue, txCmdQueue, False)

    def printMemData(cmd):
        # remove the header from the data
        addr = cmd.memAddr()
        data = cmd.memData()
        for idx in range(0,len(data)):
            print("addr %d val %d" %(addr+idx,data[idx]))

    # if there a register access to perfrom
    if args.pdc >= 0 and args.cmd >= 0:
        if args.val >= 0:
            cmd = AmpCmd(args.pdc, args.cmd, [args.val], [OK_RESP], args.zone)
            amp.sendCmd(cmd)
        else:
            cmd  = AmpCmd(args.pdc, args.cmd, zone=args.zone)
            data = amp.recieveData(cmd)            
            print(data)

    # is there a memory access to perform
    if args.addr >= 0:
        if args.val >= 0:
            cmd = AmpCmd.AmpMemWriteCmd(args.addr, [args.val])
            amp.sendCmd(cmd)
        else:
            cmd  = AmpCmd.AmpMemReadCmd(args.addr, 1)
            data = amp.recieveData(cmd)
            printMemData(data)

    # Dump the amp control memory
    amp.verbose = False
    size        = 64
    if args.dump:
        for addr in range(0, 3584, size):
            cmd  = AmpCmd.AmpMemReadCmd(addr, size)
            data = amp.recieveData(cmd)
            printMemData(data)

    amp.close()