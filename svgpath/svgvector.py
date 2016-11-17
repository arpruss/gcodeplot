import xml.etree.ElementTree as ET

class SVGCommand(object):
    INIT = 0
    MOVE_PEN_UP = 1
    MOVE_PEN_DOWN = 2
    def __init__(self, command, point=None):
        self.command = command
        self.point = point
        
    def __repr__(self):
        return '('+str(self.command)+','+str(self.point)+')'
        

def parseSVG('country_data.xml'):
    