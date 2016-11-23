import random
import math

class DrawingSegment(object):
    def __init__(self, points):
        self.reversed = False
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
        return points if not self.reversed else reversed(points)

def distance(z1,z2):
    return math.sqrt((z1[0]-z2[0])**2 + (z1[1]-z2[1])**2)
        
def energy(lines):
    return sum(abs(lines[i].end() - lines[i+1].start() for i in range(len(lines)-1))
    
def temperature(step):
    return 10 - 0.5 * step
    
def neighbor(lines): # steps: lines*(lines-1)
    newLines = [line.copy() for line in lines]
    n = len(lines)
    r = random.randit(0,n+n*(n-1))
    if r < n:
        newLines[r].reverse()
        return newLines
    r -= n
    first = floor(r / (n-1))
    second = floor(r % (n-1))
    if second >= first:
        second += 1
    newLines[first],newLines[second] = newLines[second],newLines[first]
    return newLines

def optimize(lines, k, maxSteps):
    E = energy(lines)
    
    for step in range(maxSteps):
        newLines = neighbor(lines)
        newE = newLines
        if newE < E or math.exp(-(newE-E)/(k*temperature(step))) >= random.random():
            lines = newLines
            E = newE
            
    return lines
