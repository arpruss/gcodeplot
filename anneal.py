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
    return .006 ** u
    
def neighborSwapping(lines, T):
    n = len(lines)
    n1,n2,n3,n4 = sorted(random.sample(xrange(n+1), 4))
    # swap [n1:n2] for [n3:n4]
    return lines[:n1] + lines[n3:n4] + lines[n2:n3] + lines[n1:n2] + lines[n4:]
    
def neighborReversing(lines, T):
    newLines = [line.copy() for line in lines]
    n = len(lines)
    
    i = random.randint(0,n-1)
    j = random.randint(0,n-2)
    if j >= i:
        j += 1
    
    i,j = min(i,j),max(i,j)
    
    while i<j:
        newLines[i].reverse()
        newLines[j].reverse()
        newLines[i],newLines[j] = newLines[j],newLines[i]
        i += 1
        j -= 1
    
    return newLines
    
def neighbor(lines, T):
    return neighborSwapping(lines,T) if random.random()<0.25*T else neighborReversing(lines,T)
    
def optimize(lines, k, maxSteps, neighbor=neighborReversing, temperature=linearTemperature):
    E = energy(lines)
    E0 = E
    
    print "original", E

    bestE = E
    bestLines = lines
    
    for step in range(maxSteps):
        T = temperature(step/float(maxSteps))
        newLines = neighbor(lines,T)
        newE = energy(newLines)
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
#        if step > maxSteps / 2:
#            break
            
    print "final", E
    print "best", bestE
            
    return bestLines
    
if __name__ == '__main__':
    lines = []
    random.seed(1)
    
    n = 100
    
    for i in range(n):
        lines.append(DrawingSegment([(random.random(),random.random()),(random.random(),random.random())]))

    steps = 100*n #int(20*n*math.log(n))
    print steps
    optimize(lines, 0.001, steps, neighbor=neighbor, temperature=exponentialTemperature)
