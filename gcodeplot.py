#!/usr/bin/python
from __future__ import print_function
import re
import sys
import getopt
import math
import xml.etree.ElementTree as ET
import gcodeplotutils.anneal as anneal
import svgpath.parser as parser
from svgpath.shader import Shader

SCALE_NONE = 0
SCALE_DOWN_ONLY = 1
SCALE_FIT = 2
ALIGN_NONE = 0
ALIGN_BOTTOM = 1
ALIGN_TOP = 2
ALIGN_LEFT = ALIGN_BOTTOM
ALIGN_RIGHT = ALIGN_TOP
ALIGN_CENTER = 3

GCODE_HEADER = ['G90; absolute', 'G0 S1 E0', 'G1 S1 E0', 'G21; millimeters', 'G28; home']

class Plotter(object):
    def __init__(self, xyMin=(10,8), xyMax=(192,150), 
            drawSpeed=35, moveSpeed=40, zSpeed=5, penDownZ = 14.5, penUpZ = 17, safeUpZ = 40):
        self.xyMin = xyMin
        self.xyMax = xyMax
        self.drawSpeed = drawSpeed
        self.moveSpeed = moveSpeed
        self.penDownZ = penDownZ
        self.penUpZ = penUpZ
        self.safeUpZ = safeUpZ
        self.zSpeed = zSpeed
        
    def inRange(self, point):
        for i in range(2):
            if point[i] < self.xyMin[i] or point[i] > self.xyMax[i]:
                return False
        return True

class Pen(object):
    def __init__(self, text):
        text = re.sub(r'\s+', r' ', text.strip())
        self.description = text
        data = text.split(' ', 4)
        if len(data) < 3:
            raise ValueError('Pen parsing error')
        if len(data) < 4:
            data.append('')
        self.pen = int(data[0])
        self.offset = tuple(map(float, re.sub(r'[()]',r'',data[1]).split(',')))
        self.color = parser.rgbFromColor(data[2])
        self.name = data[3]        

class Scale(object):
    def __init__(self, scale=(1.,1.), offset=(0.,0.)):
        self.offset = offset
        self.scale = scale
        
    def clone(self):
        return Scale(scale=self.scale, offset=self.offset)
        
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
        self.offset = tuple(plotter.xyMin[i] - self.scale[i]*xyMin[i] for i in range(2))
        
    def align(self, plotter, xyMin, xyMax, align):
        o = [0,0]
        for i in range(2):
            if align[i] == ALIGN_LEFT:
                o[i] = plotter.xyMin[i] - self.scale[i]*xyMin[i]
            elif align[i] == ALIGN_RIGHT:
                o[i] = plotter.xyMax[i] - self.scale[i]*xyMax[i]
            elif align[i] == ALIGN_NONE:
                o[i] = plotter.xyMin[i]
            elif align[i] == ALIGN_CENTER:
                o[i] = 0.5 * (plotter.xyMin[i] - self.scale[i]*xyMin[i] + plotter.xyMax[i] - self.scale[i]*xyMax[i])            
            else:
                raise ValueError()
        self.offset = tuple(o)
                
        
    def scalePoint(self, point):
        return (point[0]*self.scale[0]+self.offset[0], point[1]*self.scale[1]+self.offset[1])

def removePenBob(data):
    """
    Merge segments with same beginning and end
    """

    outData = {}
    
    for pen in data:
        outSegments = []
        outSegment = []

        for segment in data[pen]:
            if not outSegment:
                outSegment = list(segment)
            elif outSegment[-1] == segment[0]:
                outSegment += segment[1:]
            else:
                outSegments.append(outSegment)
                outSegment = list(segment)
                
        if outSegment:
            outSegments.append(outSegment)
            
        if outSegments:
            outData[pen] = outSegments
        
    return outData
        
