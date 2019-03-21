from __future__ import print_function
import time
import os
import re
import sys
from .evaluate import *

try:
    from serial import Serial
except:
    if sys.version_info < (2, 7):
        dir = "pyserial27"
    else:
        dir = "pyserial3"
    import inspect
    serialFolder = os.path.abspath(os.path.split(inspect.getfile(inspect.currentframe()))[0] + "/" + dir)
    sys.path.insert(0, serialFolder)
    from serial import Serial

class FakeSerial(object):
    def __init__(self, name):
        if name == 'stdout':
            self.handle = sys.stdout
        elif name == 'stderr':
            self.handle = sys.stderr
        else:
            self.handle = open(name, "w")
        
    def flushInput(self):
        return
        
    def write(self, data):
        self.handle.write(data)
        
    def close(self):
        if self.handle is not sys.stdout:
            self.handle.close()
            
def sendHPGL(port, commands):
    s = Serial(port, 115200)
    s.flushInput()
    s.write(commands)
    s.close()

def sendGcode(port, commands, speed=115200, quiet = False, gcodePause="@pause", plotter=None, variables={}, formulas={}):
    class State(object):
        pass
        
    state = State()
    state.cmd = None
    state.done = False

    if sys.version_info[0] <= 2:
        text_input = raw_input
    else:
        text_input = input
    
    if port.startswith('file:'):
        s = FakeSerial(port[5:])
    else:
        s = Serial(port, 115200)
    s.flushInput()
    
    class State(object):
        pass
        
    state = State()
    state.relative = False
    state.lineNumber = 1

    s.write('\nM110 N1\n')

## TODO: flow control  
    state.lineNumber = 2
    
    def sendCommand(c):
        def checksum(text):
            cs = 0
            for c in text:
                cs ^= ord(c)
            return cs & 0xFF
        components = c.strip().split(';')
        c = components[0].strip()
        
        if len(components) > 1:
            if '!!' in components[1]:
                for subst in re.split(r'\s+', components[1].split('!!', 2)[1].strip()):
                    axis = subst[0]
                    try:
                        value = evaluate(subst[1:],variables,formulas)
                        c = re.sub(r'\b' + axis + r'[0-9.\-]+', '%s%.3f' % (axis, value), c)
                    except ValueError:
                        pass
        if c:
            ## assumes movement is always absolute
            if not state.relative and re.match(r'[Gg][012]\s', c):
                for part in re.split(r'\s+', c.upper()):
                    if re.match(r'X[-.0-9]', part):
                        variables['x'] = float(part[1:])
                    elif re.match(r'Y[-.0-9]', part):
                        variables['y'] = float(part[1:])
                    elif re.match(r'Z[-.0-9]', part):
                        variables['z'] = float(part[1:])
            elif re.match(r'[Gg]91\b', c):
                state.relative = True
                if 'x' in variables: del variables['x']
                if 'y' in variables: del variables['y']
                if 'z' in variables: del variables['z']
            elif re.match(r'[Gg]90\b', c):
                state.relative = False
            elif re.match(r'[Gg]28\b', c):
                if 'x' in variables: del variables['x']
                if 'y' in variables: del variables['y']
                if 'z' in variables: del variables['z']
                            
            command = 'N' + str(state.lineNumber) + ' ' + c
            command += '*' + str(checksum(command))
            s.write(command+'\n')
            s.flushInput()
            state.lineNumber += 1
    
    for c in commands:
        c = c.strip()
        if c.startswith(gcodePause):
            print("PAUSE:"+c[len(gcodePause):]+"""
Commands available:
   c[ontinue]
   a[bort]
   xvalue yvalue zvalue: move absolute
   x+value y+value z+value: move relative
   variable=value
   Gxxx / Mxxx / Txxx: manual gcode command""") 
                
            def showVariables():
                if variables:
                    print("\nCurrent variables:")
                    print('\t'.join(("%s=%.5g" % (var, variables[var]) for var in sorted(variables))))
                if formulas:
                    print("\nCurrent formulas and constants:")
                    out = []
                    for var in sorted(formulas):
                        try:
                            value = float(formulas[var])
                            out.append("%s=%.5g" % (var, value))
                        except ValueError:
                            out.append("%s=%s=%.5g" % (var, formulas[var], evaluate(formulas[var],variables,formulas)))
                    print('\t'.join(out))
                
            showVariables()
                
            while True:
                cmdOriginalCase = text_input("\nCOMMAND: ").strip()
                cmd = cmdOriginalCase.lower()
                if len(cmd) == 0:
                    continue
                if '=' in cmd:
                    try:
                        var,value = re.split(r'\s*=\s*', cmd, maxsplit=2)
                        if var in formulas:
                            raise ValueError()
                        variables[var] = evaluate(value,variables,formulas)
                    except:
                        print("Syntax error.")
                    showVariables()
                elif cmd.startswith('c'):
                    print("Resuming.")
                    break
                elif cmd.startswith('a'):
                    print("Aborting.")
                    s.close()
                    sys.exit(0)
                elif cmdOriginalCase[0] in 'GMT':
                    sendCommand(cmdOriginalCase)
                    showVariables()
                elif re.search('[xyz]', cmd):
                    try:
                        xyMove = ''
                        zMove = ''
                        parts = re.split('\s+', cmd)
                        i = 0
                        while i < len(parts):
                            part = parts[i]
                            if part[0] in 'xyz':
                                if len(part) == 1:
                                    i += 1
                                    if len(parts) <= i:
                                        raise ValueError()
                                    valueString = parts[i]
                                else:
                                    valueString = part[1:]
                                if valueString[0] == '+':
                                    value = variables[part[0]] + evaluate(valueString[1:],variables,formulas)
                                else:
                                    value = evaluate(valueString,variables,formulas)
                                if part[0] == 'z':
                                    zMove = 'G0 F%.1f Z%.3f; pen up' % (600 if plotter is None else plotter.zSpeed*60., value)
                                elif part[0] == 'x':
                                    xyMove += 'X%.3f '%value
                                elif part[0] == 'y':
                                    xyMove += 'Y%.3f '%value
                            else:
                                raise ValueError()
                            i += 1
                    except:
                        print("Syntax error.")
                        showVariables()
                        continue
                    if zMove:
                        sendCommand(zMove)
                    if xyMove:
                        sendCommand('G1 F%.1f %s'%(600 if plotter is None else plotter.moveSpeed*60., xyMove))
                    showVariables()
                else:
                    print("Unknown command.")
        else:
            sendCommand(c)
    s.close()
    
if __name__ == '__main__':
    import sys
    sendGcode(port=sys.argv[2], commands=open(sys.argv[1], 'r').readlines())
    