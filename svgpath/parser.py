# SVG Path specification parser

import re
from . import path
import xml.etree.ElementTree as ET
import re
import math

COMMANDS = set('MmZzLlHhVvCcSsQqTtAa')
UPPERCASE = set('MZLHVCSQTA')

COMMAND_RE = re.compile("([MmZzLlHhVvCcSsQqTtAa])")
FLOAT_RE = re.compile("[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?")

SVG_COLORS = {
"aliceblue": (0.941176,0.972549,1),
"antiquewhite": (0.980392,0.921569,0.843137),
"aqua": (0,1,1),
"aquamarine": (0.498039,1,0.831373),
"azure": (0.941176,1,1),
"beige": (0.960784,0.960784,0.862745),
"bisque": (1,0.894118,0.768627),
"black": (0,0,0),
"blanchedalmond": (1,0.921569,0.803922),
"blue": (0,0,1),
"blueviolet": (0.541176,0.168627,0.886275),
"brown": (0.647059,0.164706,0.164706),
"burlywood": (0.870588,0.721569,0.529412),
"cadetblue": (0.372549,0.619608,0.627451),
"chartreuse": (0.498039,1,0),
"chocolate": (0.823529,0.411765,0.117647),
"coral": (1,0.498039,0.313725),
"cornflowerblue": (0.392157,0.584314,0.929412),
"cornsilk": (1,0.972549,0.862745),
"crimson": (0.862745,0.0784314,0.235294),
"cyan": (0,1,1),
"darkblue": (0,0,0.545098),
"darkcyan": (0,0.545098,0.545098),
"darkgoldenrod": (0.721569,0.52549,0.0431373),
"darkgray": (0.662745,0.662745,0.662745),
"darkgreen": (0,0.392157,0),
"darkgrey": (0.662745,0.662745,0.662745),
"darkkhaki": (0.741176,0.717647,0.419608),
"darkmagenta": (0.545098,0,0.545098),
"darkolivegreen": (0.333333,0.419608,0.184314),
"darkorange": (1,0.54902,0),
"darkorchid": (0.6,0.196078,0.8),
"darkred": (0.545098,0,0),
"darksalmon": (0.913725,0.588235,0.478431),
"darkseagreen": (0.560784,0.737255,0.560784),
"darkslateblue": (0.282353,0.239216,0.545098),
"darkslategray": (0.184314,0.309804,0.309804),
"darkslategrey": (0.184314,0.309804,0.309804),
"darkturquoise": (0,0.807843,0.819608),
"darkviolet": (0.580392,0,0.827451),
"deeppink": (1,0.0784314,0.576471),
"deepskyblue": (0,0.74902,1),
"dimgray": (0.411765,0.411765,0.411765),
"dimgrey": (0.411765,0.411765,0.411765),
"dodgerblue": (0.117647,0.564706,1),
"firebrick": (0.698039,0.133333,0.133333),
"floralwhite": (1,0.980392,0.941176),
"forestgreen": (0.133333,0.545098,0.133333),
"fuchsia": (1,0,1),
"gainsboro": (0.862745,0.862745,0.862745),
"ghostwhite": (0.972549,0.972549,1),
"gold": (1,0.843137,0),
"goldenrod": (0.854902,0.647059,0.12549),
"gray": (0.501961,0.501961,0.501961),
"grey": (0.501961,0.501961,0.501961),
"green": (0,0.501961,0),
"greenyellow": (0.678431,1,0.184314),
"honeydew": (0.941176,1,0.941176),
"hotpink": (1,0.411765,0.705882),
"indianred": (0.803922,0.360784,0.360784),
"indigo": (0.294118,0,0.509804),
"ivory": (1,1,0.941176),
"khaki": (0.941176,0.901961,0.54902),
"lavender": (0.901961,0.901961,0.980392),
"lavenderblush": (1,0.941176,0.960784),
"lawngreen": (0.486275,0.988235,0),
"lemonchiffon": (1,0.980392,0.803922),
"lightblue": (0.678431,0.847059,0.901961),
"lightcoral": (0.941176,0.501961,0.501961),
"lightcyan": (0.878431,1,1),
"lightgoldenrodyellow": (0.980392,0.980392,0.823529),
"lightgray": (0.827451,0.827451,0.827451),
"lightgreen": (0.564706,0.933333,0.564706),
"lightgrey": (0.827451,0.827451,0.827451),
"lightpink": (1,0.713725,0.756863),
"lightsalmon": (1,0.627451,0.478431),
"lightseagreen": (0.12549,0.698039,0.666667),
"lightskyblue": (0.529412,0.807843,0.980392),
"lightslategray": (0.466667,0.533333,0.6),
"lightslategrey": (0.466667,0.533333,0.6),
"lightsteelblue": (0.690196,0.768627,0.870588),
"lightyellow": (1,1,0.878431),
"lime": (0,1,0),
"limegreen": (0.196078,0.803922,0.196078),
"linen": (0.980392,0.941176,0.901961),
"magenta": (1,0,1),
"maroon": (0.501961,0,0),
"mediumaquamarine": (0.4,0.803922,0.666667),
"mediumblue": (0,0,0.803922),
"mediumorchid": (0.729412,0.333333,0.827451),
"mediumpurple": (0.576471,0.439216,0.858824),
"mediumseagreen": (0.235294,0.701961,0.443137),
"mediumslateblue": (0.482353,0.407843,0.933333),
"mediumspringgreen": (0,0.980392,0.603922),
"mediumturquoise": (0.282353,0.819608,0.8),
"mediumvioletred": (0.780392,0.0823529,0.521569),
"midnightblue": (0.0980392,0.0980392,0.439216),
"mintcream": (0.960784,1,0.980392),
"mistyrose": (1,0.894118,0.882353),
"moccasin": (1,0.894118,0.709804),
"navajowhite": (1,0.870588,0.678431),
"navy": (0,0,0.501961),
"oldlace": (0.992157,0.960784,0.901961),
"olive": (0.501961,0.501961,0),
"olivedrab": (0.419608,0.556863,0.137255),
"orange": (1,0.647059,0),
"orangered": (1,0.270588,0),
"orchid": (0.854902,0.439216,0.839216),
"palegoldenrod": (0.933333,0.909804,0.666667),
"palegreen": (0.596078,0.984314,0.596078),
"paleturquoise": (0.686275,0.933333,0.933333),
"palevioletred": (0.858824,0.439216,0.576471),
"papayawhip": (1,0.937255,0.835294),
"peachpuff": (1,0.854902,0.72549),
"peru": (0.803922,0.521569,0.247059),
"pink": (1,0.752941,0.796078),
"plum": (0.866667,0.627451,0.866667),
"powderblue": (0.690196,0.878431,0.901961),
"purple": (0.501961,0,0.501961),
"red": (1,0,0),
"rosybrown": (0.737255,0.560784,0.560784),
"royalblue": (0.254902,0.411765,0.882353),
"saddlebrown": (0.545098,0.270588,0.0745098),
"salmon": (0.980392,0.501961,0.447059),
"sandybrown": (0.956863,0.643137,0.376471),
"seagreen": (0.180392,0.545098,0.341176),
"seashell": (1,0.960784,0.933333),
"sienna": (0.627451,0.321569,0.176471),
"silver": (0.752941,0.752941,0.752941),
"skyblue": (0.529412,0.807843,0.921569),
"slateblue": (0.415686,0.352941,0.803922),
"slategray": (0.439216,0.501961,0.564706),
"slategrey": (0.439216,0.501961,0.564706),
"snow": (1,0.980392,0.980392),
"springgreen": (0,1,0.498039),
"steelblue": (0.27451,0.509804,0.705882),
"tan": (0.823529,0.705882,0.54902),
"teal": (0,0.501961,0.501961),
"thistle": (0.847059,0.74902,0.847059),
"tomato": (1,0.388235,0.278431),
"turquoise": (0.25098,0.878431,0.815686),
"violet": (0.933333,0.509804,0.933333),
"wheat": (0.960784,0.870588,0.701961),
"white": (1,1,1),
"whitesmoke": (0.960784,0.960784,0.960784),
"yellow": (1,1,0),
"yellowgreen": (0.603922,0.803922,0.196078),
}

