import random
import math

class DrawingSegment(object):
    def __init__(self, points, reversed=False):
        self.reversed = reversed
        self.points = points
        
    def reverse(self):
        self.reversed = not self.reversed
        
    def start(self):
        if self.reversed:
            return self.points[-1]
        else:
            return self.points[0]

    def end(self):
        if self.reversed:
            return self.points[0]
        else:
            return self.points[-1]
            
    def getPoints(self):
        return self.points if not self.reversed else reversed(self.points)
        
    def copy(self):
        return DrawingSegment(self.points, reversed=self.reversed)        

def distance(z1,z2):
    return math.sqrt((z1[0]-z2[0])**2 + (z1[1]-z2[1])**2)
        
def energy(lines):
    return sum(distance(lines[i].end(), lines[i+1].start()) for i in range(len(lines)-1))
    
def linearTemperature(u):
    return 1 - u
    
def exponentialTemperature(u):
    return (math.exp(-u*3) - math.exp(-3))/(1-math.exp(-3))
    
def neighborConsecutive(lines, T):
    newLines = [line.copy() for line in lines]
    n = len(lines)
    if random.randint(0,10) == 0:
        newLines[random.randint(0,n-1)].reverse()
        return newLines
    first = random.randint(0,n-1)
    second = (first + random.randint(1,n/4)) % n
    newLines[first],newLines[second] = newLines[second],newLines[first]
    return newLines
    
def neighborSpread(lines, T): # steps: lines*(lines-1)
    newLines = [line.copy() for line in lines]
    n = len(lines)
    r = random.randint(0,10*n+n*(n-1)-1)
    if r < 10*n:
        newLines[r % n].reverse()
        return newLines
    r -= 10*n
    first = int(math.floor(r / (n-1)))
    second = int(math.floor(r % (n-1)))
    if second >= first:
        second += 1
    newLines[first],newLines[second] = newLines[second],newLines[first]
    return newLines

def optimize(lines, k, maxSteps, neighbor=neighborSpread, temperature=linearTemperature):
    E = energy(lines)
    
    print "original", E

    bestE = E
    bestLines = lines
    
    for step in range(maxSteps):
        T = temperature(step/float(maxSteps))
        newLines = neighbor(lines,T)
        newE = energy(newLines)
        try:
            if math.exp(-(newE-E)/(k*T)) >= random.random():
                lines = newLines
                E = newE
                if E < bestE:
                    bestE = E
                    bestLines = lines
        except:
            # overflow
            break
#        if step > maxSteps / 2:
#            break
            
    print "final", E
    print "best", bestE
            
    return bestLines
    
if __name__ == '__main__':
    lines = []
    random.seed(1)
    
    n = 200
    
    for i in range(n):
        lines.append(DrawingSegment([(random.random(),random.random()),(random.random(),random.random())]))

    optimize(lines, 0.1, int(3*n*math.log(n)), neighbor=neighborSpread, temperature=linearTemperature)
    