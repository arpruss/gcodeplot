import random
import math

def distance(z1,z2):
    return math.hypot(z1[0]-z2[0], z1[1]-z2[1])
    
def measure(lines, reversals, index):
    if index < 0 or index >= len(lines) - 1:
        return 0.
    z1 = lines[index][0] if reversals[index] else lines[index][-1]
    z2 = lines[index+1][-1] if reversals[index+1] else lines[index+1][0]
    return distance(z1,z2)
        
def energy(lines, reversals):
    return sum(measure(lines, reversals, i) for i in range(len(lines)-1))
    
def linearTemperature(u):
    return 1 - u
    
def exponentialTemperature(u):
    return .006 ** u
    
def optimize(lines, reversals, k, maxSteps, temperature=linearTemperature):
    E = energy(lines, reversals)
    E0 = E
    
    print "original", E

    bestE = E
    bestLines = lines
    bestReversals = reversals
    
    for step in range(maxSteps):
        T = temperature(step/float(maxSteps))
        
        i = random.randint(0,n-2)
        if i == 0:
            j = random.randint(1,n-2)
        else:
            j = random.randint(i+1,n-1)

        oldE = measure(lines,reversals,j) + measure(lines,reversals,i-1)
        lines[i],lines[j]=lines[j],lines[i]
        reversals[i],reversals[j]=not reversals[j],not reversals[i]
        
        deltaE = measure(lines,reversals,j) + measure(lines,reversals,i-1) - oldE

        lines[i],lines[j]=lines[j],lines[i]
        reversals[i],reversals[j]=not reversals[j],not reversals[i]
        
        try:
            if math.exp(-deltaE/(E0*k*T)) >= random.random():
                newLines = lines[:i]
                newReversals = reversals[:i]
                
                for ii in range(i,j+1):
                    newLines.append(lines[j+i-ii])
                    newReversals.append(not reversals[j+i-ii])
                
                newLines += lines[j+1:]    
                newReversals += reversals[j+1:]

                lines = newLines
                reversals = newReversals

                E += deltaE
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
    
    n = 10000
    
    for i in range(n):
        lines.append([(random.random(),random.random()),(random.random(),random.random())])
        reversals.append(False)

    steps = 100*n #int(20*n*math.log(n))
    print steps
    optimize(lines, reversals, 0.001, steps, temperature=exponentialTemperature)
