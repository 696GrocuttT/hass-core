import serial
import argparse
import time
import queue
import threading

IRMAN_WATCHDOG_IDLE_COUNT = 5
CMD_REPEAT_FILTER_TIME = 1.5


################################################################################
class IrManCmd:
    def __init__(self, data):
        self.data = data
        self.timeStamp = time.time()

    def __str__(self):
        return "IrManEvent: %s" % self.data

    def __eq__(self, other):
        eq = False
        if isinstance(other, IrManCmd):
            eq = self.data == other.data
        return eq

    def __hash__(self):
        return hash(self.data)

    def repeatOf(self, other):
        return (
            self.__eq__(other)
            and (self.timeStamp + CMD_REPEAT_FILTER_TIME > other.timeStamp)
            and (self.timeStamp - CMD_REPEAT_FILTER_TIME < other.timeStamp)
        )


################################################################################
class IrMan(threading.Thread):
    def __init__(self, port, txQueue):
        threading.Thread.__init__(self)
        self.running = True
        self.txQueue = txQueue
        self.port = port
        self.start()

    def run(self):
        irMan = serial.Serial(port=self.port, timeout=1, baudrate=9600)
        # after the serial port has been opened wait for the IRMan to wake up, then
        # throw away any garbage that has collected in the input buffer
        time.sleep(0.1)
        irMan.flushInput()

        # init the IRMan
        irMan.write(b"IR")
        irMan.read(2)

        idleCount = 0
        prevCmd = IrManCmd("")
        # keep checking for new IR data until told to stop
        while self.running:
            resp = irMan.read(6)
            if len(resp) != 0:
                print(":".join(f"{c:x}" for c in resp))

            # have we got a command or a timeout
            if len(resp) == 6:
                cmd = IrManCmd(":".join(f"{c:x}" for c in resp))
                # skip repeated commands
                if not prevCmd.repeatOf(cmd):
                    self.txQueue.put(cmd)
                prevCmd = cmd
            else:
                # in a sort of watchdog style, flush the buffer if we've had a
                # while of inactivity. This helps keep things in sync
                idleCount += 1
                if idleCount > IRMAN_WATCHDOG_IDLE_COUNT:
                    idleCount = 0
                    irMan.flushInput()

        # clean up
        irMan.close()

    def close(self):
        self.running = False
