from __future__ import division
from math import sqrt, cos, sin, acos, degrees, radians, log
try:
    from collections.abc import MutableSequence
except ImportError:
    from collections import MutableSequence

# This file contains classes for the different types of SVG path segments as
# well as a Path object that contains a sequence of path segments.

MIN_DEPTH = 5
ERROR = 1e-12

def segment_length(curve, start, end, start_point, end_point, error, min_depth, depth):
    """Recursively approximates the length by straight lines"""
    mid = (start + end) / 2
    mid_point = curve.point(mid)
    length = abs(end_point - start_point)
    first_half = abs(mid_point - start_point)
    second_half = abs(end_point - mid_point)

    length2 = first_half + second_half
    if (length2 - length > error) or (depth < min_depth):
        # Calculate the length of each segment:
        depth += 1
        return (segment_length(curve, start, mid, start_point, mid_point,
                               error, min_depth, depth) +
                segment_length(curve, mid, end, mid_point, end_point,
                               error, min_depth, depth))
    # This is accurate enough.
    return length2

def approximate(path, start, end, start_point, end_point, max_error, depth, max_depth):
    if depth >= max_depth:
        return [start_point, end_point]
    actual_length = path.measure(start, end, error=max_error/4)
    linear_length = abs(end_point - start_point)
    # Worst case deviation given a fixed linear_length and actual_length would probably be 
    # a symmetric tent shape (I haven't proved it -- TODO).
    deviationSquared = (actual_length/2)**2 - (linear_length/2)**2
    if deviationSquared <= max_error ** 2:
        return [start_point, end_point]
    else:
        mid = (start+end)/2.
        mid_point = path.point(mid)
        return ( approximate(path, start, mid, start_point, mid_point, max_error, depth+1, max_depth)[:-1] + 
                    approximate(path, mid, end, mid_point, end_point, max_error, depth+1, max_depth) )
                    
def removeCollinear(points, error, pointsToKeep=set()):
    out = []
    
    lengths = [0]

    for i in range(1,len(points)):
        lengths.append(lengths[-1] + abs(points[i]-points[i-1]))
        
    def length(a,b):
        return lengths[b] - lengths[a]
    
    i = 0
    
    while i < len(points):
        j = len(points) - 1
        while i < j:
            deviationSquared = (length(i, j)/2)**2 - (abs(points[j]-points[i])/2)**2
            if deviationSquared <= error ** 2 and set(range(i+1,j)).isdisjoint(pointsToKeep):
                out.append(points[i])
                i = j
                break
            j -= 1
        out.append(points[j])
        i += 1

    return out

class Segment(object):
    def __init__(self, start, end):
        self.start = start
        self.end = end
        
    def measure(self, start, end, error=ERROR, min_depth=MIN_DEPTH):
        return Path(self).measure(start, end, error=error, min_depth=min_depth)

    def getApproximatePoints(self, error=0.001, max_depth=32):
        points = approximate(self, 0., 1., self.point(0.), self.point(1.), error, 0, max_depth)
        return points

class Line(Segment):
    def __init__(self, start, end):
        super(Line, self).__init__(start,end)

    def __repr__(self):
        return 'Line(start=%s, end=%s)' % (self.start, self.end)

    def __eq__(self, other):
        if not isinstance(other, Line):
            return NotImplemented
        return self.start == other.start and self.end == other.end

    def __ne__(self, other):
        if not isinstance(other, Line):
            return NotImplemented
        return not self == other
        
    def getApproximatePoints(self, error=0.001, max_depth=32):
        return [self.start, self.end]

    def point(self, pos):
        if pos == 0.:
            return self.start
        elif pos == 1.:
            return self.end
        distance = self.end - self.start
        return self.start + distance * pos

    def length(self, error=None, min_depth=None):
        distance = (self.end - self.start)
        return sqrt(distance.real ** 2 + distance.imag ** 2)


