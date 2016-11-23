#!/usr/bin/python
import re
import sys
import getopt
import math
import xml.etree.ElementTree as ET
import utils.anneal as anneal
from svgpath.parser import getPathsFromSVG 
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

class Plotter(object):
    def __init__(self, xyMin=(10,8), xyMax=(192,150), 
            drawSpeed=35, moveSpeed=40, zSpeed=5, penDownZ = 13.5, penUpZ = 18, safeUpZ = 40):
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

def removePenBob(segments):
    """
    Merge segments with same beginning and end
    """

    outSegments = []
    outSegment = []
    
    for segment in segments:
        if not outSegment:
            outSegment = list(segment)
        elif outSegment[-1] == segment[0]:
            outSegment += segment[1:]
        else:
            outSegments.append(outSegment)
            outSegment = list(segment)
            
    if outSegment:
        outSegments.append(outSegment)
        
    return outSegments
        
def dedup(segments):
    curPoint = None
    draws = set()
    
    def d2(a,b):
        return (a[0]-b[0])**2+(a[1]-b[1])**2
    
    newSegments = []
    newSegment = []
    
    for segment in segments:
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

    return removePenBob(newSegments)
    
def emitGcode(segments, scale = Scale(), plotter=Plotter(), scalingMode=SCALE_NONE, align = None, tolerance = 0):

    xyMin = [float("inf"),float("inf")]
    xyMax = [float("-inf"),float("-inf")]
    
    allFit = True
    
    for segment in segments:
        for point in segment:
            if not plotter.inRange(scale.scalePoint(point)):
                allFit = False
            for i in range(2):
                xyMin[i] = min(xyMin[i], point[i])
                xyMax[i] = max(xyMax[i], point[i])
    
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
        
    if align is not None:
        scale.align(plotter, xyMin, xyMax, align)
        
    gcode = []

    gcode.append('G0 S1 E0')
    gcode.append('G1 S1 E0')
    gcode.append('G21; millimeters')

    gcode.append('G28; home')
    gcode.append('G1 Z%.3f; pen up' % plotter.safeUpZ)

    gcode.append('G1 F%.1f Y%.3f' % (plotter.moveSpeed*60.,plotter.xyMin[1]))
    gcode.append('G1 F%.1f X%.3f' % (plotter.moveSpeed*60.,plotter.xyMin[0]))
    
    class State(object):
        pass
        
    state = State()
    state.curXY = plotter.xyMin
    state.curZ = plotter.safeUpZ
    state.time = (plotter.xyMin[1]+plotter.xyMin[0]) / plotter.moveSpeed
    
    def distance(a,b):
        return math.hypot(a[0]-b[0],a[1]-b[1])
    
    def penUp():
        if state.curZ < plotter.penUpZ:
            gcode.append('G0 F%.1f Z%.3f; pen up' % (plotter.zSpeed*60., plotter.penUpZ))
            state.time += abs(plotter.penUpZ-state.curZ) / plotter.zSpeed
            state.curZ = plotter.penUpZ
        
    def penDown():
        if state.curZ != plotter.penDownZ:
            gcode.append('G0 F%.1f Z%.3f; pen down' % (plotter.zSpeed*60., plotter.penDownZ))
            state.time += abs(state.curZ-plotter.penDownZ) / plotter.zSpeed
            state.curZ = plotter.penDownZ

    def penMove(down, speed, p):
        d = distance(state.curXY, p)
        if d > tolerance:
            if (down):
                penDown()
            else:
                penUp()
            gcode.append('G1 F%.1f X%.3f Y%.3f; draw' % (speed*60., p[0], p[1]))
            state.curXY = p
            state.time += d / speed

    for segment in segments:
        penMove(False, plotter.moveSpeed, scale.scalePoint(segment[0]))
        for i in range(1,len(segment)):
            penMove(True, plotter.drawSpeed, scale.scalePoint(segment[i]))

    penUp()
    
    sys.stderr.write('Estimated time %dm %.1fs\n' % (state.time // 60, state.time % 60))

    return gcode
    
def parseHPGL(data,dpi=(1016.,1016.)):
    try:
        scale = (25.4/dpi[0], 25.4/dpi[1])
    except:
        scale = (25.4/dpi, 25.4/dpi)

    segments = []
    segment = []
    
    sys.stderr.write(str(scale)+"\n")

    for cmd in re.sub(r'\s',r'',data).split(';'):
        if cmd.startswith('PD'):
            try:
                coords = map(float, cmd[2:].split(','))
                for i in range(0,len(coords),2):
                    segment.append((coords[i]*scale[0], coords[i+1]*scale[1]))
            except:
                pass
                # ignore no-movement PD/PU
        elif cmd.startswith('PU'):
            try:
                coords = map(float, cmd[2:].split(','))
                segments.append(segment)
                segment = [(coords[-2]*scale[0], coords[-1]*scale[1])]
            except:
                pass 
                # ignore no-movement PD/PU
        elif cmd.startswith('IN'):
            pass
        elif len(cmd) > 0:
            sys.stderr.write('Unknown command '+cmd[:2]+'\n')
            
    if segment:
        segments.append(segment)
        
    return segments
    
def emitHPGL(segments):

    def hpglCoordinates(point):
        x = point[0] * 1016. / 25.4
        y = point[1] * 1016. / 25.4
        return str(int(round(x)))+','+str(int(round(y)))

    hpgl = []
    hpgl.append('IN')
    for segment in segments:
        hpgl.append('PU'+hpglCoordinates(segment[0]))
        for i in range(1,len(segment)):
            hpgl.append('PD'+hpglCoordinates(segment[i]))
            # TODO: combine PD commands
    hpgl.append('PU')
    hpgl.append('')
    return ';'.join(hpgl)

def parseSVG(svgTree, tolerance=0.05, shader=None, strokeAll=False):
    segments = []
    for path in getPathsFromSVG(svgTree)[0]:
        lines = []
        
        stroke = strokeAll or path.svgState.stroke is not None
        
        for line in path.linearApproximation(error=tolerance):
            if stroke:
                segments.append([(line.start.real,line.start.imag),(line.end.real,line.end.imag)])
            lines.append((line.start, line.end))

        if shader is not None and shader.isActive() and path.svgState.fill is not None:
            grayscale = sum(path.svgState.fill) / 3. 
            mode = Shader.MODE_NONZERO if path.svgState.fillRule == 'nonzero' else Shader.MODE_EVEN_ODD
            if path.svgState.fillOpacity is not None:
                grayscale *= path.svgState.fillOpacity # TODO: real alpha!
            fillLines = shader.shade(lines, grayscale, avoidOutline=(path.svgState.stroke is None), mode=mode)
            for line in fillLines:
                segments.append([(line[0].real,line[0].imag),(line[1].real,line[1].imag)])
 
    return segments
    
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
    tolerance = 0.05
    doDedup = True    
    scale = Scale()
    sendPort = None
    sendSpeed = 115200
    hpglLength = 279.4
    scalingMode = SCALE_FIT
    shader = Shader()
    align = [ALIGN_NONE, ALIGN_NONE]
    plotter = Plotter()
    hpglOut = False
    strokeAll = False
    optimizationTimeOut = 30
    dpi = (1016., 1016.)
    
    try:
        opts, args = getopt.getopt(sys.argv[1:], "o:Oc:LT:M:m:A:XHrf:dna:D:t:s:S:x:y:z:Z:p:f:F:u:", 
                        ["allow-repeats", "no-allow-repeats", "scale=", "config-file=",
                        "area=", 'align-x=', 'align-y=', 'optimize-timeout=', 
                        'input-dpi=', 'tolerance=', 'send=', 'send-speed=', 'pen-down-z=', 'pen-up-z=', 'parking-z=',
                        'pen-down-speed=', 'pen-up-speed=', 'z-speed=', 'hpgl-out', 'no-hpgl-out', 'shading-threshold=',
                        'shading-angle=', 'shading-crosshatch', 'no-shading-crosshatch', 'shading-avoid-outline', 
                        'no-shading-avoid-outline', 'shading-darkest=', 'shading-lightest=', 'stroke-all', 'no-stroke-all'], )
        if len(args) != 1:
            raise getopt.GetoptError("invalid commandline")

        i = 0
        while i < len(opts):
            opt,arg = opts[i]
            if opt in ('-r', '--allow-repeats'):
                doDedup = False
            elif opt == '--no-allow-repeats':
                doDedup = True
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
            elif opt in ('-S', '--send-speed'):
                sendSpeed = int(arg)
            elif opt in ('-a', '--area'):
                v = map(float, arg.split(','))
                plotter.xyMin = (v[0],v[1])
                plotter.xyMax = (v[2],v[3])
            elif opt in ('-D', '--input-dpi'):
                v = map(float, arg.split(','))
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
            elif opt in ('-O', '--shading-avoid-outline'):
                avoidOutline = True
            elif opt == '--no-shading-avoid-outline':
                avoidOutline = False
            elif opt == '--no-shading-crosshatch':
                shader.crossHatch = False
            elif opt in ('-L', '--stroke-all'):
                strokeAll = True
            elif opt == '--no-stroke-all':
                strokeAll = False
            elif opt in ('-c', '--config-file'):
                configOpts = getConfigOpts(arg)
                opts = opts[:i+1] + configOpts + opts[i+1:]
            elif opt in ('-o', '--optimization-timeout'):
                optimizationTimeOut = float(arg)
            else:
                raise ValueError("Unrecognized argument "+opt)
            i += 1
        
    except getopt.GetoptError:
        sys.stderr.write("gcodeplot.py [options] inputfile [> output.gcode]\n")
        sys.stderr.write("""
 -h|--help: this
 -r|--allow-repeats*: do not deduplicate paths
 -f|--scale=mode: scaling option: none(n), fit(f), down-only(d)
 -D|--input-dpi=xdpi[,ydpi]: hpgl dpi
 -t|--tolerance=x: ignore (some) deviations of x millimeters or less [default 0.05]
 -s|--send=port: send gcode to serial port instead of stdout
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
 -o|--optimimze-timeout=t: timeout on optimization attempt (seconds; will be retried once; set to 0 to turn off optimization) [default 30]
 -c|--config-file=filename: read arguments, one per line, from filename
 
 The options with an asterisk are default off and can be turned off again by adding "no-" at the beginning to the long-form option, e.g., --no-stroke-all.
""")
        sys.exit(2)

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
        segments = parseSVG(svgTree, tolerance=tolerance, shader=shader, strokeAll=strokeAll)
    else:
        segments = parseHPGL(data, dpi=dpi)
    segments = removePenBob(segments)

    if doDedup:
        segments = dedup(segments)

    if optimizationTimeOut > 0.:
        segments = removePenBob(anneal.optimize(segments, timeout=optimizationTimeOut))

    if hpglOut:
        g = emitHPGL(segments)
    else:    
        g = emitGcode(segments, scale=scale, align=align, scalingMode=scalingMode, tolerance=tolerance, plotter=plotter)

    if g:
        if sendPort is not None:
            import utils.sendgcode as sendgcode
            if hpglOut:
                sendgcode.sendHPGL(port=sendPort, speed=115200, commands=g)
            else:
                sendgcode.sendGcode(port=sendPort, speed=115200, commands=g)
        else:    
            if hpglOut:
                sys.stdout.write(g)
            else:
                print('\n'.join(g))
    else:
        sys.stderr.write("No points.")
        sys.exit(1)

       