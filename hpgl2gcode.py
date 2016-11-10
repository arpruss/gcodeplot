#!/usr/bin/python
import re
import sys
import getopt
import math

SCALE_NONE = 0
SCALE_DOWN_ONLY = 1
SCALE_BEST = 2

class Command(object):
    INIT = 0
    MOVE_PEN_UP = 1
    MOVE_PEN_DOWN = 2
    def __init__(self, command, point=None):
        self.command = command
        self.point = point
        
    def __repr__(self):
        return '('+str(self.command)+','+str(self.point)+')'
        
class Plotter(object):
    def __init__(self, xyMin=(0.,0.), xyMax=(200.,200.), 
            drawSpeed=35, moveSpeed=40, fastMoveSpeed=50, zSpeed=6, penDownZ = 13.8, penUpZ = 20):
        self.xyMin = xyMin
        self.xyMax = xyMax
        self.drawSpeed = drawSpeed
        self.moveSpeed = moveSpeed
        self.fastMoveSpeed = fastMoveSpeed
        self.penDownZ = penDownZ
        self.penUpZ = penUpZ
        self.zSpeed = zSpeed # currently only for measuring
        
    def inRange(self, point):
        for i in range(2):
            if point[i] < self.xyMin[i] or point[i] > self.xyMax[i]:
                return False
        return True
        

class Scale(object):
    def __init__(self, scale=(1.,1.), offset=(0.,0.)):
        self.offset = offset
        self.scale = scale
        
    def __repr__(self):
        return str(self.scale)+','+str(self.offset)

    def fit(self, plotter, xyMin, xyMax):
        s = [0,0]
        o = [0,0]
        for i in range(2):
            delta = xyMax[i]-xyMin[i]
            if delta == 0:
                s[i] = 1.
            else:
                s[i] = (plotter.xyMax[i]-plotter.xyMin[i]) / delta
        self.scale = (min(s),min(s))
        self.offset = tuple(plotter.xyMin[i] - s[i]*xyMin[i] for i in range(2))
        
    def scalePoint(self, point):
        return (point[0]*self.scale[0]+self.offset[0], point[1]*self.scale[1]+self.offset[1])

def dedup(commands):
    newCommands = []
    curPoint = None
    draws = set()
    
    dups = 0
    cons = 0
    
    def d2(a,b):
        return (a[0]-b[0])**2+(a[1]-b[1])**2
    
    for c in commands:
        if c.command == Command.MOVE_PEN_DOWN and curPoint is not None:
            draw = (curPoint, c.point)
            if draw in draws or (c.point, curPoint) in draws:
                dups += 1
                c = Command(Command.MOVE_PEN_UP, point=c.point) 
            else:
                draws.add(draw)

        if (c.command == Command.MOVE_PEN_UP and len(newCommands) > 0 and 
                newCommands[-1].command == Command.MOVE_PEN_UP):
            cons += 1
            newCommands[-1] = c
        else:
            newCommands.append(c)
            
        if c.point is not None and (c.command == Command.MOVE_PEN_DOWN or c.command == Command.MOVE_PEN_UP):
            curPoint = c.point

    return newCommands
        
