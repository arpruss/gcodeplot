import svg.parser as parser
import getopt
import sys

try:
    opts, args = getopt.getopt(sys.argv[1:], "p:d:", ["--precision=", "--dpi=" ], )
    if len(args) != 1:
        raise getopt.GetoptError("invalid commandline")

    precision = 0.025
    dpi = 1016
        
    for opt,arg in opts:
        if opt in ('-p','--precision'):
            precision = float(arg)
    
except getopt.GetoptError:
    print("svg2gcode.py [options] inputfile [> output.gcode]")
    print("""
 -h|--help: this
 -p|--precision: precision in millimeters (default 0.025)
 -d|--dpi: output DPI (default: 1016)
""")

paths, corner1, corner2 = parser.getPathsFromSVG(args[0])

def hpglCoordinates(z):
    x = z.real * dpi / 25.4
    y = z.imag * dpi / 25.4
    return str(int(round(x)))+','+str(int(round(y)))

sys.stdout.write('IN')

for path in paths:
    for subpath in path.breakup():
        points = subpath.getApproximatePoints(error=precision)
        if len(points):
            sys.stdout.write(';PU'+hpglCoordinates(points[0]))
            if len(points) > 1:
                sys.stdout.write(';PD')
                for i in range(1,len(points)):
                    sys.stdout.write(hpglCoordinates(points[i]))
                    if i + 1 < len(points):
                        sys.stdout.write(',')
sys.stdout.write(';PU')                        