class CubicBezier(Segment):
    def __init__(self, start, control1, control2, end):
        super(CubicBezier, self).__init__(start,end)
        self.control1 = control1
        self.control2 = control2

    def __repr__(self):
        return 'CubicBezier(start=%s, control1=%s, control2=%s, end=%s)' % (
               self.start, self.control1, self.control2, self.end)

    def __eq__(self, other):
        if not isinstance(other, CubicBezier):
            return NotImplemented
        return self.start == other.start and self.end == other.end and \
               self.control1 == other.control1 and self.control2 == other.control2

    def __ne__(self, other):
        if not isinstance(other, CubicBezier):
            return NotImplemented
        return not self == other

    def is_smooth_from(self, previous):
        """Checks if this segment would be a smooth segment following the previous"""
        if isinstance(previous, CubicBezier):
            return (self.start == previous.end and
                    (self.control1 - self.start) == (previous.end - previous.control2))
        else:
            return self.control1 == self.start

    def point(self, pos):
        """Calculate the x,y position at a certain position of the path"""
        if pos == 0.:
            return self.start
        elif pos == 1.:
            return self.end
        return ((1 - pos) ** 3 * self.start) + \
               (3 * (1 - pos) ** 2 * pos * self.control1) + \
               (3 * (1 - pos) * pos ** 2 * self.control2) + \
               (pos ** 3 * self.end)

    def length(self, error=ERROR, min_depth=MIN_DEPTH):
        """Calculate the length of the path up to a certain position"""
        start_point = self.point(0)
        end_point = self.point(1)
        return segment_length(self, 0, 1, start_point, end_point, error, min_depth, 0)


class QuadraticBezier(Segment):
    def __init__(self, start, control, end):
        super(QuadraticBezier, self).__init__(start,end)
        self.control = control

    def __repr__(self):
        return 'QuadraticBezier(start=%s, control=%s, end=%s)' % (
               self.start, self.control, self.end)

    def __eq__(self, other):
        if not isinstance(other, QuadraticBezier):
            return NotImplemented
        return self.start == other.start and self.end == other.end and \
               self.control == other.control

    def __ne__(self, other):
        if not isinstance(other, QuadraticBezier):
            return NotImplemented
        return not self == other

    def is_smooth_from(self, previous):
        """Checks if this segment would be a smooth segment following the previous"""
        if isinstance(previous, QuadraticBezier):
            return (self.start == previous.end and
                    (self.control - self.start) == (previous.end - previous.control))
        else:
            return self.control == self.start

    def point(self, pos):
        if pos == 0.:
            return self.start
        elif pos == 1.:
            return self.end
        return (1 - pos) ** 2 * self.start + 2 * (1 - pos) * pos * self.control + \
               pos ** 2 * self.end

    def length(self, error=None, min_depth=None):
        a = self.start - 2*self.control + self.end
        b = 2*(self.control - self.start)
        a_dot_b = a.real*b.real + a.imag*b.imag

        if abs(a) < 1e-12:
            s = abs(b)
        elif abs(a_dot_b + abs(a)*abs(b)) < 1e-12:
            k = abs(b)/abs(a)
            if k >= 2:
                s = abs(b) - abs(a)
            else:
                s = abs(a)*(k**2/2 - k + 1)
        else:
            # For an explanation of this case, see
            # http://www.malczak.info/blog/quadratic-bezier-curve-length/
            A = 4 * (a.real ** 2 + a.imag ** 2)
            B = 4 * (a.real * b.real + a.imag * b.imag)
            C = b.real ** 2 + b.imag ** 2

            Sabc = 2 * sqrt(A + B + C)
            A2 = sqrt(A)
            A32 = 2 * A * A2
            C2 = 2 * sqrt(C)
            BA = B / A2

            s = (A32 * Sabc + A2 * B * (Sabc - C2) + (4 * C * A - B ** 2) *
                    log((2 * A2 + BA + Sabc) / (BA + C2))) / (4 * A32)
        return s