def _tokenize_path(pathdef):
    for x in COMMAND_RE.split(pathdef):
        if x in COMMANDS:
            yield x
        for token in FLOAT_RE.findall(x):
            yield token

def applyMatrix(matrix, z):
    return complex(z.real * matrix[0] + z.imag * matrix[1] + matrix[2], 
             z.real * matrix[3] + z.imag * matrix[4] + matrix[5] )
             
def matrixMultiply(matrix1, matrix2):
    if matrix1 is None:
        return matrix2
    elif matrix2 is None:
        return matrix1
        
    m1 = [matrix1[0:3], matrix1[3:6] ] # don't need last row
    m2 = [matrix2[0:3], matrix2[3:6], [0,0,1]]

    out = []
    
    for i in range(2):
        for j in range(3):
            out.append( sum(m1[i][k]*m2[k][j] for k in range(3)) )
            
    return out

def parse_path(pathdef, current_pos=0j, matrix = None, svgState=None):
    if matrix is None:
        scaler=lambda z : z
    else:
        scaler=lambda z : applyMatrix(matrix, z)
    if svgState is None:
        svgState = path.SVGState()

    # In the SVG specs, initial movetos are absolute, even if
    # specified as 'm'. This is the default behavior here as well.
    # But if you pass in a current_pos variable, the initial moveto
    # will be relative to that current_pos. This is useful.
    elements = list(_tokenize_path(pathdef))
    # Reverse for easy use of .pop()
    elements.reverse()

    segments = path.Path(svgState = svgState)
    start_pos = None
    command = None

    while elements:

        if elements[-1] in COMMANDS:
            # New command.
            last_command = command  # Used by S and T
            command = elements.pop()
            absolute = command in UPPERCASE
            command = command.upper()
        else:
            # If this element starts with numbers, it is an implicit command
            # and we don't change the command. Check that it's allowed:
            if command is None:
                raise ValueError("Unallowed implicit command in %s, position %s" % (
                    pathdef, len(pathdef.split()) - len(elements)))
            last_command = command  # Used by S and T

        if command == 'M':
            # Moveto command.
            x = elements.pop()
            y = elements.pop()
            pos = float(x) + float(y) * 1j
            if absolute:
                current_pos = pos
            else:
                current_pos += pos

            # when M is called, reset start_pos
            # This behavior of Z is defined in svg spec:
            # http://www.w3.org/TR/SVG/paths.html#PathDataClosePathCommand
            start_pos = current_pos

            # Implicit moveto commands are treated as lineto commands.
            # So we set command to lineto here, in case there are
            # further implicit commands after this moveto.
            command = 'L'

        elif command == 'Z':
            # Close path
            if current_pos != start_pos:
                segments.append(path.Line(scaler(current_pos), scaler(start_pos)))
            if len(segments):
                segments.closed = True
            current_pos = start_pos
            start_pos = None
            command = None  # You can't have implicit commands after closing.

        elif command == 'L':
            x = elements.pop()
            y = elements.pop()
            pos = float(x) + float(y) * 1j
            if not absolute:
                pos += current_pos
            segments.append(path.Line(scaler(current_pos), scaler(pos)))
            current_pos = pos

        elif command == 'H':
            x = elements.pop()
            pos = float(x) + current_pos.imag * 1j
            if not absolute:
                pos += current_pos.real
            segments.append(path.Line(scaler(current_pos), scaler(pos)))
            current_pos = pos

        elif command == 'V':
            y = elements.pop()
            pos = current_pos.real + float(y) * 1j
            if not absolute:
                pos += current_pos.imag * 1j
            segments.append(path.Line(scaler(current_pos), scaler(pos)))
            current_pos = pos

        elif command == 'C':
            control1 = float(elements.pop()) + float(elements.pop()) * 1j
            control2 = float(elements.pop()) + float(elements.pop()) * 1j
            end = float(elements.pop()) + float(elements.pop()) * 1j

            if not absolute:
                control1 += current_pos
                control2 += current_pos
                end += current_pos

            segments.append(path.CubicBezier(scaler(current_pos), scaler(control1), scaler(control2), scaler(end)))
            current_pos = end

        elif command == 'S':
            # Smooth curve. First control point is the "reflection" of
            # the second control point in the previous path.

            if last_command not in 'CS':
                # If there is no previous command or if the previous command
                # was not an C, c, S or s, assume the first control point is
                # coincident with the current point.
                control1 = scaler(current_pos)
            else:
                # The first control point is assumed to be the reflection of
                # the second control point on the previous command relative
                # to the current point.
                control1 = 2 * scaler(current_pos) - segments[-1].control2

            control2 = float(elements.pop()) + float(elements.pop()) * 1j
            end = float(elements.pop()) + float(elements.pop()) * 1j

            if not absolute:
                control2 += current_pos
                end += current_pos

            segments.append(path.CubicBezier(scaler(current_pos), control1, scaler(control2), scaler(end)))
            current_pos = end

        elif command == 'Q':
            control = float(elements.pop()) + float(elements.pop()) * 1j
            end = float(elements.pop()) + float(elements.pop()) * 1j

            if not absolute:
                control += current_pos
                end += current_pos

            segments.append(path.QuadraticBezier(scaler(current_pos), scaler(control), scaler(end)))
            current_pos = end

        elif command == 'T':
            # Smooth curve. Control point is the "reflection" of
            # the second control point in the previous path.

            if last_command not in 'QT':
                # If there is no previous command or if the previous command
                # was not an Q, q, T or t, assume the first control point is
                # coincident with the current point.
                control = scaler(current_pos)
            else:
                # The control point is assumed to be the reflection of
                # the control point on the previous command relative
                # to the current point.
                control = 2 * scaler(current_pos) - segments[-1].control

            end = float(elements.pop()) + float(elements.pop()) * 1j

            if not absolute:
                end += current_pos

            segments.append(path.QuadraticBezier(scaler(current_pos), control, scaler(end)))
            current_pos = end

        elif command == 'A':
            radius = float(elements.pop()) + float(elements.pop()) * 1j
            rotation = float(elements.pop())
            arc = float(elements.pop())
            sweep = float(elements.pop())
            end = float(elements.pop()) + float(elements.pop()) * 1j
           
            if not absolute:
                end += current_pos

            segments.append(path.Arc(current_pos, radius, rotation, arc, sweep, end, scaler))
            current_pos = end

    return segments

