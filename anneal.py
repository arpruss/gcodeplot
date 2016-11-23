import random
import math

def distance(z1,z2):
    return math.hypot(z1[0]-z2[0], z1[1]-z2[1])
    
def measure(lines, reversals, index):
    z1 = lines[index][0] if reversals[index] else lines[index][-1]
    z2 = lines[index+1][-1] if reversals[index+1] else lines[index+1][0]
    return distance(z1,z2)
        
def energy(lines, reversals):
    return sum(measure(lines, reversals, i) for i in range(len(lines)-1))
    
def linearTemperature(u):
    return 1 - u
    
def exponentialTemperature(u):
    return .006 ** u
    
def neighborReversing(lines, reversals, T, E):
    n = len(lines)
    
    i = random.randint(0,n-2)
    if i == 0:
        j = random.randint(1,n-2)
    else:
        j = random.randint(i+1,n-1)

    newLines = lines[:i]
    newReversals = reversals[:i]
    
    for ii in range(i,j+1):
        newLines.append(lines[j+i-ii])
        newReversals.append(not reversals[j+i-ii])
    
    newLines += lines[j+1:]    
    newReversals += reversals[j+1:]

    if j < n-1:
        deltaE = measure(newLines, newReversals, j) - measure(lines, reversals, j)
    else:
        deltaE = 0
    if 0 < i:
        deltaE += measure(newLines, newReversals, i-1) - measure(lines, reversals, i-1)

    return newLines, newReversals, E+deltaE # energy(newLines)
    
def optimize(lines, reversals, k, maxSteps, neighbor=neighborReversing, temperature=linearTemperature):
    E = energy(lines, reversals)
    E0 = E
    
    print "original", E

    bestE = E
    bestLines = lines
    bestReversals = reversals
    
    for step in range(maxSteps):
        T = temperature(step/float(maxSteps))
        newLines,newReversals,newE = neighbor(lines,reversals,T,E)
        try:
            if math.exp(-(newE-E)/(E0*k*T)) >= random.random():
                lines = newLines
                reversals = newReversals
                E = newE
                if E < bestE:
                    bestE = E
                    bestLines = lines
                    bestReversals = reversals
        except:
            # overflow
            break
            
    print "final", E
    print "best", bestE
            
    return bestLines,bestReversals
    
if __name__ == '__main__':
    lines = []
    reversals = []
    random.seed(1)
    
    n = 1000
    
    for i in range(n):
        lines.append([(random.random(),random.random()),(random.random(),random.random())])
        reversals.append(False)

    steps = 100*n #int(20*n*math.log(n))
    print steps
    optimize(lines, reversals, 0.001, steps, neighbor=neighborReversing, temperature=exponentialTemperature)