class Arc(Segment):
    def __init__(self, start, radius, rotation, arc, sweep, end, scaler=lambda z:z):
        """radius is complex, rotation is in degrees,
           large and sweep are 1 or 0 (True/False also work)"""

        super(Arc, self).__init__(scaler(start),scaler(end))
        self.start0 = start
        self.end0 = end
        self.radius = radius
        self.rotation = rotation
        self.arc = bool(arc)
        self.sweep = bool(sweep)
        self.scaler = scaler

        self._parameterize()
        
    def __repr__(self):
        return 'Arc(start0=%s, radius=%s, rotation=%s, arc=%s, sweep=%s, end0=%s, scaler=%s)' % (
               self.start0, self.radius, self.rotation, self.arc, self.sweep, self.end0, self.scaler)

    def __eq__(self, other):
        if not isinstance(other, Arc):
            return NotImplemented
        return self.start == other.start and self.end == other.end and \
               self.radius == other.radius and self.rotation == other.rotation and \
               self.arc == other.arc and self.sweep == other.sweep

    def __ne__(self, other):
        if not isinstance(other, Arc):
            return NotImplemented
        return not self == other

    def _parameterize(self):
        # Conversion from endpoint to center parameterization
        # http://www.w3.org/TR/SVG/implnote.html#ArcImplementationNotes

        cosr = cos(radians(self.rotation))
        sinr = sin(radians(self.rotation))
        dx = (self.start0.real - self.end0.real) / 2
        dy = (self.start0.imag - self.end0.imag) / 2
        x1prim = cosr * dx + sinr * dy
        x1prim_sq = x1prim * x1prim
        y1prim = -sinr * dx + cosr * dy
        y1prim_sq = y1prim * y1prim

        rx = self.radius.real
        rx_sq = rx * rx
        ry = self.radius.imag
        ry_sq = ry * ry

        # Correct out of range radii
        radius_check = (x1prim_sq / rx_sq) + (y1prim_sq / ry_sq)
        if radius_check > 1:
            rx *= sqrt(radius_check)
            ry *= sqrt(radius_check)
            rx_sq = rx * rx
            ry_sq = ry * ry

        t1 = rx_sq * y1prim_sq
        t2 = ry_sq * x1prim_sq
        c = sqrt(abs((rx_sq * ry_sq - t1 - t2) / (t1 + t2)))

        if self.arc == self.sweep:
            c = -c
        cxprim = c * rx * y1prim / ry
        cyprim = -c * ry * x1prim / rx

        self.center = complex((cosr * cxprim - sinr * cyprim) +
                              ((self.start0.real + self.end0.real) / 2),
                              (sinr * cxprim + cosr * cyprim) +
                              ((self.start0.imag + self.end0.imag) / 2))

        ux = (x1prim - cxprim) / rx
        uy = (y1prim - cyprim) / ry
        vx = (-x1prim - cxprim) / rx
        vy = (-y1prim - cyprim) / ry
        n = sqrt(ux * ux + uy * uy)
        p = ux
        theta = degrees(acos(p / n))
        if uy < 0:
            theta = -theta
        self.theta = theta % 360

        n = sqrt((ux * ux + uy * uy) * (vx * vx + vy * vy))
        p = ux * vx + uy * vy
        d = p/n
        # In certain cases the above calculation can through inaccuracies
        # become just slightly out of range, f ex -1.0000000000000002.
        if d > 1.0:
            d = 1.0
        elif d < -1.0:
            d = -1.0
        delta = degrees(acos(d))
        if (ux * vy - uy * vx) < 0:
            delta = -delta
        self.delta = delta % 360
        if not self.sweep:
            self.delta -= 360
            
    def point(self, pos):
        if pos == 0.:
            return self.start
        elif pos == 1.:
            return self.end
        angle = radians(self.theta + (self.delta * pos))
        cosr = cos(radians(self.rotation))
        sinr = sin(radians(self.rotation))

        x = (cosr * cos(angle) * self.radius.real - sinr * sin(angle) *
             self.radius.imag + self.center.real)
        y = (sinr * cos(angle) * self.radius.real + cosr * sin(angle) *
             self.radius.imag + self.center.imag)
        return self.scaler(complex(x, y))

    def length(self, error=ERROR, min_depth=MIN_DEPTH):
        """The length of an elliptical arc segment requires numerical
        integration, and in that case it's simpler to just do a geometric
        approximation, as for cubic bezier curves.
        """
        start_point = self.point(0)
        end_point = self.point(1)
        return segment_length(self, 0, 1, start_point, end_point, error, min_depth, 0)

class SVGState(object):
    def __init__(self, fill=(0.,0.,0.), fillOpacity=None, fillRule='nonzero', stroke=None, strokeOpacity=None, strokeWidth=0.1, strokeWidthScaling=True):
        self.fill = fill
        self.fillOpacity = fillOpacity
        self.fillRule = fillRule
        self.stroke = stroke
        self.strokeOpacity = strokeOpacity
        self.strokeWidth = strokeWidth
        self.strokeWidthScaling = strokeWidthScaling
                
    def clone(self):
        return SVGState(fill=self.fill, fillOpacity=self.fillOpacity, fillRule=self.fillRule, stroke=self.stroke, strokeOpacity=self.strokeOpacity,
                strokeWidth=self.strokeWidth, strokeWidthScaling=self.strokeWidthScaling)
        
