import random
import math
import time
import sys

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
    
def optimize(lines, maxSteps=None, k=0.0001, temperature=exponentialTemperature, timeout=30, retries=2, quiet=False):
    t00 = time.time()

    if not quiet: 
        sys.stderr.write("Optimizing...")
        sys.stderr.flush()
        lastMessagePercent = -100

    N = len(lines)

    if maxSteps == None:
        maxSteps = 250*N
        
    reversals = [False for i in range(N)]

    E = energy(lines, reversals)
    E0 = E
    
    if E == 0:
        return lines
    
    def P(deltaE,T):
        try:
            return math.exp(-deltaE/(E0*k*T))
        except:
            return 1 # overflow
    
    bestE = E
    bestLines = lines
    bestReversals = reversals

    tryCount = 0
    
    while tryCount < retries:
        t0 = time.time()
        step = 0
        while step < maxSteps:
            T = temperature(step/float(maxSteps))
            
            i = random.randint(0,N-1)
            j = random.randint(i,N-1)
            # useless if i==j, but that occurs rarely enough that it's not worth optimizing for

            oldE = measure(lines,reversals,j) + measure(lines,reversals,i-1)

            lines[i],lines[j]=lines[j],lines[i]
            reversals[i],reversals[j]=not reversals[j],not reversals[i]
            
            deltaE = measure(lines,reversals,j) + measure(lines,reversals,i-1) - oldE

            if P(deltaE, T) >= random.random():
                i += 1
                j -= 1
                
                while i<j:
                    lines[i],lines[j]=lines[j],lines[i]
                    reversals[i],reversals[j]=not reversals[j],not reversals[i]                    
                    i+=1
                    j-=1
                    
                if i == j:
                    reversals[i] = not reversals[i]

                E += deltaE
                if E < bestE:
                    bestE = E
                    bestLines = lines[:]
                    bestReversals = reversals[:]
            else:
                lines[i],lines[j]=lines[j],lines[i]
                reversals[i],reversals[j]=not reversals[j],not reversals[i]
            
            if step % 100 == 0:
                if not quiet:
                    percent = step * 100./maxSteps
                    if percent >= lastMessagePercent + 5:
                        sys.stderr.write("[%.0f%%]" % percent)
                        sys.stderr.flush()
                        lastMessagePercent = percent
                if time.time() > t0 + timeout:
                    sys.stderr.write("Timeout!\n")
                    sys.stderr.flush()
                    break
                    
            step += 1
            
        if step < maxSteps and tryCount + 1 < retries:
            maxSteps = int(.95 * step)
            E = bestE
            lines = bestLines
            reversals = bestReversals
            tryCount += 1
            if not quiet: 
                sys.stderr.write("Retrying.\n")
                sys.stderr.flush()
        else:
            break
    
    if not quiet:
        sys.stderr.write("\nTransport time improvement: %.1f%% (took %.2f seconds).\n" % ((E0-bestE)*100./E0, time.time()-t00))
        sys.stderr.flush()

    #print "final", E
    #print "best", bestE, energy(bestLines,bestReversals)
            
    return [list(reversed(bestLines[i])) if reversals[i] else bestLines[i] for i in range(N)]
    
if __name__ == '__main__':
    lines = []
    random.seed(1)
    
    n = 2000
    
    for i in range(n):
        lines.append([(random.random(),random.random()),(random.random(),random.random())])

    steps = 250*n #int(20*n*math.log(n))
    optimize(lines, maxSteps=steps, k=0.0001, temperature=exponentialTemperature, timeout=15, retries=2)
