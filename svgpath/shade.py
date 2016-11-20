import math
from operator import itemgetter

def shadePolygon(polygon, theta, spacing, evenOdd=True):
    rotate = complex(math.cos(theta), math.sin(theta))
    
    rotated = [z / rotate for z in polygon]
    
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
        
    minY = min(z.real for z in polygon)
    maxY = max(z.real for z in polygon)

    lines = []
    
    y = minY + ( - minY ) % spacing + deltaY    
    
    while y < maxY:
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
        
        if evenOdd:
            for i in range(0,len(intersections)-1,2):
                lines.append((complex(intersections[i][0], y),complex(intersections[i+1][0], y)))
        else:
            count = 0
            for i in range(0,len(intersections)-1):
                if intersections[i][1]:
                    count += 1
                else:
                    count -= 1
                if count != 0:
                    lines.append((complex(intersections[i][0], y),complex(intersections[i+1][0], y)))
                    
        y += spacing
                   
    return [(line[0]*rotate, line[1]*rotate) for line in lines]
                    
if __name__ == '__main__':
    polygon=(0+0j, 10+10j, 10+0j, 0+0j)
    print(shadePolygon(polygon,0,1))
                    