def path_from_ellipse(x, y, rx, ry, matrix, state):
    arc = "M %.9f %.9f " % (x-rx,y)
    arc += "A %.9f %.9f 0 0 1 %.9f %.9f " % (rx, ry, x+rx,y) 
    arc += "A %.9f %.9f 0 0 1 %.9f %.9f" % (rx, ry, x-rx,y) 
    return parse_path(arc, matrix=matrix, svgState=state)

def path_from_rect(x,y,w,h,rx,ry, matrix,state):
    if not rx and not ry:
        rect = "M %.9f %.9f h %.9f v %.9f h %.9f Z" % (x,y,w,h,-w)
    else:
        if rx is None:
            rx = ry
        elif ry is None:
            ry = rx
        rect = "M %.9f %.9f h %.9f " % (x+rx,y,w-2*rx)
        rect += "a %.9f %.9f 0 0 1 %.9f %.9f " % (rx, ry, rx, ry)
        rect += "v %.9f " % (h-2*ry)
        rect += "a %.9f %.9f 0 0 1 %.9f %.9f " % (rx, ry, -rx, ry)
        rect += "h %.9f " % -(w-2*rx)
        rect += "a %.9f %.9f 0 0 1 %.9f %.9f " % (rx, ry, -rx, -ry)
        rect += "v %.9f " % -(h-2*ry)
        rect += "a %.9f %.9f 0 0 1 %.9f %.9f Z" % (rx, ry, rx, -ry)
    return parse_path(rect, matrix=matrix, svgState=state)
    
