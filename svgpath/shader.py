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
        self.crossHatch = False
        
    def shadePolygon(polygon, grayscale, mode=Shader.MODE_EVEN_ODD):
        if grayscale >= self.unshadedThreshold:
            return []
        intensity = (self.unshadedThreshold-grayscale) / float(self.unshadedThreshold)
        spacing = self.lightestSpacing * (1-intensity) + self.darkestSpacing * intensity
        lines = shadePolygon(polygon, self.angle, spacing, mode=self.mode)
        if self.crossHatch:
            lines += shadePolygon(polygon, self.angle+90, spacing, mode=self.mode)
        return lines

    @staticmethod
    def shadePolygon(polygon, angleDegrees, spacing, mode=Shader.MODE_EVEN_ODD):
        rotate = complex(math.cos(angleDegrees * math.pi / 180.), math.sin(angleDegrees * math.pi / 180.))
        
        polygon = [z / rotate for z in polygon]
        
        spacing = float(spacing)

        toAvoid = list(set(z.imag for z in polygon))

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
            
        minY = min(z.imag for z in polygon)
        maxY = max(z.imag for z in polygon)

        lines = []
        
        y = minY + ( - minY ) % spacing + deltaY    
        
        odd = False
        
        while y < maxY:
            thisLine = []
            intersections = []
            for i,z in enumerate(polygon[:-1]):
                z1 = polygon[i+1]
                if z1.imag == y or z.imag == y: # roundoff generated corner case -- ignore -- TODO
                    break
                if z1.imag < y < z.imag or z.imag < y < z1.imag:
                    if z1.real == z.real:
                        intersections.append((z.real,z1.imag<y))
                    else:
                        m = (z1.imag-z.imag)/(z1.real-z.real)
                        # m * (x - z.real) = y - z.imag
                        # so: x = (y - z.imag) / m + z.real
                        intersections.append( ((y-z.imag)/m + z.real,z.imag<y) )
        
            intersections.sort(key=itemgetter(0))
            
            if mode == Shader.MODE_EVEN_ODD:
                for i in range(0,len(intersections)-1,2):
                    thisLine.append((complex(intersections[i][0], y),complex(intersections[i+1][0], y)))
            elif mode == Shader.MODE_NONZERO:
                count = 0
                for i in range(0,len(intersections)-1):
                    if intersections[i][1]:
                        count += 1
                    else:
                        count -= 1
                    if count != 0:
                        thisLine.append((complex(intersections[i][0], y),complex(intersections[i+1][0], y)))
            else:
                raise ValueError()
                   
            if odd:
                lines += reversed([(l[1],l[0]) for l in thisLine])
            else:
                lines += thisLine
            
            odd = not odd
                
            y += spacing
                       
        return [(line[0]*rotate, line[1]*rotate) for line in lines]
    
                    
if __name__ == '__main__':
    polygon=(0+0j, 10+10j, 10+0j, 0+0j)
    print(shadePolygon(polygon,90,1))
                    