#!/usr/bin/env python
# coding=utf-8
'''
Copyright (C) 2008 Aaron Spike, aaron@ekips.org
Copyright (C) 2013 Sebastian Wüst, sebi@timewaster.de
Copyright (C) 2016 Alexander Pruss

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
'''

# standard libraries
import math

class OffsetProcessor:
    def __init__(self, toolOffset=1., overcut=0.2, tolerance=0.01):
        self.toolOffset = toolOffset
        self.overcut = overcut
        self.tolerance = tolerance
        self.PI = math.pi
        self.TWO_PI = 2 * math.pi
        if self.toolOffset > 0.0:
            self.toolOffsetFlat = self.tolerance / self.toolOffset * 4.5 # scale flatness to offset
        else:
            self.toolOffsetFlat = 0.0

    @staticmethod
    def changeLength(x1, y1, x2, y2, offset):
        # change length of line
        d = OffsetProcessor.getLength(x1, y1, x2, y2)
        if offset < 0:
            offset = max( -d, offset)
        x = x2 + (x2 - x1) / d * offset
        y = y2 + (y2 - y1) / d * offset
        return [x, y]

    @staticmethod
    def getLength(ax,ay,bx,by):
        return math.sqrt((ax-bx)**2+(ay-by)**2)

    def processOffset(self, cmd, posX, posY):
        # calculate offset correction (or dont)
        if self.toolOffset == 0.0:
            self.storePoint(cmd, posX, posY)
        else:
            # insert data into cache
            self.vData.pop(0)
            self.vData.insert(3, [cmd, posX, posY])
            # decide if enough data is availabe
            if self.vData[2][1] != -1.0:
                if self.vData[1][1] == -1.0:
                    self.storePoint(self.vData[2][0], self.vData[2][1], self.vData[2][2])
                else:
                    # perform tool offset correction (It's a *tad* complicated, if you want to understand it draw the data as lines on paper)
                    if self.vData[2][0] == 'PD': # If the 3rd entry in the cache is a pen down command make the line longer by the tool offset
                        pointThree = OffsetProcessor.changeLength(self.vData[1][1], self.vData[1][2], self.vData[2][1], self.vData[2][2], self.toolOffset)
                        self.storePoint('PD', pointThree[0], pointThree[1])
                    elif self.vData[0][1] != -1.0:
                        # Elif the 1st entry in the cache is filled with data and the 3rd entry is a pen up command shift
                        # the 3rd entry by the current tool offset position according to the 2nd command
                        pointThree = OffsetProcessor.changeLength(self.vData[0][1], self.vData[0][2], self.vData[1][1], self.vData[1][2], self.toolOffset)
                        pointThree[0] = self.vData[2][1] - (self.vData[1][1] - pointThree[0])
                        pointThree[1] = self.vData[2][2] - (self.vData[1][2] - pointThree[1])
                        self.storePoint('PU', pointThree[0], pointThree[1])
                    else:
                        # Else just write the 3rd entry
                        pointThree = [self.vData[2][1], self.vData[2][2]]
                        self.storePoint('PU', pointThree[0], pointThree[1])
                    if self.vData[3][0] == 'PD':
                        # If the 4th entry in the cache is a pen down command guide tool to next line with a circle between the prolonged 3rd and 4th entry
                        if OffsetProcessor.getLength(self.vData[2][1], self.vData[2][2], self.vData[3][1], self.vData[3][2]) >= self.toolOffset:
                            pointFour = OffsetProcessor.changeLength(self.vData[3][1], self.vData[3][2], self.vData[2][1], self.vData[2][2], - self.toolOffset)
                        else:
                            pointFour = OffsetProcessor.changeLength(self.vData[2][1], self.vData[2][2], self.vData[3][1], self.vData[3][2],
                                (self.toolOffset - OffsetProcessor.getLength(self.vData[2][1], self.vData[2][2], self.vData[3][1], self.vData[3][2])))
                        # get angle start and angle vector
                        angleStart = math.atan2(pointThree[1] - self.vData[2][2], pointThree[0] - self.vData[2][1])
                        angleVector = math.atan2(pointFour[1] - self.vData[2][2], pointFour[0] - self.vData[2][1]) - angleStart
                        # switch direction when arc is bigger than 180°
                        if angleVector > self.PI:
                            angleVector -= self.TWO_PI
                        elif angleVector < - self.PI:
                            angleVector += self.TWO_PI
                        # draw arc
                        if angleVector >= 0:
                            angle = angleStart + self.toolOffsetFlat
                            while angle < angleStart + angleVector:
                                self.storePoint('PD', self.vData[2][1] + math.cos(angle) * self.toolOffset, self.vData[2][2] + math.sin(angle) * self.toolOffset)
                                angle += self.toolOffsetFlat
                        else:
                            angle = angleStart - self.toolOffsetFlat
                            while angle > angleStart + angleVector:
                                self.storePoint('PD', self.vData[2][1] + math.cos(angle) * self.toolOffset, self.vData[2][2] + math.sin(angle) * self.toolOffset)
                                angle -= self.toolOffsetFlat
                        self.storePoint('PD', pointFour[0], pointFour[1])

    def storePoint(self, command, x, y):
        # skip when no change in movement
        if self.lastPoint[0] == command and self.lastPoint[1] == x and self.lastPoint[2] == y:
            return
        if command == 'PD':
            self.curPath.append((x,y))
        elif command == 'PU':
            if len(self.curPath) > 1:
                self.paths.append(self.curPath)
            self.curPath = []
            self.curPath.append((x,y))
        self.lastPoint = [command, x, y]

    def processPath(self, path):
        self.vData = [['', -1.0, -1.0], ['', -1.0, -1.0], ['', -1.0, -1.0], ['', -1.0, -1.0]]
        self.paths = []
        self.curPath = []
        self.lastPoint = [0, 0, 0]
        
        self.processOffset('PU', 0, 0)

        oldPosX = float("inf")
        oldPosY = float("inf")
        for singlePath in path:
            cmd = 'PU'
            for singlePathPoint in singlePath:
                posX, posY = singlePathPoint
                # check if point is repeating, if so, ignore
                if OffsetProcessor.getLength(oldPosX,oldPosY,posX,posY) >= self.tolerance:
                    self.processOffset(cmd, posX, posY)
                    cmd = 'PD'
                    oldPosX = posX
                    oldPosY = posY
            # perform overcut
            if self.overcut > 0.0:
                # check if last and first points are the same, otherwise the path is not closed and no overcut can be performed
                if OffsetProcessor.getLength(oldPosX,oldPosY,singlePath[0][0],singlePath[0][1]) <= self.tolerance:
                    overcutLength = 0
                    for singlePathPoint in singlePath:
                        posX, posY = singlePathPoint
                        # check if point is repeating, if so, ignore
                        distance = OffsetProcessor.getLength(oldPosX,oldPosY, posX,posY)
                        if distance >= self.tolerance:
                            overcutLength += distance
                            if overcutLength >= self.overcut:
                                newLength = OffsetProcessor.changeLength(oldPosX, oldPosY, posX, posY, - (overcutLength - self.overcut))
                                self.processOffset(cmd, newLength[0], newLength[1])
                                break
                            else:
                                self.processOffset(cmd, posX, posY)
                            oldPosX = posX
                            oldPosY = posY
    
        self.processOffset('PU', 0, 0)
        if len(self.curPath) > 1:
            self.paths.append(self.curPath)
        return self.paths

if __name__ == '__main__':
    paths = [[(0,0),(20,0),(20,20),(0,20),(0,0)], [(0,0),(20,0),(20,20),(0,20),(0,0)]]
    op = OffsetProcessor()
    print(op.processPath(paths))