def sizeFromString(text):
    """
    Returns size in mm, if possible.
    """
    text = re.sub(r'\s',r'', text)
    try:
        return float(text)*25.4/96 # px
    except:
        if text[-1] == '%':
            return float(text[:-1]) # NOT mm
        units = text[-2:].lower()
        x = float(text[:-2])
        convert = { 'mm':1, 'cm':10, 'in':25.4, 'px':25.4/96, 'pt':25.4/72, 'pc':12*25.4/72 }
        try:
            return x * convert[units]
        except:
            return x # NOT mm

def rgbFromColor(colorName):
    colorName = colorName.strip().lower()
    if colorName == 'none':
        return None
    cmd = re.split(r'[\s(),]+', colorName)
    if cmd[0] == 'rgb':
        colors = cmd[1:4]
        outColor = []
        for c in colors:
            if c.endswith('%'):
                outColor.append(float(c[:-1]) / 100.)
            else:
                outColor.append(float(c) / 255.)
        return tuple(outColor)
    elif colorName.startswith('#'):
        if len(colorName) == 4:
            return (int(colorName[1],16)/15., int(colorName[2],16)/15., int(colorName[3],16)/15.)
        else:
            return (int(colorName[1:3],16)/255., int(colorName[3:5],16)/255., int(colorName[5:7],16)/255.)
    else:
        return SVG_COLORS[colorName]        
        
        
