#!/usr/bin/python
from __future__ import print_function
import re
import sys
import getopt
import math
import xml.etree.ElementTree as ET
import gcodeplotutils.anneal as anneal
import svgpath.parser as parser
import cmath
from random import sample
from svgpath.shader import Shader
from gcodeplotutils.processoffset import OffsetProcessor
from gcodeplotutils.evaluate import evaluate

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
    def __init__(self, xyMin=(7,8), xyMax=(204,178),
            drawSpeed=35, moveSpeed=40, zSpeed=5, workZ = 14.5, liftDeltaZ = 2.5, safeDeltaZ = 20,
            liftCommand=None, safeLiftCommand=None, downCommand=None, comment=";",
            initCode = "G00 S1; endstops|"
                       "G00 E0; no extrusion|"
                       "G01 S1; endstops|"
                       "G01 E0; no extrusion|"
                       "G21; millimeters|"
                       "G91 G0 F%.1f{{zspeed*60}} Z%.3f{{safe}}; pen park !!Zsafe|"
                       "G90; absolute|"
                       "G28 X; home|"
                       "G28 Y; home|"
                       "G28 Z; home",
            endCode=None):
        self.xyMin = xyMin
        self.xyMax = xyMax
        self.drawSpeed = drawSpeed
        self.moveSpeed = moveSpeed
        self.workZ = workZ
        self.liftDeltaZ = liftDeltaZ
        self.safeDeltaZ = safeDeltaZ
        self.zSpeed = zSpeed
        self.liftCommand = liftCommand
        self.safeLiftCommand = safeLiftCommand
        self.downCommand = downCommand
        self.initCode = initCode
        self.endCode = endCode
        self.comment = comment

    def inRange(self, point):
        for i in range(2):
            if point[i] < self.xyMin[i]-.001 or point[i] > self.xyMax[i]+.001:
                return False
        return True

    @property
    def safeUpZ(self):
        return self.workZ + self.safeDeltaZ

    @property
    def penUpZ(self):
        return self.workZ + self.liftDeltaZ
        
    def updateVariables(self):
        self.variables = {'lift':self.liftDeltaZ, 'work':self.workZ, 'safe':self.safeDeltaZ, 'left':self.xyMin[0],
            'bottom':self.xyMin[1], 'zspeed':self.zSpeed, 'movespeed':self.moveSpeed}
        self.formulas = {'right':str(self.xyMax[0]), 'top':str(self.xyMax[1]), 'up':'work+lift', 'park':'work+safe', 'centerx':'(left+right)/2.', 'centery':'(top+bottom)/2.'}

def processCode(code):
    if not code:
        return []

    data = []
    pattern = r'\{\{([^}]+)\}\}'
    
    data = tuple( evaluate(expr, plotter.variables, plotter.formulas) for expr in re.findall(pattern, code))

        
    formatString = re.sub(pattern, '', code.replace('|', '\n'))
    
    return [formatString % data]
        
def gcodeHeader(plotter):
    return processCode(plotter.initCode)

def isSameColor(rgb1, rgb2):
    if rgb1 is None or rgb2 is None:
        return rgb1 is rgb2
    return max(abs(rgb1[i]-rgb2[i]) for i in range(3)) < 0.001

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
        return Scale(scale=[self.scale[0],self.scale[1]], offset=[self.offset[0],self.offset[1]])

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
        self.scale = [min(s),min(s)]
        self.offset = list(plotter.xyMin[i] - xyMin[i]*self.scale[i] for i in range(2))

    def align(self, plotter, xyMin, xyMax, align):
        o = [0,0]
        for i in range(2):
            if align[i] == ALIGN_LEFT:
                o[i] = plotter.xyMin[i] - self.scale[i]*xyMin[i]
            elif align[i] == ALIGN_RIGHT:
                o[i] = plotter.xyMax[i] - self.scale[i]*xyMax[i]
            elif align[i] == ALIGN_NONE:
                o[i] = self.offset[i] # self.xyMin[i]
            elif align[i] == ALIGN_CENTER:
                o[i] = 0.5 * (plotter.xyMin[i] - self.scale[i]*xyMin[i] + plotter.xyMax[i] - self.scale[i]*xyMax[i])
            else:
                raise ValueError()
        self.offset = o

    def scalePoint(self, point):
        return (point[0]*self.scale[0]+self.offset[0], point[1]*self.scale[1]+self.offset[1])