def emitGcode(commands, scale = Scale(), plotter=Plotter(), scalingMode=SCALE_NONE, tolerance = 0, pause = False):

    xyMin = [float("inf"),float("inf")]
    xyMax = [float("-inf"),float("-inf")]
    
    allFit = True
    
    for c in commands:
        if c.point is not None:
            if not plotter.inRange(scale.scalePoint(c.point)):
                allFit = False
            for i in range(2):
                xyMin[i] = min(xyMin[i], c.point[i])
                xyMax[i] = max(xyMax[i], c.point[i])
    
    if scalingMode == SCALE_NONE:
        if not allFit:
            sys.stderr.write("Drawing out of range.")
            return None
    elif scalingMode != SCALE_DOWN_ONLY or not allFit:
        if xyMin[0] > xyMax[0]:
            sys.stderr.write("No points.")
            return None
        scale = Scale()
        scale.fit(plotter, xyMin, xyMax)
        
    gcode = []

    gcode.append('G0 S1 E0')
    gcode.append('G1 S1 E0')
    gcode.append('G21 (millimeters)')

    gcode.append('G28 (Home)')
    gcode.append('G1 Z%.3f (pen up)' % plotter.penUpZ)

    gcode.append('G1 F%.1f Y%.3f' % (plotter.fastMoveSpeed,plotter.xyMin[1]))
    gcode.append('G1 F%.1f X%.3f' % (plotter.fastMoveSpeed,plotter.xyMin[0]))
    
    class State(object):
        pass
        
    state = State()
    state.curXY = plotter.xyMin
    state.time = (plotter.xyMin[1]+plotter.xyMin[0]) / plotter.fastMoveSpeed
    state.penDown = False
    
    def distance(a,b):
        return math.hypot(a[0]-b[0],a[1]-b[1])
    
    def penUp():
        if state.penDown is not False:
            gcode.append('G0 Z%.3f (pen up)' % plotter.penUpZ)
            state.time += abs(plotter.penUpZ-plotter.penDownZ) / plotter.zSpeed
            state.penDown = False
        
    def penDown():
        if state.penDown is not True:
            gcode.append('G0 Z%.3f (pen down)' % plotter.penDownZ)
            state.time += abs(plotter.penUpZ-plotter.penDownZ) / plotter.zSpeed
            state.penDown = True

    def penMove(down, speed, p):
        d = distance(state.curXY, p)
        if d > tolerance:
            if (down):
                penDown()
            else:
                penUp()
            gcode.append('G1 F%.1f X%.3f Y%.3f' % (speed*60., p[0], p[1]))
            state.curXY = p
            state.time += d / speed

    for c in commands:
        if c.command == Command.MOVE_PEN_UP:
            penMove(False, plotter.moveSpeed, scale.scalePoint(c.point))
        elif c.command == Command.MOVE_PEN_DOWN:
            penMove(True, plotter.drawSpeed, scale.scalePoint(c.point))

    penUp()
    
    sys.stderr.write('Estimated time %dm %.1fs\n' % (state.time // 60, state.time % 60))
    
    return ('\n@pause\n' if pause else '\n').join(gcode)
    
def parseHPGL(file,dpi=(1016.,1016.)):
    try:
        scale = (254./dpi[0], 254./dpi[1])
    except:
        scale = (254./dpi, 254./dpi)

    commands = []
    with open(file, 'r') as f:
        for cmd in re.sub(r'\s',r'',f.read()).split(';'):
            if cmd.startswith('PD'):
                try:
                    coords = map(float, cmd[2:].split(','))
                    for i in range(0,len(coords),2):
                        commands.append(Command(Command.MOVE_PEN_DOWN, point=(coords[i]*scale[0], coords[i+1]*scale[1])))
                except:
                    pass 
                    # ignore no-movement PD/PU
            elif cmd.startswith('PU'):
                try:
                    coords = map(float, cmd[2:].split(','))
                    for i in range(0,len(coords),2):
                        commands.append(Command(Command.MOVE_PEN_UP, point=(coords[i]*scale[0], coords[i+1]*scale[1])))
                except:
                    pass 
                    # ignore no-movement PD/PU
            elif cmd.startswith('IN'):
                commands.append(Command(Command.INIT))
            elif len(cmd) > 0:
                sys.stderr.write('Unknown command '+cmd+'\n')
    return commands
    
if __name__ == '__main__':
    try:
        opts, args = getopt.getopt(sys.argv[1:], "rfdma:D:t:", ["--allow-repeats", "--scale-to-fit",
                        "--scale-down", "--scale-manual", "--area=", '--input-dpi=', '--tolerance='], )
        if len(args) != 1:
            raise getopt.GetoptError("invalid commandline")

        tolerance = 0
        doDedup = True    
        scale = Scale()
        scalingMode = SCALE_BEST
        plotter = Plotter(xyMin=(60.,20.),xyMax=(160.,120.))
        dpi = (1016., 1016.)
            
        for opt,arg in opts:
            if opt in ('-r','--allow-repeats'):
                doDedup = False
            elif opt in ('-f','--scale-to-fit'):
                scalingMode = SCALE_BEST
            elif opt in ('-d','--scale-down'):
                scalingMode = SCALE_DOWN_ONLY
            elif opt in ('-m','--scale-manual'):
                scalingMode = SCALE_NONE
            elif opt in ('-t', '--tolerance'):
                tolerance = float(arg)
            elif opt in ('-a','--area'):
                v = map(float, arg.split(','))
                plotter.xyMin = (v[0],v[1])
                plotter.xyMax = (v[2],v[3])
            elif opt in ('-D','--input-dpi'):
                v = map(float, arg.split(','))
                if len(v) > 1:
                    dpi = v[0:2]
                else:
                    dpi = (v[0],v[0])
        
    except getopt.GetoptError:
        print("hpgl2gcode.py [options] inputfile > output.gcode")
        print("""
 -r|--allow-repeats: do not deduplicate paths [default: off]
 -f|--scale-to-fit: scale to fit plotter area [default]
 -d|--scale-down: scale to fit plotter area only if too big
 -m|--scale-manual: no scaling
 -a|--area=x1,y1,x2,y2: print area in millimeters [default: 0,0,200,200]
 -D|--input-dpi=xdpi[,ydpi]: hpgl dpi
 -t|--toerance=x: skip moves of x millimeters or less
""")
        sys.exit(2)
        
    commands = parseHPGL(args[0], dpi=dpi)
    if doDedup:
        commands = dedup(commands)
    drawing = emitGcode(dedup(commands), scale=scale, scalingMode=scalingMode, pause=False, tolerance=tolerance, plotter=plotter)
    if drawing is not None:
        print(drawing)

       