def dedup(data):
    curPoint = None
    
    def d2(a,b):
        return (a[0]-b[0])**2+(a[1]-b[1])**2
        
    newData = {}
        
    for pen in data:
        newSegments = []
        newSegment = []
        draws = set()
        
        for segment in data[pen]:
            newSegment = [segment[0]]
            for i in range(1,len(segment)):
                draw = (segment[i-1], segment[i])
                if draw in draws or (segment[i], segment[i-1]) in draws:
                    if len(newSegment)>1:
                        newSegments.append(newSegment)
                    newSegment = [segment[i]]
                else:        
                    draws.add(draw)
                    newSegment.append(segment[i])
            if newSegment:
                newSegments.append(newSegment)
                
        if newSegments:
            newData[pen] = newSegments

    return removePenBob(newData)
    
def describePen(pens, pen):
    if pens is not None and pen in pens:
        return pens[pen].description
    else:
        return str(pen)
    
def emitGcode(data, pens = {}, plotter=Plotter(), scalingMode=SCALE_NONE, align = None, tolerance = 0, gcodePause="@pause", pauseAtStart = False):
    xyMin = [float("inf"),float("inf")]
    xyMax = [float("-inf"),float("-inf")]
    
    allFit = True
    
    scale = Scale()
    scale.offset = (plotter.xyMin[0],plotter.xyMin[1])

    for pen in data:
        for segment in data[pen]:
            for point in segment:
                if not plotter.inRange(scale.scalePoint(point)):
                    allFit = False
                for i in range(2):
                    xyMin[i] = min(xyMin[i], point[i])
                    xyMax[i] = max(xyMax[i], point[i])
    
    if scalingMode == SCALE_NONE:
        if not allFit:
            sys.stderr.write("Drawing out of range: "+str(xyMin)+" "+str(xyMax)+"\n")
            return None
    elif scalingMode != SCALE_DOWN_ONLY or not allFit:
        if xyMin[0] > xyMax[0]:
            sys.stderr.write("No points.\n")
            return None
        scale = Scale()
        scale.fit(plotter, xyMin, xyMax)
        
    if align is not None:
        scale.align(plotter, xyMin, xyMax, align)
        
    gcode = GCODE_HEADER[:]
    
    def park():
        gcode.append('G1 F%.1f Z%.3f; pen park !!Zpark' % (plotter.zSpeed*60., plotter.safeUpZ))

    park()
    gcode.append('G1 F%.1f Y%.3f' % (plotter.moveSpeed*60.,plotter.xyMin[1]))
    gcode.append('G1 F%.1f X%.3f' % (plotter.moveSpeed*60.,plotter.xyMin[0]))
    
    class State(object):
        pass
        
    state = State()
    state.time = (plotter.xyMin[1]+plotter.xyMin[0]) / plotter.moveSpeed
    state.curXY = plotter.xyMin
    state.curZ = plotter.safeUpZ
    
    def distance(a,b):
        return math.hypot(a[0]-b[0],a[1]-b[1])
    
    def penUp():
        if state.curZ is None or state.curZ < plotter.penUpZ:
            gcode.append('G0 F%.1f Z%.3f; pen up !!Zup' % (plotter.zSpeed*60., plotter.penUpZ))
            if state.curZ is not None:
                state.time += abs(plotter.penUpZ-state.curZ) / plotter.zSpeed
            state.curZ = plotter.penUpZ
        
    def penDown():
        if state.curZ is None or state.curZ != plotter.penDownZ:
            gcode.append('G0 F%.1f Z%.3f; pen down !!Zdown' % (plotter.zSpeed*60., plotter.penDownZ))
            state.time += abs(state.curZ-plotter.penDownZ) / plotter.zSpeed
            state.curZ = plotter.penDownZ

    def penMove(down, speed, p):
        if state.curXY is None:
            d = float("inf")
        else:
            d = distance(state.curXY, p)
        if d > tolerance:
            if down:
                penDown()
            else:
                penUp()
            gcode.append('G1 F%.1f X%.3f Y%.3f; %s' % (speed*60., p[0], p[1], "draw" if down else "move"))
            if state.curXY is not None:
                state.time += d / speed
            state.curXY = p
            
    for pen in data:
        if pen is not 1:
            state.curZ = None
            state.curXY = None
            
        s = scale.clone()

        if pens is not None and pen in pens:
            s.offset = (s.offset[0]-pens[pen].offset[0],s.offset[0]-pens[pen].offset[0])

        newPen = True

        for segment in data[pen]:
            penMove(False, plotter.moveSpeed, s.scalePoint(segment[0]))
            
            if newPen and (pen != 1 or pauseAtStart):
                gcode.append( gcodePause+' load pen: ' + describePen(pens,pen) )
            newPen = False
            
            for i in range(1,len(segment)):
                penMove(True, plotter.drawSpeed, s.scalePoint(segment[i]))

    park()
    
    sys.stderr.write('Estimated printing time: %dm %.1fs\n' % (state.time // 60, state.time % 60))
    sys.stderr.flush()

    return gcode
    
def parseHPGL(hpgl,dpi=(1016.,1016.)):
    try:
        scale = (25.4/dpi[0], 25.4/dpi[1])
    except:
        scale = (25.4/dpi, 25.4/dpi)

    segment = []
    pen = 1
    data = {pen:[]}
    
    for cmd in re.sub(r'\s', r'', hpgl).split(';'):
        if cmd.startswith('PD'):
            try:
                coords = list(map(float, cmd[2:].split(',')))
                for i in range(0,len(coords),2):
                    segment.append((coords[i]*scale[0], coords[i+1]*scale[1]))
            except:
                pass
                # ignore no-movement PD/PU
        elif cmd.startswith('PU'):
            try:
                if segment:
                    data[pen].append(segment)
                coords = list(map(float, cmd[2:].split(',')))
                segment = [(coords[-2]*scale[0], coords[-1]*scale[1])]
            except:
                pass 
                # ignore no-movement PD/PU
        elif cmd.startswith('SP'):
            if segment:
                data[pen].append(segment)
                segment = []
                pen = int(cmd[2:])
                if pen not in data:
                    data[pen] = []
        elif cmd.startswith('IN'):
            pass
        elif len(cmd) > 0:
            sys.stderr.write('Unknown command '+cmd[:2]+'\n')
            
    if segment:
        data[pen].append(segment)
        
    return data
    
def emitHPGL(data, pens=None):
    def hpglCoordinates(offset,point):
        x = (point[0]-offset[0]) * 1016. / 25.4
        y = (point[1]-offset[1]) * 1016. / 25.4
        return str(int(round(x)))+','+str(int(round(y)))

    hpgl = []
    hpgl.append('IN')
    for pen in sorted(data):
        if pens is not None and pen in pens:
            offset = pens[pen].offset
        else:
            offset = (0.,0.)
        hpgl.append('SP'+str(pen))
        for segment in data[pen]:
            hpgl.append('PU'+hpglCoordinates(offset,segment[0]))
            for i in range(1,len(segment)):
                hpgl.append('PD'+hpglCoordinates(offset,segment[i]))
    hpgl.append('PU')
    hpgl.append('')
    return ';'.join(hpgl)
    
def getPen(pens, color):
    if pens is None:
        return 1

    if color is None:
        color = (0.,0.,0.)
        
    bestD2 = 10
    bestPen = 1

    for p in pens:
        c = pens[p].color
        d2 = (c[0]-color[0])**2+(c[1]-color[1])**2+(c[2]-color[2])**2
        if d2 < bestD2:
            bestPen = p
            bestD2 = d2
            
    return bestPen

def parseSVG(svgTree, tolerance=0.05, shader=None, strokeAll=False, pens=None):
    data = {}
    for path in parser.getPathsFromSVG(svgTree)[0]:
        lines = []
        
        stroke = strokeAll or path.svgState.stroke is not None
        
        pen = getPen(pens, path.svgState.stroke)

        if pen not in data:
            data[pen] = []
            
        for line in path.linearApproximation(error=tolerance):
            if stroke:
                data[pen].append([(line.start.real,line.start.imag),(line.end.real,line.end.imag)])
            lines.append((line.start, line.end))

        if shader is not None and shader.isActive() and path.svgState.fill is not None:
            pen = getPen(pens, path.svgState.fill)
            
            if pen not in data:
                data[pen] = []
        
            grayscale = sum(path.svgState.fill) / 3. 
            mode = Shader.MODE_NONZERO if path.svgState.fillRule == 'nonzero' else Shader.MODE_EVEN_ODD
            if path.svgState.fillOpacity is not None:
                grayscale = grayscale * path.svgState.fillOpacity + 1. - path.svgState.fillOpacity # TODO: real alpha!
            fillLines = shader.shade(lines, grayscale, avoidOutline=(path.svgState.stroke is None), mode=mode)
            for line in fillLines:
                data[pen].append([(line[0].real,line[0].imag),(line[1].real,line[1].imag)])

    return data
    
def getConfigOpts(filename):
    opts = []
    with open(filename) as f:
        for line in f:
            l = line.strip()
            if len(l) and l[0] != '#':
                entry = l.split('=', 2)
                opt = entry[0]
                if len(opt) == 1:
                    opt = '-' + opt
                elif opt[0] != '-':
                    opt = '--' + opt
                if len(entry) > 1:
                    arg = entry[1]
                    if arg[0] in ('"', "'"):
                        arg = arg[1:-1]
                else:
                    arg = None
                opts.append( (opt,arg) )
    return opts
    
if __name__ == '__main__':

    def help():
        sys.stdout.write("gcodeplot.py [options] [inputfile [> output.gcode]\n")
        sys.stdout.write("""
 -h|--help: this
 -r|--allow-repeats*: do not deduplicate paths
 -f|--scale=mode: scaling option: none(n), fit(f), down-only(d) [default none]
 -D|--input-dpi=xdpi[,ydpi]: hpgl dpi
 -t|--tolerance=x: ignore (some) deviations of x millimeters or less [default 0.05]
 -s|--send=port*: send gcode to serial port instead of stdout
 -S|--send-speed=baud: set baud rate for sending
 -x|--align-x=mode: horizontal alignment: none(n), left(l), right(r) or center(c)
 -y|--align-y=mode: vertical alignment: none(n), bottom(b), top(t) or center(c)
 -a|--area=x1,y1,x2,y2: gcode print area in millimeters
 -Z|--pen-up-z=z: z-position for pen-up (millimeters)
 -z|--pen-down-z=z: z-position for pen-down (millimeters)
 -p|--parking-z=z: z-position for parking (millimeters)
 -Z|--pen-up-z=z: z-position for pen-up (millimeters)
 -z|--pen-down-z=z: z-position for pen-down (millimeters)
 -Z|--pen-up-speed=z: speed for moving with pen up (millimeters/second)
 -z|--pen-down-speed=z: speed for moving with pen down (millimeters/second)
 -u|--z-speed=s: speed for up/down movement (millimeters/second)
 -H|--hpgl-out*: output is HPGL, not gcode; most options ignored [default: off]
 -T|--shading-threshold=n: darkest grayscale to leave unshaded (decimal, 0. to 1.; set to 0 to turn off SVG shading) [default 1.0]
 -m|--shading-lightest=x: shading spacing for lightest colors (millimeters) [default 3.0]
 -M|--shading-darkest=x: shading spacing for darkest color (millimeters) [default 0.5]
 -A|--shading-angle=x: shading angle (degrees) [default 45]
 -X|--shading-crosshatch*: cross hatch shading
 -L|--stroke-all*: stroke even regions specified by SVG to have no stroke
 -O|--shading-avoid-outline*: avoid going over outline twice when shading
 -o|--optimize-timeout=t: timeout on optimization attempt (seconds; will be retried once; set to 0 to turn off optimization) [default 30]
 -c|--config-file=filename: read arguments, one per line, from filename
 -w|--gcode-pause=cmd: gcode pause command [default: @pause]
 -P|--pens=penfile: read output pens from penfile
 -U|--pause-at-start*: pause at start (can be included without any input file to manually move stuff)
 
 The options with an asterisk are default off and can be turned off again by adding "no-" at the beginning to the long-form option, e.g., --no-stroke-all or --no-send.
""")
    

    tolerance = 0.05
    doDedup = True    
    sendPort = None
    sendSpeed = 115200
    hpglLength = 279.4
    scalingMode = SCALE_NONE
    shader = Shader()
    align = [ALIGN_NONE, ALIGN_NONE]
    plotter = Plotter()
    hpglOut = False
    strokeAll = False
    gcodePause = "@pause"
    optimizationTimeOut = 30
    dpi = (1016., 1016.)
    pens = {1:Pen('1 (0.,0.) black default')}
    doDump = False
    penFilename = None
    pauseAtStart = False
    
    try:
        opts, args = getopt.getopt(sys.argv[1:], "Uhdulw:P:o:Oc:LT:M:m:A:XHrf:dna:D:t:s:S:x:y:z:Z:p:f:F:", 
                        ["help", "down", "up", "lower-left", "allow-repeats", "no-allow-repeats", "scale=", "config-file=",
                        "area=", 'align-x=', 'align-y=', 'optimize-timeout=', "pens=",
                        'input-dpi=', 'tolerance=', 'send=', 'send-speed=', 'pen-down-z=', 'pen-up-z=', 'parking-z=',
                        'pen-down-speed=', 'pen-up-speed=', 'z-speed=', 'hpgl-out', 'no-hpgl-out', 'shading-threshold=',
                        'shading-angle=', 'shading-crosshatch', 'no-shading-crosshatch', 'shading-avoid-outline', 
                        'pause-at-start', 'no-pause-at-start', 'min-x=', 'max-x=', 'min-y=', 'max-y=',
                        'no-shading-avoid-outline', 'shading-darkest=', 'shading-lightest=', 'stroke-all', 'no-stroke-all', 'gcode-pause', 'dump-options', 'tab='], )

        if len(args) + len(opts) == 0:
            raise getopt.GetoptError("invalid commandline")

        i = 0
        while i < len(opts):
            opt,arg = opts[i]
            if opt in ('-r', '--allow-repeats'):
                doDedup = False
            elif opt == '--no-allow-repeats':
                doDedup = True
            elif opt in ('-w', '--gcode-pause'):
                gcodePause = arg
            elif opt in ('-p', '--pens'):
                pens = {}
                penFilename = arg
                with open(arg) as f:
                    for line in f:
                        if line.strip():
                            p = Pen(line)
                            pens[p.pen] = p                            
            elif opt in ('-f', '--scale'):
                if arg.startswith('n'):
                    scalingMode = SCALE_NONE
                elif arg.startswith('d'):
                    scalingMode = SCALE_DOWN_ONLY
                elif arg.startswith('f'):
                    scalingMode = SCALE_FIT
            elif opt in ('-x', '--align-x'):
                if arg.startswith('l'):
                    align[0] = ALIGN_LEFT
                elif arg.startswith('r'):
                    align[0] = ALIGN_RIGHT
                elif arg.startswith('c'):
                    align[0] = ALIGN_CENTER
                elif arg.startswith('n'):
                    align[0] = ALIGN_NONE
                else:
                    raise ValueError()
            elif opt in ('-y', '--align-y'):
                if arg.startswith('b'):
                    align[1] = ALIGN_LEFT
                elif arg.startswith('t'):
                    align[1] = ALIGN_RIGHT
                elif arg.startswith('c'):
                    align[1] = ALIGN_CENTER
                elif arg.startswith('n'):
                    align[1] = ALIGN_NONE
                else:
                    raise ValueError()
            elif opt in ('-t', '--tolerance'):
                tolerance = float(arg)
            elif opt in ('-s', '--send'):
                sendPort = arg
            elif opt == '--no-send':
                sendPort = None
            elif opt in ('-S', '--send-speed'):
                sendSpeed = int(arg)
            elif opt in ('-a', '--area'):
                v = list(map(float, arg.split(',')))
                plotter.xyMin = (v[0],v[1])
                plotter.xyMax = (v[2],v[3])
            elif opt == '--min-x':
                plotter.xyMin = (float(arg),plotter.xyMin[1])
            elif opt == '--min-y':
                plotter.xyMin = (plotter.xyMin[0],float(arg))
            elif opt == '--max-x':
                plotter.xyMax = (float(arg),plotter.xyMax[1])
            elif opt == '--max-y':
                plotter.xyMax = (plotter.xyMax[0],float(arg))
            elif opt in ('-D', '--input-dpi'):
                v = list(map(float, arg.split(',')))
                if len(v) > 1:
                    dpi = v[0:2]
                else:
                    dpi = (v[0],v[0])
            elif opt in ('-Z', '--pen-up-z'):
                plotter.penUpZ = float(arg)
            elif opt in ('-z', '--pen-down-z'):
                plotter.penDownZ = float(arg)
            elif opt in ('-p', '--parking-z'):
                plotter.safeUpZ = float(arg)
            elif opt in ('-F', '--pen-up-speed'):
                plotter.moveSpeed = float(arg)
            elif opt in ('-f', '--pen-down-speed'):
                plotter.drawSpeed = float(arg)
            elif opt in ('-u', '--z-speed'):
                plotter.zSpeed = float(arg)
            elif opt in ('-H', '--hpgl-out'):
                hpglOut = True
            elif opt == '--no-hpgl-out':
                hpglOut = False
            elif opt in ('-T', '--shading-threshold'):
                shader.unshadedThreshold = float(arg)
            elif opt in ('-m', '--shading-lightest'):
                shader.lightestSpacing = float(arg)
            elif opt in ('-M', '--shading-darkest'):
                shader.darkestSpacing = float(arg)
            elif opt in ('-A', '--shading-angle'):
                shader.angle = float(arg)
            elif opt in ('-X', '--shading-crosshatch'):
                shader.crossHatch = True
            elif opt == '--no-shading-crosshatch':
                shader.crossHatch = False
            elif opt in ('-O', '--shading-avoid-outline'):
                avoidOutline = True
            elif opt == '--no-shading-avoid-outline':
                avoidOutline = False
            elif opt == '--no-shading-crosshatch':
                shader.crossHatch = False
            elif opt == '--pause-at-start':
                pauseAtStart = True
            elif opt == '--no-pause-at-start':
                pauseAtStart = False
            elif opt in ('-L', '--stroke-all'):
                strokeAll = True
            elif opt == '--no-stroke-all':
                strokeAll = False
            elif opt in ('-c', '--config-file'):
                configOpts = getConfigOpts(arg)
                opts = opts[:i+1] + configOpts + opts[i+1:]
            elif opt in ('-o', '--optimization-timeout'):
                optimizationTimeOut = float(arg)
            elif opt in ('-h', '--help'):
                help()
                sys.exit(0)
            elif opt == '--dump-options':
                doDump = True
            elif opt == '--tab':
                pass # Inkscape
            else:
                raise ValueError("Unrecognized argument "+opt)
            i += 1
        
    except getopt.GetoptError:
        help()
        sys.exit(2)
        
    if doDump:
        print('no-allow-repeats' if doDedup else 'allow-repeats')
        
        print('gcode-pause=' + gcodePause)
        
        if penFilename is not None:
            print('pens=' + penFilename)

        if scalingMode == SCALE_NONE:
            print('scale=none')
        elif scalingMode == SCALE_DOWN_ONLY:
            print('scale=down')
        else:
            print('scale=fit')
        
        if align[0] == ALIGN_LEFT:
            print('align-x=left')
        elif align[0] == ALIGN_CENTER:
            print('align-x=center')
        elif align[0] == ALIGN_RIGHT:
            print('align-x=right')
        else:
            print('align-x=none')
        
        if align[1] == ALIGN_BOTTOM:
            print('align-y=bottom')
        elif align[1] == ALIGN_CENTER:
            print('align-y=center')
        elif align[1] == ALIGN_TOP:
            print('align-y=top')
        else:
            print('align-y=none')
            
        print('tolerance=' + str(tolerance))
        
        if sendPort is not None:
            print('send=' + str(sendPort))
        else:
            print('no-send')
            
        print('send-speed=' + str(sendSpeed))
        print('area=%g,%g,%g,%g' % tuple(list(plotter.xyMin)+list(plotter.xyMax)))
        print('input-dpi=%g,%g' % tuple(dpi))
        print('pen-up-z=%g' % (plotter.penUpZ))
        print('pen-down-z=%g' % (plotter.penDownZ))
        print('parking-z=%g' % (plotter.safeUpZ))
        print('hpgl-out' if hpglOut else 'no-hpgl-out')        
        print('shading-threshold=%g' % (shader.unshadedThreshold))
        print('shading-lightest=%g' % (shader.lightestSpacing))
        print('shading-darkest=%g' % (shader.darkestSpacing))
        print('shading-angle=%g' % (shader.angle))
        print('shading-crosshatch' if shader.crossHatch else 'no-shading-crosshatch')
        print('stroke-all' if strokeAll else 'no-stroke-all')
        print('optimization-timeout=%g' % (optimizationTimeOut))
        print('pause-at-start' if pauseAtStart else 'no-pause-at-start')
        
        sys.exit(0)
        
    variables = {'up':plotter.penUpZ, 'down':plotter.penDownZ, 'park':plotter.safeUpZ, 'left':plotter.xyMin[0],
        'bottom':plotter.xyMin[1], 'right':plotter.xyMax[0], 'top':plotter.xyMax[1]}
        
    if len(args) == 0:
        if not pauseAtStart:
            help()
        
        if sendPort is None:
            sys.stderr.write("Need to specify --send=port to be able to pause without any file.")
            sys.exit(1)
        import gcodeplotutils.sendgcode as sendgcode

        sendgcode.sendGcode(port=sendPort, speed=115200, commands=GCODE_HEADER + [gcodePause], gcodePause=gcodePause, variables=variables)
        sys.exit(0)

    with open(args[0]) as f:
        data = f.read()
        
    svgTree = None    
        
    try:
        svgTree = ET.fromstring(data)
        if not 'svg' in svgTree.tag:
            svgTree = None
    except:
        svgTree = None
        
    if svgTree is None and 'PD' not in data and 'PU' not in data:
        sys.stderr.write("Unrecognized file.\n")
        exit(1)
        
    if svgTree is not None:
        penData = parseSVG(svgTree, tolerance=tolerance, shader=shader, strokeAll=strokeAll, pens=pens)
    else:
        penData = parseHPGL(data, dpi=dpi)
    penData = removePenBob(penData)

    if doDedup:
        penData = dedup(penData)

    if optimizationTimeOut > 0.:
        for pen in penData:
            penData[pen] = anneal.optimize(penData[pen], timeout=optimizationTimeOut)
        penData = removePenBob(penData)
        
    if len(penData) > 1:
        sys.stderr.write("Uses the following pens:\n")
        for pen in penData:
            sys.stderr.write(describePen(pens, pen)+"\n")

    if hpglOut:
        g = emitHPGL(penData, pens=pens)
    else:    
        g = emitGcode(penData, align=align, scalingMode=scalingMode, tolerance=tolerance, 
                plotter=plotter, gcodePause=gcodePause, pens=pens, pauseAtStart=pauseAtStart)

    if g:
        if sendPort is not None:
            import gcodeplotutils.sendgcode as sendgcode
            if hpglOut:
                sendgcode.sendHPGL(port=sendPort, speed=115200, commands=g)
            else:
                sendgcode.sendGcode(port=sendPort, speed=115200, commands=g, gcodePause=gcodePause, plotter=plotter, variables=variables)
        else:    
            if hpglOut:
                sys.stdout.write(g)
            else:
                print('\n'.join(g))
    else:
        sys.stderr.write("No points.")
        sys.exit(1)
       