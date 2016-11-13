import serial
import time
import threading
import os
import re

def sendGcode(port, commands, speed=115200, quiet = False):    
    class State(object):
        pass
        
    state = State()
    state.cmd = None
    state.done = False
    
#    print('Type s<ENTER> to stop and p<ENTER> to pause.')
    
#    def pauseThread():
#        while not state.done:
#            state.cmd = raw_input().strip()
            
#    threading.Thread(target = pauseThread).start()
    
    def checksum(s):
        cs = 0
        for c in s:
            cs ^= ord(c)
        return cs & 0xFF
    
    s = serial.Serial(port, 115200)
    s.flushInput()
    
    lineNumber = 1
    s.write('\nM110 N1\n')

## TODO: flow control    
    lineNumber = 2
    for c in commands:
        c = re.sub(r'\s*\;.*',r'', c.strip())
        if len(c):
            command = 'N' + str(lineNumber) + ' ' + c
            command += '*' + str(checksum(command))
            s.write(command+'\n')
            print(command)
    #        sys.stderr.write(command+'\n')
    #        n = s.inWaiting()
            s.flushInput()
            lineNumber += 1
#        sys.stderr.write(s.read(n))
    """
        time.sleep(0.1)
        if state.cmd is not None:
            if state.cmd == '':
                print('Terminating.')
                state.done = True
                os._exit(0)
            elif state.cmd == 'p':
                print('Press enter to resume.')
                state.cmd = None
                while state.cmd is None:
                    time.sleep(0.1)
                print('Resuming.')
            state.cmd = None
    """            
    s.close()
    
if __name__ == '__main__':
    import sys
    sendGcode(port=sys.argv[2], commands=open(sys.argv[1], 'r').readlines())
    