class Path(MutableSequence):
    """A Path is a sequence of path segments"""

    # Put it here, so there is a default if unpickled.
    _closed = False

    def __init__(self, *segments, **kw):
        self._segments = list(segments)
        self._length = None
        self._lengths = None
        if 'closed' in kw:
            self.closed = kw['closed']
        if 'svgState' in kw:
            self.svgState = kw['svgState']
        else:
            self.svgState = SVGState()

    def __getitem__(self, index):
        return self._segments[index]

    def __setitem__(self, index, value):
        self._segments[index] = value
        self._length = None

    def __delitem__(self, index):
        del self._segments[index]
        self._length = None

    def insert(self, index, value):
        self._segments.insert(index, value)
        self._length = None

    def reverse(self):
        # Reversing the order of a path would require reversing each element
        # as well. That's not implemented.
        raise NotImplementedError

    def __len__(self):
        return len(self._segments)

    def __repr__(self):
        return 'Path(%s, closed=%s)' % (
            ', '.join(repr(x) for x in self._segments), self.closed)

    def __eq__(self, other):
        if not isinstance(other, Path):
            return NotImplemented
        if len(self) != len(other):
            return False
        for s, o in zip(self._segments, other._segments):
            if not s == o:
                return False
        return True

    def __ne__(self, other):
        if not isinstance(other, Path):
            return NotImplemented
        return not self == other

    def _calc_lengths(self, error=ERROR, min_depth=MIN_DEPTH):
    ## TODO: check if error has decreased since last calculation
        if self._length is not None:
            return

        lengths = [each.length(error=error, min_depth=min_depth) for each in self._segments]
        self._length = sum(lengths)
        self._lengths = [each / (1 if self._length==0. else self._length) for each in lengths]

    def point(self, pos, error=ERROR):
        # Shortcuts
        if pos == 0.0:
            return self._segments[0].point(pos)
        if pos == 1.0:
            return self._segments[-1].point(pos)

        self._calc_lengths(error=error)
        # Find which segment the point we search for is located on:
        segment_start = 0
        for index, segment in enumerate(self._segments):
            segment_end = segment_start + self._lengths[index]
            if segment_end >= pos:
                # This is the segment! How far in on the segment is the point?
                segment_pos = (pos - segment_start) / (segment_end - segment_start)
                break
            segment_start = segment_end

        return segment.point(segment_pos)

    def length(self, error=ERROR, min_depth=MIN_DEPTH):
        self._calc_lengths(error, min_depth)
        return self._length
        
    def measure(self, start, end, error=ERROR, min_depth=MIN_DEPTH):
        self._calc_lengths(error=error)
        if start == 0.0 and end == 1.0:
            return self.length()
        length = 0
        segment_start = 0
        for index, segment in enumerate(self._segments):
            if end <= segment_start:
                break
            segment_end = segment_start + self._lengths[index]
            if start < segment_end:
                # this segment intersects the part of the path we want
                if start <= segment_start and segment_end <= end:
                    # whole segment is contained in the part of the path
                    length += self._lengths[index] * self._length
                else:
                    if start <= segment_start:
                        start_in_segment = 0. 
                    else:
                        start_in_segment = (start-segment_start)/(segment_end-segment_start)
                    if segment_end <= end:
                        end_in_segment = 1.
                    else:
                        end_in_segment = (end-segment_start)/(segment_end-segment_start)
                    segment = self._segments[index]
                    length += segment_length(segment, start_in_segment, end_in_segment, segment.point(start_in_segment), 
                                segment.point(end_in_segment), error, MIN_DEPTH, 0)
            segment_start = segment_end
        return length
        
    def _is_closable(self):
        """Returns true if the end is on the start of a segment"""
        try:
            end = self[-1].end
        except:
            return False
        for segment in self:
            if segment.start == end:
                return True
        return False
        
    def breakup(self):
        paths = []
        prevEnd = None
        segments = []
        for segment in self._segments:
            if prevEnd is None or segment.point(0.) == prevEnd:
                segments.append(segment)
            else:
                paths.append(Path(*segments, svgState=self.svgState))
                segments = [segment]
            prevEnd = segment.point(1.)
                
        if len(segments) > 0:
            paths.append(Path(*segments, svgState=self.svgState))
            
        return paths
        
    def linearApproximation(self, error=0.001, max_depth=32):
        closed = False
        keepSegmentIndex = 0
        if self.closed:
            end = self[-1].end
            for i,segment in enumerate(self):
                if segment.start == end:
                    keepSegmentIndex = i
                    closed = True
                    break
        
        keepSubpathIndex = 0
        keepPointIndex = 0

        subpaths = []
        subpath = []
        prevEnd = None
        for i,segment in enumerate(self._segments):
            if prevEnd is None or segment.start == prevEnd:
                if i == keepSegmentIndex:
                    keepSubpathIndex = len(subpaths)
                    keepPointIndex = len(subpath)
            else:
                subpaths.append(subpath)
                subpath = []
            subpath += segment.getApproximatePoints(error=error/2., max_depth=max_depth)
            prevEnd = segment.end
                
        if len(subpath) > 0:
            subpaths.append(subpath)
            
        linearPath = Path(svgState=self.svgState)
        
        for i,subpath in enumerate(subpaths):
            keep = set((keepPointIndex,)) if i == keepSubpathIndex else set() 
            special = None
            if i == keepSubpathIndex:
                special = subpath[keepPointIndex]
            points = removeCollinear(subpath, error=error/2., pointsToKeep=keep)
