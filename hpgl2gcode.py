import re
import sys

SCALE_NONE = 0
SCALE_DOWN_ONLY = 1
SCALE_BEST = 2

class Command(object):
    INIT = 0
    MOVE_PENUP = 1
    MOVE_PENDOWN = 2
    def __init__(self, command, point=None):
        self.command = command
        self.point = point
        
    def __repr__(self):
        return str(self.command)+','+str(self.point)
        
class Plotter(object):
    def __init__(self, xyMin=(0.,0.), xyMax=(200.,200.)):
        self.xyMin = xyMin
        self.xyMax = xyMax
        
    def inRange(self, point):
        for i in range(2):
            if point[i] < self.xyMin[i] or point[i] > self.xyMax[i]:
                return False
        return True
        

class Scale(object):
    def __init__(self, offset=(0.,0.), scale=(0.,0.)):
        self.offset = offset
        self.scale = scale
        
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
        
def emitGcode(commands, penDownZ = 13.8, penUpZ = 20, scale = Scale(), 
        fastSpeed = 50, penDownSpeed = 35, penUpSpeed = 40, pauses=True, plotter=Plotter(), autoScale=SCALE_NONE,
        pause = False):

    xyMin = [float("inf"),float("inf")]
    xyMax = [float("-inf"),float("-inf")]
    
    allFit = False
    
    for c in commands:
        if c.point is not None:
            if not plotter.inRange(scale.scalePoint(c.point)):
                allFit = False
            for i in range(2):
                xyMin[i] = min(xyMin[i], c.point[i])
                xyMax[i] = max(xyMax[i], c.point[i])
    
    if autoScale == SCALE_NONE:
        if not allFit:
            sys.stderr.write("Drawing out of range.")
            return None
    elif autoScale != SCALE_DOWN_ONLY or not allFit:
        if xyMin[0] > xyMax[0]:
            sys.stderr.write("No points.")
            return None
        scale = Scale()
        scale.fit(plotter, xyMin, xyMax)
        
    gcode = []
    penDown = None
    
    gcode.append('G0 S1 E0')
    gcode.append('G1 S1 E0')
    gcode.append('G21 (millimeters)')

    gcode.append('G28 (Home)')
    penDown = False
    gcode.append('G1 Z%.3f (pen up)' % penUpZ)
    gcode.append('G1 F%.1f Y%.3f' % (fastSpeed,plotter.xyMin[1]))
    gcode.append('G1 F%.1f X%.3f' % (fastSpeed,plotter.xyMin[0]))
    

    for c in commands:
        if c.command == Command.MOVE_PENUP:
            if penDown is not False:
                gcode.append('G0 Z%.3f (pen up)' % penUpZ)
                penDown = False
            if c.point is not None:
                s = scale.scalePoint(c.point)
                gcode.append('G1 F%.1f X%.3f Y%.3f' % (penUpSpeed*60., s[0], s[1]))
        elif c.command == Command.MOVE_PENDOWN:
            if penDown is not True:
                gcode.append('G1 Z%.3f (pen down)' % penDownZ)
                penDown = True
            if c.point is not None:
                s = scale.scalePoint(c.point)
                gcode.append('G1 F%.1f X%.3f Y%.3f' % (penDownSpeed*60., s[0], s[1]))
    if penDown is not False:
        gcode.append('G0 Z%.3f (pen up)' % penUpZ)
    return ('\n@pause\n' if pause else '\n').join(gcode)
    
def parseHPGL(file):
    commands = []
    with open(file, 'r') as f:
        for cmd in re.sub(r'\s',r'',f.read()).split(';'):
            if cmd.startswith('PD'):
                try:
                    x,y = map(float, cmd[2:].split(',',2))
                    commands.append(Command(Command.MOVE_PENDOWN, point=(x/40., y/40.)))
                except:
                    commands.append(Command(Command.MOVE_PENDOWN))
            elif cmd.startswith('PU'):
                try:
                    x,y = map(float, cmd[2:].split(',',2))
                    commands.append(Command(Command.MOVE_PENUP, point=(x/40., y/40.)))
                except:
                    commands.append(Command(Command.MOVE_PENUP))
            elif cmd.startswith('IN'):
                commands.append(Command(Command.INIT))
            elif len(cmd) > 0:
                sys.stderr.write('Unknown command '+cmd+'\n')
    return commands
    
if __name__ == '__main__':
    plotter = Plotter(xyMin=(60.,20.),xyMax=(160.,120.))
    drawing = emitGcode(parseHPGL(sys.argv[1]), autoScale=SCALE_BEST, pause=False, plotter=plotter)
    if drawing is not None:
        print(drawing)
       