def getPathsFromSVG(svg):
    def updateStateCommand(state,cmd,arg):
        if cmd == 'fill':
            state.fill = rgbFromColor(arg)
        elif cmd == 'fill-opacity':
            state.fillOpacity = float(arg)
        elif cmd == 'fill-rule':
            state.fillRule = arg
#            if state.fill is None:
#                state.fill = (0.,0.,0.)
        elif cmd == 'stroke':
            state.stroke = rgbFromColor(arg)
        elif cmd == 'stroke-opacity':
            state.strokeOpacity = rgbFromColor(arg)
        elif cmd == 'stroke-width':
            state.strokeWidth = float(arg)
        elif cmd == 'vector-effect':
            state.strokeWidthScaling = 'non-scaling-stroke' not in cmd
            # todo better scaling for non-uniform cases?
    
    def updateState(tree,state,matrix):
        state = state.clone()
        try:
            style = re.sub(r'\s',r'', tree.attrib['style']).lower()
            for item in style.split(';'):
                cmd,arg = item.split(':')[:2]
                updateStateCommand(state,cmd,arg)
        except:
            pass
            
        for item in tree.attrib:
            try:
                updateStateCommand(state,item,tree.attrib[item])
            except:
                pass
                
        if state.strokeWidth and state.strokeWidthScaling:
            # this won't work great for non-uniform scaling
            h = abs(applyMatrix(matrix, complex(0,state.strokeWidth)) - applyMatrix(matrix, 0j))
            w = abs(applyMatrix(matrix, complex(state.strokeWidth,0)) - applyMatrix(matrix, 0j))
            state.strokeWidth = (h+w)/2
        return state
        
    def reorder(a,b,c,d,e,f):
        return [a,c,e, b,d,f]            
        
    def updateMatrix(tree, matrix):
        try:
            transformList = re.split(r'\)[\s,]+', tree.attrib['transform'].strip().lower())
        except KeyError:
            return matrix
            
        for transform in transformList:
            cmd = re.split(r'[,()\s]+', transform)
            
            updateMatrix = None
            
            if cmd[0] == 'matrix':
                updateMatrix = reorder(*list(map(float, cmd[1:7])))
            elif cmd[0] == 'translate':
                x = float(cmd[1])
                if len(cmd) >= 3 and cmd[2] != '':
                    y = float(cmd[2])
                else:
                    y = 0
                updateMatrix = reorder(1,0,0,1,x,y)
            elif cmd[0] == 'scale':
                x = float(cmd[1])
                if len(cmd) >= 3 and cmd[2] != '':
                    y = float(cmd[2])
                else:
                    y = x
                updateMatrix = reorder(x,0,0, y,0,0)
            elif cmd[0] == 'rotate':
                theta = float(cmd[1]) * math.pi / 180.
                c = math.cos(theta)
                s = math.sin(theta)
                updateMatrix = [c, -s, 0,  s, c, 0]
                if len(cmd) >= 4 and cmd[2] != '':
                    x = float(cmd[2])
                    y = float(cmd[3])
                    updateMatrix = matrixMultiply(updateMatrix, [1,0,-x, 0,1,-y])
                    updateMatrix = matrixMultiply([1,0,x, 0,1,y], updateMatrix)
            elif cmd[0] == 'skewX':
                theta = float(cmd[1]) * math.pi / 180.
                updateMatrix = [1, math.tan(theta), 0,  0,1,0]
            elif cmd[0] == 'skewY':
                theta = float(cmd[1]) * math.pi / 180.
                updateMatrix = [1,0,0, math.tan(theta),1,0]
                
            matrix = matrixMultiply(matrix, updateMatrix)
            
        return matrix
        
    def updateStateAndMatrix(tree,state,matrix):
        matrix = updateMatrix(tree,matrix)
        return updateState(tree,state,matrix),matrix
        
    def getPaths(paths, matrix, tree, state, savedElements):
        def getFloat(attribute,default=0.):
            try:
                return float(tree.attrib[attribute].strip())
            except KeyError:
                return default

        tag = re.sub(r'.*}', '', tree.tag).lower()
        try:
            savedElements[tree.attrib['id']] = tree
        except KeyError:
            pass
            
        state, matrix = updateStateAndMatrix(tree, state, matrix)
        if tag == 'path':
            path = parse_path(tree.attrib['d'], matrix=matrix, svgState=state)
            if len(path):
                paths.append(path)
        elif tag == 'circle':
            path = path_from_ellipse(getFloat('cx'), getFloat('cy'), getFloat('r'), getFloat('r'), matrix, state)
            paths.append(path)
        elif tag == 'ellipse':
            path = path_from_ellipse(getFloat('cx'), getFloat('cy'), getFloat('rx'), getFloat('ry'), matrix, state)
            paths.append(path)
        elif tag == 'line':
            x1 = getFloat('x1')
            y1 = getFloat('y1')
            x2 = getFloat('x2')
            y2 = getFloat('y2')
            p = 'M %.9f %.9f L %.9f %.9f' % (x1,y1,x2,y2)
            path = parse_path(p, matrix=matrix, svgState=state)
            paths.append(path)
        elif tag == 'polygon':
            points = re.split(r'[\s,]+', tree.attrib['points'].strip())
            p = ' '.join(['M', points[0], points[1], 'L'] + points[2:] + ['Z'])
            path = parse_path(p, matrix=matrix, svgState=state)
            paths.append(path)
        elif tag == 'polyline':
            points = re.split(r'[\s,]+', tree.attrib['points'].strip())
            p = ' '.join(['M', points[0], points[1], 'L'] + points[2:])
            path = parse_path(p, matrix=matrix, svgState=state)
            paths.append(path)
        elif tag == 'rect':
            x = getFloat('x')
            y = getFloat('y')
            w = getFloat('width')
            h = getFloat('height')
            rx = getFloat('rx',default=None)
            ry = getFloat('ry',default=None)
            path = path_from_rect(x,y,w,h,rx,ry, matrix,state)
            paths.append(path)
        elif tag == 'g' or tag == 'svg':
            for child in tree:
                getPaths(paths, matrix, child, state, savedElements)
        elif tag == 'use':
            try:
                link = None
                for tag in tree.attrib:
                    if tag.strip().lower().endswith("}href"):
                        link = tree.attrib[tag]
                        break
                if link is None or link[0] != '#':
                    raise KeyError
                source = savedElements[link[1:]]
                x = 0
                y = 0
                try:
                    x = float(tree.attrib['x'])
                except:
                    pass
                try:
                    y = float(tree.attrib['y'])
                except:
                    pass
                # TODO: handle width and height? (Inkscape does not)
                matrix = matrixMultiply(matrix, reorder(1,0,0,1,x,y))
                getPaths(paths, matrix, source, state, dict(savedElements))
            except KeyError:
                pass

    def scale(width, height, viewBox, z):
        x = (z.real - viewBox[0]) / (viewBox[2] - viewBox[0]) * width
        y = (viewBox[3]-z.imag) / (viewBox[3] - viewBox[1]) * height
        return complex(x,y)
        
    paths = []

    try:
        width = sizeFromString(svg.attrib['width'].strip())
    except KeyError:
        width = None
    try:
        height = sizeFromString(svg.attrib['height'].strip())
    except KeyError:
        height = None
    
    try:
        viewBox = list(map(float, re.split(r'[\s,]+', svg.attrib['viewBox'].strip())))
    except KeyError:
        if width is None or height is None:
            raise KeyError
        viewBox = [0, 0, width*96/25.4, height*96/25.4]
        
    if width is None:
        width = viewBox[2] * 25.4/96
    
    if height is None:
        height = viewBox[3] * 25.4/96
        
    viewBoxWidth = viewBox[2]
    viewBoxHeight = viewBox[3]
    
    viewBox[2] += viewBox[0]
    viewBox[3] += viewBox[1]
    
    try:
        preserve = svg.attrib['preserveAspectRatio'].strip().lower().split()
        if len(preserve[0]) != 8:
            raise KeyError
        if len(preserve)>=2 and preserve[1] == 'slice':
            if viewBoxWidth/viewBoxHeight > width/height:
                # viewbox is wider than viewport, so scale by height to ensure
                # viewbox covers the viewport
                rescale = height / viewBoxHeight
            else:
                rescale = width / viewBoxWidth
        else:
            if viewBoxWidth/viewBoxHeight > width/height:
                # viewbox is wider than viewport, so scale by width to ensure
                # viewport covers the viewbox
                rescale = width / viewBoxWidth
            else:
                rescale = height / viewBoxHeight
        matrix = [rescale, 0, 0,    
                  0, rescale, 0];

        if preserve[0][0:4] == 'xmin':
            # viewBox[0] to 0
            matrix[2] = -viewBox[0] * rescale
        elif preserve[0][0:4] == 'xmid':
            # viewBox[0] to width/2
            matrix[2] = -viewBox[0] * rescale + width/2
        else: # preserve[0][0:4] == 'xmax':
            # viewBox[0] to width
            matrix[2] = -viewBox[0] * rescale + width
        
        if preserve[0][4:8] == 'ymin':
            # viewBox[1] to 0
            matrix[5] = -viewBox[1] * rescale
        elif preserve[0][4:8] == 'ymid':
            # viewBox[0] to width/2
            matrix[5] = -viewBox[1] * rescale + height/2
        else: # preserve[0][4:8] == 'xmax':
            # viewBox[0] to width
            matrix[5] = -viewBox[1] * rescale + height
    except:
        matrix = [ width/viewBoxWidth, 0, -viewBox[0]* width/viewBoxWidth,  
                   0, -height/viewBoxHeight, viewBox[3]*height/viewBoxHeight ]
        
    getPaths(paths, matrix, svg, path.SVGState(), {})

    return ( paths, applyMatrix(matrix, complex(viewBox[0], viewBox[1])), 
                applyMatrix(matrix, complex(viewBox[2], viewBox[3])) )

def getPathsFromSVGFile(filename):
    return getPathsFromSVG(ET.parse(filename).getroot())
    