#            points = subpath
            
            for j in range(len(points)-1):
                linearPath.append(Line(points[j], points[j+1]))
        
        linearPath.closed = self.closed and linearPath._is_closable()
        linearPath.svgState = self.svgState

        return linearPath

    def getApproximateLines(self, error=0.001, max_depth=32):
        lines = []
        for subpath in self.breakup():
            points = subpath.getApproximatePoints(error=error, max_depth=max_depth)
            for i in range(len(points)-1):
                lines.append(points[i],points[i+1])
        return lines

    @property
    def closed(self):
        """Checks that the path is closed"""
        return self._closed and self._is_closable()

    @closed.setter
    def closed(self, value):
        value = bool(value)
        if value and not self._is_closable():
            raise ValueError("End does not coincide with a segment start.")
        self._closed = value

    def d(self):
        if self.closed:
            segments = self[:-1]
        else:
            segments = self[:]

        current_pos = None
        parts = []
        previous_segment = None
        end = self[-1].end

        for segment in segments:
            start = segment.start
            # If the start of this segment does not coincide with the end of
            # the last segment or if this segment is actually the close point
            # of a closed path, then we should start a new subpath here.
            if current_pos != start or (self.closed and start == end):
                parts.append('M {0:G},{1:G}'.format(start.real, start.imag))

            if isinstance(segment, Line):
                parts.append('L {0:G},{1:G}'.format(
                    segment.end.real, segment.end.imag)
                )
            elif isinstance(segment, CubicBezier):
                if segment.is_smooth_from(previous_segment):
                    parts.append('S {0:G},{1:G} {2:G},{3:G}'.format(
                        segment.control2.real, segment.control2.imag,
                        segment.end.real, segment.end.imag)
                    )
                else:
                    parts.append('C {0:G},{1:G} {2:G},{3:G} {4:G},{5:G}'.format(
                        segment.control1.real, segment.control1.imag,
                        segment.control2.real, segment.control2.imag,
                        segment.end.real, segment.end.imag)
                    )
            elif isinstance(segment, QuadraticBezier):
                if segment.is_smooth_from(previous_segment):
                    parts.append('T {0:G},{1:G}'.format(
                        segment.end.real, segment.end.imag)
                    )
                else:
                    parts.append('Q {0:G},{1:G} {2:G},{3:G}'.format(
                        segment.control.real, segment.control.imag,
                        segment.end.real, segment.end.imag)
                    )

            elif isinstance(segment, Arc):
                parts.append('A {0:G},{1:G} {2:G} {3:d},{4:d} {5:G},{6:G}'.format(
                    segment.radius.real, segment.radius.imag, segment.rotation,
                    int(segment.arc), int(segment.sweep),
                    segment.end.real, segment.end.imag)
                )
            current_pos = segment.end
            previous_segment = segment

        if self.closed:
            parts.append('Z')

        return ' '.join(parts)
        
