from __future__ import print_function
import serial
import time
import os
import re
import sys

def sendHPGL(port, commands):
    s = serial.Serial(port, 115200)
    s.flushInput()
    s.write(commands)
    s.close()

def sendGcode(port, commands, speed=115200, quiet = False, gcodePause="@pause"):    
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

    s = serial.Serial(port, 115200)
    s.flushInput()
#    s = open(port, 'w')
    
    lineNumber = 1
    s.write('\nM110 N1\n')

## TODO: flow control    
    lineNumber = 2

    def sendCommand(c):
        def checksum(text):
            cs = 0
            for c in text:
                cs ^= ord(c)
            return cs & 0xFF
    
        c = re.sub(r'\s*\;.*',r'', c.strip())
        if len(c):
            command = 'N' + str(lineNumber) + ' ' + c
            command += '*' + str(checksum(command))
            s.write(command+'\n')
            s.flushInput()
            lineNumber += 1
    
    for c in commands:
        c = c.strip()
        if c.startswith(gcodePause):
            print("PAUSE:"+c[len(gcodePause):]+"""
Commands available:
 c[ontinue]
 u[p]
 d[own]
 a[bort]""") 
            sys.stdout.flush()
            while True:
                cmd = raw_input()
                if cmd.startswith('c'):
                    print("Resuming.")
                    break
                elif cmd.startswith('a'):
                    print("Aborting.")
                    s.close()
                    sys.exit(0)
                elif cmd.startswith('u'):
                    print("Pen up.")
                    sendCommand('G0 F%.1f Z%.3f; pen up' % (plotter.zSpeed*60., plotter.penUpZ))
                elif cmd.startswith('d'):
                    print("Pen down.")
                    sendCommand('G0 F%.1f Z%.3f; pen down' % (plotter.zSpeed*60., plotter.penDownZ))
                else:
                    print("Unknown command. Try: c/u/d/a.")
        else:
            sendCommand(c)
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
    