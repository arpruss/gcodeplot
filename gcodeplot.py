#!/usr/bin/python
from __future__ import print_function
from gcodeplotutils.evaluate import evaluate
from gcodeplotutils.processoffset import OffsetProcessor
from pathlib import Path
from random import sample
from svgpath.shader import Shader
import argparse
import cmath
import gcodeplotutils.anneal as anneal
import gcodeplotutils.sendgcode as sendgcode
import io
import math
import re
import requests
import svgpath.parser as parser
import sys
import xml.etree.ElementTree as ET
from gcodeplotutils.enums import *
from gcodeplotutils.argparser_c import cArgumentParser, PrintDefaultsAction, CustomBooleanAction, PenAction, parse_alignment, none_or_str

class Plotter(object):
    def __init__(self, xyMin:tuple=(7,8), xyMax:tuple=(204,178),
            drawSpeed:int=35, moveSpeed:int=40, zSpeed:int=5, workZ:float = 14.5, liftDeltaZ:float= 2.5, safeDeltaZ:float = 20,
            liftCommand:str=None, safeLiftCommand:str=None, downCommand:str=None, comment:str=";",
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
    
    def setCoordinates(self,Xmin, Ymin, Xmax, Ymax):
        self.xyMin = (Xmin, Ymin)
        self.xyMax = (Xmax, Ymax)

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
        
    def __repr__(self):
        return f"Pen(pen={self.pen}, offset={self.offset}, color={self.color}, name={self.name})"

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
            elif align[i] == ALIGN_SCALE_NONE:
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

def emitGcode(data, pens = {}, plotter=Plotter(), scalingMode=SCALE_NONE, align = None, tolerance=0, gcodePause="@pause", pauseAtStart = False, simulation = False, quiet = False):
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



def parse_svg_file(data):  
    try:
        svgTree = ET.fromstring(data)
        return svgTree if 'svg' in svgTree.tag else None 
    except:
        return None



def generate_pen_data(svgTree, data, args, shader:Shader):
    penData = {}
    
    if svgTree is not None:
        penData = parseSVG(svgTree, tolerance=args.tolerance, shader=shader, strokeAll=args.stroke_all, pens=args.pens, extractColor=args.extract_color if args.boolean_extract_color else None)
    else:
        penData = parseHPGL(data, dpi=args.input_dpi)
        
    penData = removePenBob(penData)
    
    if not args.allow_repeats: 
        penData = dedup(penData)
        
    if args.sort and penData:
        penData = {pen: safeSorted(paths, comparison=comparePaths) for pen, paths in penData.items()}
        penData = removePenBob(penData)
        
    if args.optimization_time > 0. and args.direction is None and penData:
        penData = {pen: anneal.optimize(paths, timeout=args.optimization_time/2., quiet=args.quiet) for pen, paths in penData.items()}
        penData = removePenBob(penData)
    
    if (args.tool_offset > 0. or args.overcut > 0.) and penData:
        if parse_alignment(args.scale, enumMode=True) != SCALE_NONE:
            sys.stderr.write("Scaling with tool-offset > 0 will produce unpredictable results.\n")
        op = OffsetProcessor(toolOffset=args.tool_offset, overcut=args.overcut, tolerance=args.tolerance)
        penData = {pen: op.processPath(paths) for pen, paths in penData.items()}

    if args.direction is not None and penData:
        penData = {pen: directionalize(paths, args.direction) for pen, paths in penData.items()}
        penData = removePenBob(penData)
        
    if len(penData) > 1 and penData:
        sys.stderr.write("Uses the following pens:\n")
        for pen in sorted(penData):
            sys.stderr.write(describePen(args.pens, pen)+"\n")
            
    return penData          


def generate_HPGL_or_GCODE(penData, args, plotter):
    
    if args.hpgl_out and not args.simulation:
        res = emitHPGL(penData, pens=args.pens)
    else:
        align = [parse_alignment(args.align_x, enumMode=True), parse_alignment(args.align_y, enumMode=True)]
        res = emitGcode(penData, align=align, scalingMode=parse_alignment(args.scale, enumMode=True), tolerance=args.tolerance,
                plotter=plotter, gcodePause=args.gcode_pause, pens=args.pens, pauseAtStart=args.pause_at_start, simulation=args.simulation, quiet=args.quiet)
    
    if not res:
        sys.stderr.write("No points.")
        sys.exit(1)
        
    return res


def parse_arguments(argparser:cArgumentParser):

    argparser.add_argument('--dump-options', help='show current settings instead of doing anything', action=PrintDefaultsAction, nargs=0)
    
    argparser.add_argument('-r', '--allow-repeats', help='do not deduplicate paths', action=CustomBooleanAction, default=False)
    argparser.add_argument('-f', '--scale', metavar='MODE', choices=['n', 'f', 'd'], default='n', type=parse_alignment, help='scaling option: none(n), fit(f), down-only(d) [default none; other options do not work with tool-offset]') 
    argparser.add_argument('-D', '--input-dpi', metavar='x[,y]', default=(1016., 1016.), help='hpgl dpi', type=lambda s: tuple(map(float, s.split(','))) if ',' in s else (float(s), float(s))) # returns (x,x) if only one number provided, otherwise returns (x,y)
    argparser.add_argument('-t', '--tolerance', metavar='x', default=0.05, type=float, help='ignore (some) deviations of x millimeters or less [default: %(default)s]')

    argparser.add_argument('-s', '--send', metavar='PORT', default=None, action=CustomBooleanAction, help='Send gcode to serial port instead of stdout')
    argparser.add_argument('-S', '--send-speed', metavar='BAUD', default=115200, help='set baud rate for sending')
    
    argparser.add_argument('-x', '--align-x', metavar='MODE', choices=['n', 'l', 'r', 'c'], default='l', type=parse_alignment, help='horizontal alignment: none(n), left(l), right(r) or center(c)') 
    argparser.add_argument('-y', '--align-y', metavar='MODE', choices=['n', 'b', 't', 'c'], default='t', type=parse_alignment, help='horizontal alignment: none(n), bottom(b), top(t) or center(c)') 

    # PLOTTER INIT
    argparser.add_argument('-a', '--area', metavar='x1,y1,x2,y2', default=[7, 8, 204, 178], type=lambda s: list(map(float, s.split(','))), help='gcode print area in millimeters')
    argparser.add_argument('--min-x', type=float, default=None, help=argparse.SUPPRESS)
    argparser.add_argument('--min-y', type=float, default=None, help=argparse.SUPPRESS)
    argparser.add_argument('--max-x', type=float, default=None, help=argparse.SUPPRESS)
    argparser.add_argument('--max-y', type=float, default=None, help=argparse.SUPPRESS)
    argparser.add_argument('-Z', '--lift-delta-z', metavar='Z', default=2.5, type=float, help='amount to lift for pen-up (millimeters)')
    argparser.add_argument('-z', '--work-z', metavar='Z', default=14.5, type=float, help='z-position for drawing (millimeters)')  
    argparser.add_argument('-V', '--pen-up-speed', metavar='S', default=40, type=float, help='speed for moving with pen up (millimeters/second)')
    argparser.add_argument('-v', '--pen-down-speed', metavar='S', default=35, type=float, help='speed for moving with pen down (millimeters/second)')
    argparser.add_argument('-u', '--z-speed', metavar='S', default=5, type=float, help='speed for up/down movement (millimeters/second)')
    argparser.add_argument('--safe-delta-z', metavar='Z', default=20.0, type=float, help='height to lift tool for safe parking (Default: 20)')
    argparser.add_argument('--comment-delimiters', metavar='XY', type=none_or_str, default=';', help='one or two characters specifying comment delimiters, e.g., ";" or "()"')
    argparser.add_argument('--lift-command', metavar='GCODE', type=none_or_str, default=None, help='gcode lift command (separate lines with |)')
    argparser.add_argument('--down-command', metavar='GCODE', type=none_or_str, default=None, help='gcode down command (separate lines with |)')
    argparser.add_argument('--init-code', metavar='GCODE', type=none_or_str, default="G00 S1; endstops|G00 E0; no extrusion|G01 S1; endstops|G01 E0; no extrusion|G21; millimeters|G91 G0 F%.1f{{zspeed*60}} Z%.3f{{safe}}; pen park !!Zsafe|G90; absolute|G28 X; home|G28 Y; home|G28 Z; home", help='gcode init commands (separate lines with |)')
    argparser.add_argument('--end-code', metavar='GCODE', type=none_or_str, default=None, help='Gcode to run at end of task')
    
    argparser.add_argument('-H', '--hpgl-out', action=argparse.BooleanOptionalAction, default=False, help='output is HPGL, not gcode; most options are ignored.')
    
    argparser.add_argument('-P', '--pens', metavar='PENFILE', default={1:Pen('1 (0.,0.) black default')}, action=PenAction, PenClass=Pen, help='read output pens from penfile')
    argparser.add_argument('-T', '--shading-threshold', metavar='N', default=1.0, type=float, help='darkest grayscale to leave unshaded (decimal, 0. to 1.; set to 0 to turn off SVG shading) [default 1.0]')
    argparser.add_argument('-m', '--shading-lightest', metavar='X', default=3.0, type=float, help='shading spacing for lightest colors (millimeters) [default 3.0]')
    argparser.add_argument('-M', '--shading-darkest', metavar='X', default=0.5, type=float, help='shading spacing for darkest color (millimeters) [default 0.5]')
    argparser.add_argument('-A', '--shading-angle', metavar='X', default=45, type=float, help='shading angle (degrees) [default 45]')
    argparser.add_argument('-X', '--shading-crosshatch', action=argparse.BooleanOptionalAction, default=False, help='cross hatch shading')
    argparser.add_argument('-O', '--shading-avoid-outline', action=argparse.BooleanOptionalAction, default=False, help='avoid going over outline twice when shading') #?Unused
    
    argparser.add_argument('-R', '--extract-color', metavar='C', default=None, type=parser.rgbFromColor, help='extract color (specified in SVG format , e.g., rgb(1,0,0) or #ff0000 or red)')
    argparser.add_argument('-L', '--stroke-all', action=argparse.BooleanOptionalAction, default=False, help='stroke even regions specified by SVG to have no stroke')
    argparser.add_argument('-e', '--direction', metavar='ANGLE', default=None, type=lambda value: None if value.lower() == 'none' else float(value), help='for slanted pens: prefer to draw in given direction (degrees; 0=positive x, 90=positive y, none=no preferred direction) [default none]')
    
    argparser.add_argument('-o', '--optimization-time', metavar='T', default=60, type=int, help='max time to spend optimizing (seconds; set to 0 to turn off optimization) [default 60]')
    argparser.add_argument('-d', '--sort', action=argparse.BooleanOptionalAction, default=False, help='sort paths from inside to outside for cutting [default off]')
 
    argparser.add_argument('-w', '--gcode-pause', metavar='CMD', default='@pause', help='gcode pause command [default: @pause]')
    argparser.add_argument('-U', '--pause-at-start', action=argparse.BooleanOptionalAction, default=False, help='pause at start (can be included without any input file to manually move stuff)')
    
    argparser.add_argument('--tool-mode', metavar='MODE', choices=['custom','cut','draw'], default='custom', help=argparse.SUPPRESS)
    argparser.add_argument('--tool-offset', metavar='X', default=0.0, type=float, help='cutting tool offset (millimeters) [default 0.0]')
    argparser.add_argument('--overcut', metavar='X', default=0.0, type=float, help='overcut (millimeters) [default 0.0]')
    
    argparser.add_argument('--moonraker', metavar='URL', default=None, help='moonraker url')
    argparser.add_argument('--moonraker-filename', metavar='FILENAME', default='toolpath.gcode', help='name of uploaded file')
    argparser.add_argument('--moonraker-autoprint', metavar='TRUE/FALSE', default=False, help='whether to automatically begin the print job after upload')
    
    argparser.add_argument('--simulation', metavar='TRUE/FALSE', action=argparse.BooleanOptionalAction, default=False, help=argparse.SUPPRESS)
    
    #Inkscape specific boolean parameters
    argparser.add_argument('--boolean-extract-color', metavar='TRUE/FALSE', type=lambda val: True if val.lower() == 'true' else False, help=argparse.SUPPRESS)
    argparser.add_argument('--boolean-shading-crosshatch', metavar='TRUE/FALSE', dest='shading_crosshatch',  help=argparse.SUPPRESS)
    argparser.add_argument('--boolean-sort', metavar='TRUE/FALSE', dest='sort',  help=argparse.SUPPRESS)
    argparser.add_argument('--send-and-save', metavar='PORT', default=False, help=argparse.SUPPRESS) #Could probably roll this into "send" and check if we're in Inkscape at the end of __main__ by using tab/quiet instead
    argparser.add_argument('--tab', dest='quiet', default=False, type=bool, help=argparse.SUPPRESS)
    
    args, positional = argparser.parse_known_args()
    
    # I probably shouldn't have done this. If a port is provided on SEND, use it,
    # otherwise check if it was provided on send_and_save, otherwise set SEND to None
    # If a port is provided on send_and_save, then it sets SEND to the port, then sets itself to True. 
    args.send = args.send if str(args.send).isdigit() else args.send_and_save if str(args.send_and_save).isdigit() else None
    args.send_and_save = True if str(args.send_and_save).isdigit() else False
    
    if args.sort == True:
        args.optimization_time = 0 
    elif args.optimization_time > 0:
        args.sort = False
    
    if args.tool_mode == 'cut':
        args.optimization_time = 0
        args.sort = True
        args.direction = None
    elif args.tool_mode == 'draw':
        args.tool_offset = 0.
        args.sort = False

    
    return args, positional


            
if __name__ == '__main__':
        
    argparser = cArgumentParser(prog='Gcode Plot', description='test', fromfile_prefix_chars='$', epilog="You can load options from a text file by passing the filename prefixed with a '$' e.g. [python gcodeplot.py $'args.txt']", formatter_class=argparse.ArgumentDefaultsHelpFormatter)  
    args, positional = parse_arguments(argparser)

    plotter = Plotter(xyMin=tuple((args.min_x if args.min_x is not None else args.area[0], args.min_y if args.min_y is not None else args.area[1])),
                      xyMax=tuple((args.max_x if args.max_x is not None else args.area[2], args.max_y if args.max_y is not None else args.area[3])),
                      drawSpeed=args.pen_down_speed,
                      moveSpeed=args.pen_up_speed,
                      zSpeed=args.z_speed,
                      workZ=args.work_z,
                      liftDeltaZ=args.lift_delta_z,
                      safeDeltaZ=args.safe_delta_z,
                      liftCommand=args.lift_command,
                      safeLiftCommand=None,
                      downCommand=args.down_command,
                      initCode=args.init_code,
                      endCode=args.end_code,
                      comment=args.comment_delimiters)
    
    shader = Shader(unshadedThreshold= 0 if args.tool_mode == 'cut' else args.shading_threshold,
                    lightestSpacing=args.shading_lightest,
                    darkestSpacing=args.shading_darkest,
                    angle=args.shading_angle,
                    crossHatch=args.shading_crosshatch)

 
    plotter.updateVariables()
    
    # If no input SVG is provided on stdin, assume the intent is to just run the init g-code over serial. 
    if len(positional) == 0:
        if not args.pause_at_start:
            argparser.print_help()
        if args.send is None: 
            sys.stderr.write("Need to specify --send=port to be able to pause without any file.")
            sys.exit(1)
               
        sendgcode.sendGcode(port=args.send, speed=args.send_speed, commands=gcodeHeader(plotter) + [args.gcode_pause], gcodePause=args.gcode_pause, variables=plotter.variables, formulas=plotter.formulas)
        sys.exit(0)
    
    # Otherwise, open the input file...
    with open(positional[0], 'r') as f:
        data = f.read()
    
    # Gather the SVG data and generate pen data, then generate the output HPGL/GCode...
    # Note the program will exit if HPGL/GCode cannot be created
    svgTree = parse_svg_file(data)
    shader.setDrawingDirectionAngle(args.direction)
    penData = generate_pen_data(svgTree, data, args, shader)
    g = generate_HPGL_or_GCODE(penData, args, plotter)
    filtered = '\n'.join(fixComments(plotter, g, comment=plotter.comment)) + '\n' 

    # "Dump" here refers to whether the output code will be sent to stdout or not. 
    dump = True

    # If we have a port to send to, and we're not in simulation mode, send either the GCode or HPGL over serial.
    # If send_and_save is false, then it means we don't want to save the data (from Inkscape; saving is done by returning the data via stdout)
    if args.send is not None and not args.simulation:
        dump = args.send_and_save
        
        if args.hpgl_out: 
            sendgcode.sendHPGL(port=args.send, speed=args.send_speed, commands=g)
        else:
            sendgcode.sendGcode(port=args.send, speed=args.send_speed, commands=g, gcodePause=args.gcode_pause, plotter=plotter, variables=plotter.variables, formulas=plotter.formulas)
    
    # If we want to upload to Klipper via Moonraker
    if args.moonraker != "" and args.moonraker is not None:         
        moonraker = args.moonraker.strip("/") + "/server/files/upload"                 
        virtual_file = io.BytesIO(filtered.encode('utf-8'))
        files = {'file': (args.moonraker_filename, virtual_file), 'print': args.moonraker_autoprint}
        response = requests.post(moonraker, files=files)
        if response.status_code != 201:
            sys.stderr.write(f"Error uploading file. Status code: {response.status_code}")

    # If we don't want to return the file over stdout, we exit here...
    if not dump:
        sys.exit(0)

    # Otherwise, save the file to stdout if it's HPGL...
    if args.hpgl_out:
        sys.stdout.write(g)
        sys.exit(0)
    
    # Or format and save to stdout if it's GCode
    
    print('\n'.join(fixComments(plotter, g, comment=plotter.comment)))
   