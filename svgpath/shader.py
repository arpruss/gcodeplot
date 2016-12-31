import math
from operator import itemgetter

class Shader(object):
    MODE_EVEN_ODD = 0
    MODE_NONZERO = 1

    def __init__(self, unshadedThreshold=1., lightestSpacing=3., darkestSpacing=0.5, angle=45, crossHatch=False):
        self.unshadedThreshold = unshadedThreshold
        self.lightestSpacing = lightestSpacing
        self.darkestSpacing = darkestSpacing
        self.angle = angle
        self.secondaryAngle = angle + 90
        self.crossHatch = False
        
    def isActive(self):
        return self.unshadedThreshold > 0.000001
        
    def setDrawingDirectionAngle(self, drawingDirectionAngle):
        self.drawingDirectionAngle = drawingDirectionAngle
        
        if drawingDirectionAngle is None:
            return
            
        if 90 < (self.angle - drawingDirectionAngle) % 360 < 270:
            self.angle = (self.angle + 180) % 360
        if 90 < (self.secondaryAngle - drawingDirectionAngle) % 360 < 270:
            self.secondaryAngle = (self.secondaryAngle + 180) % 360
        
    def shade(self, polygon, grayscale, avoidOutline=True, mode=None):
        if mode is None:
            mode = Shader.MODE_EVEN_ODD
        if grayscale >= self.unshadedThreshold:
            return []
        intensity = (self.unshadedThreshold-grayscale) / float(self.unshadedThreshold)
        spacing = self.lightestSpacing * (1-intensity) + self.darkestSpacing * intensity
        lines = Shader.shadePolygon(polygon, self.angle, spacing, avoidOutline=avoidOutline, mode=mode, alternate=(self.drawingDirectionAngle is None))
        if self.crossHatch:
            lines += Shader.shadePolygon(polygon, self.angle+90, spacing, avoidOutline=avoidOutline, mode=mode, alternate=(self.drawingDirectionAngle is None))
        return lines
        
    @staticmethod
    def shadePolygon(polygon, angleDegrees, spacing, avoidOutline=True, mode=None, alternate=True):
        if mode is None:
            mode = Shader.MODE_EVEN_ODD
    
        rotate = complex(math.cos(angleDegrees * math.pi / 180.), math.sin(angleDegrees * math.pi / 180.))
        
        polygon = [(line[0] / rotate,line[1] / rotate) for line in polygon]
        
        spacing = float(spacing)

        toAvoid = list(set(line[0].imag for line in polygon)|set(line[1].imag for line in polygon))

        if len(toAvoid) <= 1:
            deltaY = (toAvoid[0]-spacing/2.) % spacing
        else:
            # find largest interval
            toAvoid.sort()
            largestIndex = 0
            largestLen = 0
            for i in range(len(toAvoid)):
                l = ( toAvoid[i] - toAvoid[i-1] ) % spacing
                if l > largestLen:
                    largestIndex = i
                    largestLen = l
            deltaY = (toAvoid[largestIndex-1] + largestLen / 2.) % spacing
            
        minY = min(min(line[0].imag,line[1].imag) for line in polygon)
        maxY = max(max(line[0].imag,line[1].imag) for line in polygon)

        y = minY + ( - minY ) % spacing + deltaY    
        
        if y > minY + spacing:
            y -= spacing
            
        y += 0.01
        
        odd = False

        all = []
        
        while y < maxY:
            intersections = []
            for line in polygon:
                z = line[0]
                z1 = line[1]
                if z1.imag == y or z.imag == y: # roundoff generated corner case -- ignore -- TODO
                    break
                if z1.imag < y < z.imag or z.imag < y < z1.imag:
                    if z1.real == z.real:
                        intersections.append(( complex(z.real, y), z.imag<y, line))
                    else:
                        m = (z1.imag-z.imag)/(z1.real-z.real)
                        # m * (x - z.real) = y - z.imag
                        # so: x = (y - z.imag) / m + z.real
                        intersections.append( (complex((y-z.imag)/m + z.real, y), z.imag<y, line) )
        
            intersections.sort(key=lambda datum: datum[0].real)
            
            thisLine = []
            if mode == Shader.MODE_EVEN_ODD:
                for i in range(0,len(intersections)-1,2):
                    thisLine.append((intersections[i], intersections[i+1]))
            elif mode == Shader.MODE_NONZERO:
                count = 0
                for i in range(0,len(intersections)-1):
                    if intersections[i][1]:
                        count += 1
                    else:
                        count -= 1
                    if count != 0:
                        thisLine.append((intersections[i], intersections[i+1]))
            else:
                raise ValueError()
                   
            if odd and alternate:
                thisLine = list(reversed([(l[1],l[0]) for l in thisLine]))
                
            if not avoidOutline and len(thisLine) and len(all) and all[-1][1][2] == thisLine[0][0][2]:
                # follow along outline to avoid an extra pen bob
                all.append( (all[-1][1], thisLine[0][0]) )
                
            all += thisLine
                
            odd = not odd
                
            y += spacing

        return [(line[0][0]*rotate, line[1][0]*rotate) for line in all]
    
                    
if __name__ == '__main__':
    polygon=(0+0j, 10+10j, 10+0j, 0+0j)
    print(shadePolygon(polygon,90,1))
                    