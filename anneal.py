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

    def reversedCopy(self):
        return DrawingSegment(self.points, reversed=not self.reversed)        

def distance(z1,z2):
    return math.hypot(z1[0]-z2[0], z1[1]-z2[1])
        
def energy(lines):
    return sum(distance(lines[i].end(), lines[i+1].start()) for i in range(len(lines)-1))
    
def linearTemperature(u):
    return 1 - u
    
def exponentialTemperature(u):
    return .006 ** u
    
def neighborSwapping(lines, T, E):
    n = len(lines)
    n1,n2,n3,n4 = sorted(random.sample(xrange(n+1), 4))
    # swap [n1:n2] for [n3:n4]
    newLines = lines[:n1] + lines[n3:n4] + lines[n2:n3] + lines[n1:n2] + lines[n4:]
    return newLines, energy(newLines)
    
def neighborReversing(lines, T, E):
    n = len(lines)
    
    i = random.randint(0,n-2)
    if i == 0:
        j = random.randint(1,n-2)
    else:
        j = random.randint(i+1,n-1)

    newLines = lines[:i]
    
    for ii in range(i,j+1):
        newLines.append(lines[j+i-ii].reversedCopy())
    
    newLines += lines[j+1:]    

    if j < n-1:
        deltaE = distance(newLines[j].end(),newLines[j+1].start()) - distance(lines[j].end(),lines[j+1].start())
    else:
        deltaE = 0
    if 0 < i:
        deltaE += distance(newLines[i-1].end(),newLines[i].start()) - distance(lines[i-1].end(),lines[i].start())

    return newLines, E+deltaE # energy(newLines)
    
def neighbor(lines, T, E):
    return neighborSwapping(lines,T,E) if random.random()<0 else neighborReversing(lines,T,E)
    
def optimize(lines, k, maxSteps, neighbor=neighborReversing, temperature=linearTemperature):
    E = energy(lines)
    E0 = E
    
    print "original", E

    bestE = E
    bestLines = lines
    
    for step in range(maxSteps):
        T = temperature(step/float(maxSteps))
        newLines,newE = neighbor(lines,T,E)
        try:
            if math.exp(-(newE-E)/(E0*k*T)) >= random.random():
                lines = newLines
                E = newE
                if E < bestE:
                    bestE = E
                    bestLines = lines
        except:
            # overflow
            break
            
    print "final", E
    print "best", bestE
            
    return bestLines
    
if __name__ == '__main__':
    lines = []
    random.seed(1)
    
    n = 1000
    
    for i in range(n):
        lines.append(DrawingSegment([(random.random(),random.random()),(random.random(),random.random())]))

    steps = 100*n #int(20*n*math.log(n))
    print steps
    optimize(lines, 0.001, steps, neighbor=neighborReversing, temperature=exponentialTemperature)