def comparison(a,b):
    return 1 if a>b else (-1 if a<b else 0)

def safeSorted(data,comparison=comparison):
    """
    A simpleminded recursive merge sort that will work even if the comparison function fails to be a partial order.
    Makes (shallow) copies of the data, which uses more memory than is absolutely necessary. In the intended application,
    the comparison function is very expensive but the number of data points is small.
    """
    n = len(data)
    if n <= 1:
        return list(data)
    d1 = safeSorted(data[:n//2],comparison=comparison)
    d2 = safeSorted(data[n//2:],comparison=comparison)
    i1 = 0
    i2 = 0
    out = []
    while i1 < len(d1) and i2 < len(d2):
        if comparison(d1[i1], d2[i2]) < 0:
            out.append(d1[i1])
            i1 += 1
        else:
            out.append(d2[i2])
            i2 += 1
    if i1 < len(d1):
        out += d1[i1:]
    elif i2 < len(d2):
        out += d2[i2:]
    return out

def comparePaths(path1,path2,tolerance=0.05,pointsToCheck=3):
    """
    inner paths come before outer ones
    closed paths come before open ones
    otherwise, average left to right movement
    """

    def fixPath(path):
        out = [complex(point[0],point[1]) for point in path]
        if out[0] != out[-1] and abs(out[0]-out[-1]) <= tolerance:
            out.append(out[0])
        return out

    def closed(path):
        return path[-1] == path[0]

    def inside(z, path):
        for p in path:
            if p == z:
                return False
        try:
            phases = sorted((cmath.phase(p-z) for p in path))
            # make a ray that is relatively far away from any points
            if len(phases) == 1:
                # should not happen
                bestPhase = phases[0] + math.pi
            else:
                bestIndex = max( (phases[i+1]-phases[i],i) for i in range(len(phases)-1))[1]
                bestPhase = (phases[bestIndex+1]+phases[bestIndex])/2.
            ray = cmath.rect(1., bestPhase)
            rotatedPath = tuple((p-z) / ray for p in path)
            # now we just need to check shiftedPath's intersection with the positive real line
            s = 0
            for i,p2 in enumerate(rotatedPath):
                p1 = rotatedPath[i-1]
                if p1.imag == p2.imag:
                    # horizontal lines can't intersect positive real line once phase selection was done
                    continue
                    # (1/m)y + xIntercept = x
                reciprocalSlope = (p2.real-p1.real)/(p2.imag-p1.imag)
                xIntercept = p2.real - reciprocalSlope * p2.imag
                if xIntercept == 0:
                    return False # on boundary
                if p1.imag * p2.imag < 0 and xIntercept > 0:
                    if p1.imag < 0:
                        s += 1
                    else:
                        s -= 1
            return s != 0

        except OverflowError:
            return False

    def nestedPaths(path1, path2):
        if not closed(path2):
            return False
        k = min(pointsToCheck, len(path1))
        for point in sample(path1, k):
            if inside(point, path2):
                return True
        return False

    path1 = fixPath(path1)
    path2 = fixPath(path2)

    if nestedPaths(path1, path2):
        return -1
    elif nestedPaths(path2, path1):
        return 1
    elif closed(path1) and not closed(path2):
        return -1
    elif closed(path2) and not closed(path1):
        return 1
    x1 = sum(p.real for p in path1) / len(path1)
    x2 = sum(p.real for p in path2) / len(path2)
    return comparison(x1,x2)

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

def penColor(pens, pen):
    if pens is not None and pen in pens:
        return pens[pen].color
    else:
        return (0.,0.,0.)

def emitGcode(data, pens = {}, plotter=Plotter(), scalingMode=SCALE_NONE, align = None, tolerance=0, gcodePause="@pause", pauseAtStart = False, simulation = False):
    if len(data) == 0:
        return None

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
            return None
        scale = Scale()
        scale.fit(plotter, xyMin, xyMax)

    if align is not None:
        scale.align(plotter, xyMin, xyMax, align)

    if not simulation:
        gcode = gcodeHeader(plotter)
    else:
        gcode = []
        gcode.append('<?xml version="1.0" standalone="yes"?>')
        gcode.append('<svg width="%.4fmm" height="%.4fmm" viewBox="%.4f %.4f %.4f %.4f" xmlns="http://www.w3.org/2000/svg" version="1.1">' % (
            plotter.xyMax[0]-plotter.xyMin[0], plotter.xyMax[1]-plotter.xyMin[0], plotter.xyMin[0], plotter.xyMin[1], plotter.xyMax[0], plotter.xyMax[1]))
            
            
    def park():
        if not simulation:
            lift = plotter.safeLiftCommand or plotter.liftCommand
            if lift:
                gcode.extend(processCode(lift))
            else:
                gcode.append('G00 F%.1f Z%.3f; pen park !!Zpark' % (plotter.zSpeed*60., plotter.safeUpZ))

    park()
    if not simulation:
        gcode.append('G00 F%.1f Y%.3f; !!Ybottom' % (plotter.moveSpeed*60.,   plotter.xyMin[1]))
        gcode.append('G00 F%.1f X%.3f; !!Xleft' % (plotter.moveSpeed*60.,   plotter.xyMin[0]))

    class State(object):
        pass

    state = State()
    state.time = (plotter.xyMin[1]+plotter.xyMin[0]) / plotter.moveSpeed
    state.curXY = plotter.xyMin
    state.curZ = plotter.safeUpZ
    state.penColor = (0.,0.,0.)

    def distance(a,b):
        return math.hypot(a[0]-b[0],a[1]-b[1])

    def penUp(force=False):
        if state.curZ is None or state.curZ not in (plotter.safeUpZ, plotter.penUpZ) or force:
            if not simulation:
                if plotter.liftCommand:
                    gcode.extend(processCode(plotter.liftCommand))
                else:
                    gcode.append('G00 F%.1f Z%.3f; pen up !!Zup' % (plotter.zSpeed*60., plotter.penUpZ))
            if state.curZ is not None:
                state.time += abs(plotter.penUpZ-state.curZ) / plotter.zSpeed
            state.curZ = plotter.penUpZ

    def penDown(force=False):
        if state.curZ is None or state.curZ != plotter.workZ or force:
            if not simulation:
                if plotter.downCommand:
                    gcode.extend(processCode(plotter.downCommand))
                else:
                    gcode.append('G00 F%.1f Z%.3f; pen down !!Zwork' % (plotter.zSpeed*60., plotter.workZ))
            state.time += abs(state.curZ-plotter.workZ) / plotter.zSpeed
            state.curZ = plotter.workZ

    def penMove(down, speed, p, force=False):
        def flip(y):
            return plotter.xyMax[1] - (y-plotter.xyMin[1])
        if state.curXY is None:
            d = float("inf")
        else:
            d = distance(state.curXY, p)
        if d > tolerance or force:
            if down:
                penDown(force=force)
            else:
                penUp(force=force)
            if not simulation:
                gcode.append('G0%d F%.1f X%.3f Y%.3f; %s !!Xleft+%.3f Ybottom+%.3f' % (
                    1 if down else 0, speed*60., p[0], p[1], "draw" if down else "move",
                    p[0]-plotter.xyMin[0], p[1]-plotter.xyMin[1]))
            else:
                start = state.curXY if state.curXY is not None else plotter.xyMin
                color = [int(math.floor(255*x+0.5)) for x in (state.penColor if down else (0,0.5,0))]
                thickness = 0.15 if down else 0.1
                end = complex(p[0], flip(p[1]))
                gcode.append('<line x1="%.3f" y1="%.3f" x2="%.3f" y2="%.3f" stroke="rgb(%d,%d,%d)" stroke-width="%.2f"/>'
                    % (start[0], flip(start[1]), end.real, end.imag, color[0], color[1], color[2], thickness))
                ray = end - complex(start[0],flip(start[1]))
                if abs(ray)>0:
                    ray = ray/abs(ray)
                    for theta in [math.pi * 0.8,-math.pi * 0.8]:
                        head = end + ray * cmath.rect(max(0.3,min(2,d*0.25)), theta)
                        gcode.append('<line x1="%.3f" y1="%.3f" x2="%.3f" y2="%.3f" stroke="rgb(0,128,0)" stroke-linejoin="round" stroke-width="0.1"/>'
                            % (end.real, end.imag, head.real, head.imag))

            if state.curXY is not None:
                state.time += d / speed
            state.curXY = p

    for pen in sorted(data):
        if pen != 1:
            state.curZ = None
            state.curXY = None

        state.penColor = penColor(pens, pen)

        s = scale.clone()

        if pens is not None and pen in pens:
            s.offset = (s.offset[0]-pens[pen].offset[0],s.offset[1]-pens[pen].offset[1])

        newPen = True

        for segment in data[pen]:
            penMove(False, plotter.moveSpeed, s.scalePoint(segment[0]))

            if newPen and (pen != 1 or pauseAtStart) and not simulation:
                gcode.append( gcodePause+' load pen: ' + describePen(pens,pen) )
                penMove(False, plotter.moveSpeed, s.scalePoint(segment[0]), force=True)
            newPen = False

            for i in range(1,len(segment)):
                penMove(True, plotter.drawSpeed, s.scalePoint(segment[i]))

    park()

    if simulation:
        gcode.append('</svg>')
    else:
        gcode.extend(processCode(plotter.endCode))

    if not quiet:
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

def parseSVG(svgTree, tolerance=0.05, shader=None, strokeAll=False, pens=None, extractColor = None):
    data = {}
    for path in parser.getPathsFromSVG(svgTree)[0]:
        lines = []

        stroke = strokeAll or (path.svgState.stroke is not None and (extractColor is None or isSameColor(path.svgState.stroke, extractColor)))

        strokePen = getPen(pens, path.svgState.stroke)

        if strokePen not in data:
            data[strokePen] = []

        for line in path.linearApproximation(error=tolerance):
            if stroke:
                data[strokePen].append([(line.start.real,line.start.imag),(line.end.real,line.end.imag)])
            lines.append((line.start, line.end))
        if not data[strokePen]:
            del data[strokePen]

        if shader is not None and shader.isActive() and path.svgState.fill is not None and (extractColor is None or
                isSameColor(path.svgState.fill, extractColor)):
            pen = getPen(pens, path.svgState.fill)

            if pen not in data:
                data[pen] = []

            grayscale = sum(path.svgState.fill) / 3.
            mode = Shader.MODE_NONZERO if path.svgState.fillRule == 'nonzero' else Shader.MODE_EVEN_ODD
            if path.svgState.fillOpacity is not None:
                grayscale = grayscale * path.svgState.fillOpacity + 1. - path.svgState.fillOpacity # TODO: real alpha!
            fillLines = shader.shade(lines, grayscale, avoidOutline=(path.svgState.stroke is None or strokePen != pen), mode=mode)
            for line in fillLines:
                data[pen].append([(line[0].real,line[0].imag),(line[1].real,line[1].imag)])

            if not data[pen]:
                del data[pen]

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

def directionalize(paths, angle, tolerance=1e-10):
    vector = (math.cos(angle * math.pi / 180.), math.sin(angle * math.pi / 180.))

    outPaths = []
    for path in paths:
        startIndex = 0
        prevPoint = path[0]
        canBeForward = True
        canBeReversed = True
        i = 1
        while i < len(path):
            curVector = (path[i][0]-prevPoint[0],path[i][1]-prevPoint[1])
            if curVector[0] or curVector[1]:
                dotProduct = curVector[0]*vector[0] + curVector[1]*vector[1]
                if dotProduct > tolerance:
                    if not canBeForward:
                        outPaths.append(list(reversed(path[startIndex:i])))
                        startIndex = i-1
                        canBeForward = True
                    canBeReversed = False
                elif dotProduct < -tolerance:
                    if not canBeReversed:
                        outPaths.append(path[startIndex:i])
                        startIndex = i-1
                        canBeReversed = True
                    canBeForward = False
                prevPoint = path[i]
            i += 1
        if canBeForward:
            outPaths.append(path[startIndex:i])
        else:
            outPaths.append(list(reversed(path[startIndex:i])))

    return outPaths

def fixComments(plotter, data, comment = ";"):
    if comment == ";":
        return data
    out = []
    for command in data:
        for line in command.split('\n'):
            try:
                ind = line.index(";")
                if ind >= 0:
                    if not comment:
                        out.append( line[:ind].strip() )
                    else:
                        out.append( line[:ind] + comment[0] + line[ind+1:] + comment[1:] )
                else:
                    out.append(line)
            except ValueError:
                out.append(line)
    return out

if __name__ == '__main__':

    def help(error=False):
        if error:
            output = sys.stderr
        else:
            output = sys.stdout
        output.write("gcodeplot.py [options] [inputfile [> output.gcode]\n")
        output.write("""
    --dump-options: show current settings instead of doing anything
 -h|--help: this
 -r|--allow-repeats*: do not deduplicate paths
 -f|--scale=mode: scaling option: none(n), fit(f), down-only(d) [default none; other options don't work with tool-offset]
 -D|--input-dpi=xdpi[,ydpi]: hpgl dpi
 -t|--tolerance=x: ignore (some) deviations of x millimeters or less [default 0.05]
 -s|--send=port*: send gcode to serial port instead of stdout
 -S|--send-speed=baud: set baud rate for sending
 -x|--align-x=mode: horizontal alignment: none(n), left(l), right(r) or center(c)
 -y|--align-y=mode: vertical alignment: none(n), bottom(b), top(t) or center(c)
 -a|--area=x1,y1,x2,y2: gcode print area in millimeters
 -Z|--lift-delta-z=z: amount to lift for pen-up (millimeters)
 -z|--work-z=z: z-position for drawing (millimeters)
 -F|--pen-up-speed=z: speed for moving with pen up (millimeters/second)
 -f|--pen-down-speed=z: speed for moving with pen down (millimeters/second)
 -u|--z-speed=s: speed for up/down movement (millimeters/second)
 -H|--hpgl-out*: output is HPGL, not gcode; most options ignored [default: off]
 -T|--shading-threshold=n: darkest grayscale to leave unshaded (decimal, 0. to 1.; set to 0 to turn off SVG shading) [default 1.0]
 -m|--shading-lightest=x: shading spacing for lightest colors (millimeters) [default 3.0]
 -M|--shading-darkest=x: shading spacing for darkest color (millimeters) [default 0.5]
 -A|--shading-angle=x: shading angle (degrees) [default 45]
 -X|--shading-crosshatch*: cross hatch shading
 -L|--stroke-all*: stroke even regions specified by SVG to have no stroke
 -O|--shading-avoid-outline*: avoid going over outline twice when shading
 -o|--optimization-time=t: max time to spend optimizing (seconds; set to 0 to turn off optimization) [default 60]
 -e|--direction=angle: for slanted pens: prefer to draw in given direction (degrees; 0=positive x, 90=positive y, none=no preferred direction) [default none]
 -d|--sort*: sort paths from inside to outside for cutting [default off]
 -c|--config-file=filename: read arguments, one per line, from filename
 -w|--gcode-pause=cmd: gcode pause command [default: @pause]
 -P|--pens=penfile: read output pens from penfile
 -U|--pause-at-start*: pause at start (can be included without any input file to manually move stuff)
 -R|--extract-color=c: extract color (specified in SVG format , e.g., rgb(1,0,0) or #ff0000 or red)
    --comment-delimiters=xy: one or two characters specifying comment delimiters, e.g., ";" or "()"
    --tool-offset=x: cutting tool offset (millimeters) [default 0.0]
    --overcut=x: overcut (millimeters) [default 0.0]
    --lift-command=gcode: gcode lift command (separate lines with |)
    --down-command=gcode: gcode down command (separate lines with |)
    --init-code=gcode: gcode init commands (separate lines with |)

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
    extractColor = None
    gcodePause = "@pause"
    optimizationTime = 30
    dpi = (1016., 1016.)
    pens = {1:Pen('1 (0.,0.) black default')}
    doDump = False
    penFilename = None
    pauseAtStart = False
    sortPaths = False
    svgSimulation = False
    toolOffset = 0.
    overcut = 0.
    toolMode = "custom"
    booleanExtractColor = False
    quiet = False
    comment = ";"
    sendAndSave = False
    directionAngle = None
    
    def maybeNone(a):
        return None if a=='none' else a

    try:
        opts, args = getopt.getopt(sys.argv[1:], "e:UR:Uhdulw:P:o:Oc:LT:M:m:A:XHrf:na:D:t:s:S:x:y:z:Z:p:f:F:",
                        ["help", "down", "up", "lower-left", "allow-repeats", "no-allow-repeats", "scale=", "config-file=",
                        "area=", 'align-x=', 'align-y=', 'optimization-time=', "pens=",
                        'input-dpi=', 'tolerance=', 'send=', 'send-speed=', 'work-z=', 'lift-delta-z=', 'safe-delta-z=',
                        'pen-down-speed=', 'pen-up-speed=', 'z-speed=', 'hpgl-out', 'no-hpgl-out', 'shading-threshold=',
                        'shading-angle=', 'shading-crosshatch', 'no-shading-crosshatch', 'shading-avoid-outline',
                        'pause-at-start', 'no-pause-at-start', 'min-x=', 'max-x=', 'min-y=', 'max-y=',
                        'no-shading-avoid-outline', 'shading-darkest=', 'shading-lightest=', 'stroke-all', 'no-stroke-all', 'gcode-pause', 'dump-options', 'tab=', 'extract-color=', 'sort', 'no-sort', 'simulation', 'no-simulation', 'tool-offset=', 'overcut=',
                        'boolean-shading-crosshatch=', 'boolean-sort=', 'tool-mode=', 'send-and-save=', 'direction=', 'lift-command=', 'down-command=',
                        'init-code=', 'comment-delimiters=', 'end-code=' ], )

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
                arg = arg.lower()
                if arg.startswith('n'):
                    scalingMode = SCALE_NONE
                elif arg.startswith('d'):
                    scalingMode = SCALE_DOWN_ONLY
                elif arg.startswith('f'):
                    scalingMode = SCALE_FIT
            elif opt in ('-x', '--align-x'):
                arg = arg.lower()
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
                arg = arg.lower()
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
                sendPort = None if len(arg.strip()) == 0 else arg
            elif opt == '--send-and-save':
                sendPort = None if len(arg.strip()) == 0 else arg
                if sendPort is not None:
                    sendAndSave = True
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
            elif opt in ('-Z', '--lift-delta-z'):
                plotter.liftDeltaZ = float(arg)
            elif opt in ('-z', '--work-z'):
                plotter.workZ = float(arg)
            elif opt == '--tool-offset':
                toolOffset = float(arg)
            elif opt == '--overcut':
                overcut = float(arg)
            elif opt in ('-p', '--safe-delta-z'):
                plotter.safeDeltaZ = float(arg)
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
            elif opt == '--boolean-shading-crosshatch':
                shader.crossHatch = arg.strip() != 'false'
            elif opt == '--boolean-sort':
                sort = arg.strip() != 'false'
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
            elif opt in ('-o', '--optimization-time'):
                optimizationTime = float(arg)
                if optimizationTime > 0:
                    sort = False
            elif opt in ('-h', '--help'):
                help()
                sys.exit(0)
            elif opt == '--dump-options':
                doDump = True
            elif opt in ('-R', '--extract-color'):
                arg = arg.lower()
                if arg == 'all' or len(arg.strip())==0:
                    extractColor = None
                else:
                    extractColor = parser.rgbFromColor(arg)
            elif opt in ('-d', '--sort'):
                sortPaths = True
                optimizationTime = 0
            elif opt == '--no-sort':
                sortPaths = False
            elif opt in ('U', '--simulation'):
                svgSimulation = True
            elif opt == '--no-simulation':
                svgSimulation = False
            elif opt == '--tab':
                quiet = True # Inkscape
            elif opt == "--tool-mode":
                toolMode = arg
            elif opt in ('e', '--direction'):
                if len(arg.strip()) == 0 or arg == 'none':
                    directionAngle = None
                else:
                    directionAngle = float(arg)
            elif opt == '--lift-command':
                plotter.liftCommand = maybeNone(arg)
            elif opt == '--down-command':
                plotter.downCommand = maybeNone(arg)
            elif opt == '--init-code':
                plotter.initCode = maybeNone(arg)
            elif opt == '--end-code':
                plotter.endCode = maybeNone(arg)
            elif opt == '--comment-delimiters':
                plotter.comment = maybeNone(arg)
            else:
                raise ValueError("Unrecognized argument "+opt)
            i += 1

    except getopt.GetoptError as e:
        sys.stderr.write(str(e)+"\n")
        help(error=True)
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
        print('safe-delta-z=%g' % (plotter.safeDeltaZ))
        print('lift-delta-z=%g' % (plotter.liftDeltaZ))
        print('work-z=%g' % (plotter.workZ))
        print('pen-down-speed=%g' % (plotter.drawSpeed))
        print('pen-up-speed=%g' % (plotter.moveSpeed))
        print('z-speed=%g' % (plotter.zSpeed))
        print('hpgl-out' if hpglOut else 'no-hpgl-out')
        print('shading-threshold=%g' % (shader.unshadedThreshold))
        print('shading-lightest=%g' % (shader.lightestSpacing))
        print('shading-darkest=%g' % (shader.darkestSpacing))
        print('shading-angle=%g' % (shader.angle))
        print('shading-crosshatch' if shader.crossHatch else 'no-shading-crosshatch')
        print('stroke-all' if strokeAll else 'no-stroke-all')
        print('optimization-time=%g' % (optimizationTime))
        print('sort' if sortPaths else 'no-sort')
        print('pause-at-start' if pauseAtStart else 'no-pause-at-start')
        print('extract-color=all' if extractColor is None else 'extract-color=rgb(%.3f,%.3f,%.3f)' % tuple(extractColor))
        print('tool-offset=%.3f' % toolOffset)
        print('overcut=%.3f' % overcut)
        print('simulation' if svgSimulation else 'no-simulation')
        print('direction=' + ('none' if directionAngle is None else '%.3f'%directionAngle))
        print('lift-command=' + ('none' if plotter.liftCommand is None else plotter.liftCommand))
        print('down-command=' + ('none' if plotter.downCommand is None else plotter.downCommand))
        print('init-code=' + ('none' if plotter.initCode is None else plotter.initCode))
        print('end-code=' + ('none' if plotter.endCode is None else plotter.endCode))
        print('comment-delimiters=' + ('none' if plotter.comment is None else plotter.comment))

        sys.exit(0)

    if toolMode == 'cut':
        shader.unshadedThreshold = 0
        optimizationTime = 0
        sortPaths = True
        directionAngle = None
    elif toolMode == 'draw':
        toolOffset = 0.
        sortPaths = False
        
    plotter.updateVariables()

    if len(args) == 0:
        if not pauseAtStart:
            help()

        if sendPort is None:
            sys.stderr.write("Need to specify --send=port to be able to pause without any file.")
            sys.exit(1)
        import gcodeplotutils.sendgcode as sendgcode

        sendgcode.sendGcode(port=sendPort, speed=sendSpeed, commands=gcodeHeader(plotter) + [gcodePause], gcodePause=gcodePause, variables=plotter.variables, formulas=plotter.formulas)
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

    shader.setDrawingDirectionAngle(directionAngle)
    if svgTree is not None:
        penData = parseSVG(svgTree, tolerance=tolerance, shader=shader, strokeAll=strokeAll, pens=pens, extractColor=extractColor)
    else:
        penData = parseHPGL(data, dpi=dpi)
    penData = removePenBob(penData)

    if doDedup:
        penData = dedup(penData)

    if sortPaths:
        for pen in penData:
            penData[pen] = safeSorted(penData[pen], comparison=comparePaths)
        penData = removePenBob(penData)

    if optimizationTime > 0. and directionAngle is None:
        for pen in penData:
            penData[pen] = anneal.optimize(penData[pen], timeout=optimizationTime/2., quiet=quiet)
        penData = removePenBob(penData)

    if toolOffset > 0. or overcut > 0.:
        if scalingMode != SCALE_NONE:
            sys.stderr.write("Scaling with tool-offset > 0 will produce unpredictable results.\n")
        op = OffsetProcessor(toolOffset=toolOffset, overcut=overcut, tolerance=tolerance)
        for pen in penData:
            penData[pen] = op.processPath(penData[pen])

    if directionAngle is not None:
        for pen in penData:
            penData[pen] = directionalize(penData[pen], directionAngle)
        penData = removePenBob(penData)

    if len(penData) > 1:
        sys.stderr.write("Uses the following pens:\n")
        for pen in sorted(penData):
            sys.stderr.write(describePen(pens, pen)+"\n")

    if hpglOut and not svgSimulation:
        g = emitHPGL(penData, pens=pens)
    else:
        g = emitGcode(penData, align=align, scalingMode=scalingMode, tolerance=tolerance,
                plotter=plotter, gcodePause=gcodePause, pens=pens, pauseAtStart=pauseAtStart, simulation=svgSimulation)

    if g:
        dump = True

        if sendPort is not None and not svgSimulation:
            import gcodeplotutils.sendgcode as sendgcode

            dump = sendAndSave

            if hpglOut:
                sendgcode.sendHPGL(port=sendPort, speed=sendSpeed, commands=g)
            else:
                sendgcode.sendGcode(port=sendPort, speed=sendSpeed, commands=g, gcodePause=gcodePause, plotter=plotter, variables=plotter.variables, formulas=plotter.formulas)

        if dump:
            if hpglOut:
                sys.stdout.write(g)
            else:
                print('\n'.join(fixComments(plotter, g, comment=plotter.comment)))

    else:
        sys.stderr.write("No points.")
        sys.exit(1)

