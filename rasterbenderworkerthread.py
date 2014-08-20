# -*- coding: utf-8 -*-
"""
/***************************************************************************
 RasterBender
                                 A QGIS plugin
 Deforms vector to adapt them despite heavy and irregular deformations
                              -------------------
        begin                : 2014-05-21
        copyright            : (C) 2014 by Olivier Dalang
        email                : olivier.dalang@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

# Import the PyQt and QGIS libraries
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *

# Basic dependencies
from osgeo import gdal  
from osgeo import gdalnumeric
import os.path, shutil
import sys
import math
import numpy

# Other classes
from rasterbendertransformers import *


class RasterBenderWorkerThread(QThread):

    finished = pyqtSignal()
    error = pyqtSignal(str)
    progress = pyqtSignal(str, float, float) #message, pixel progress, block progress

    def __init__(self, pairsLayer, limitToSelection, bufferValue, sourcePath, targetPath):
        QThread.__init__(self)

        self.pairsLayer = pairsLayer
        self.limitToSelection = limitToSelection
        self.bufferValue = bufferValue
        self.sourcePath = sourcePath
        self.targetPath = targetPath

        self._abort = False

        self.transformer = None



    def abort(self):
        self._abort = True
    
    def run(self):

        self._abort = False

        self.progress.emit("Starting RasterBender", 0.0, 0.0)

        self.progress.emit( "Loading delaunay mesh...", 0.0, 0.0 )            
        self.transformer = BendTransformer( self.pairsLayer, self.limitToSelection, self.bufferValue )


        # Starting to through all target pixels

        #Open the dataset
        gdal.UseExceptions()

        # Read the source data into numpy arrays
        dsSource = gdal.Open( self.sourcePath, gdal.GA_ReadOnly )

        sourceDataR = gdalnumeric.BandReadAsArray(dsSource.GetRasterBand(1))
        sourceDataG = gdalnumeric.BandReadAsArray(dsSource.GetRasterBand(2))
        sourceDataB = gdalnumeric.BandReadAsArray(dsSource.GetRasterBand(3))

        # Open the target into numpy array
        shutil.copy( self.sourcePath, self.targetPath ) # if the target doesn't exist, we use the source target
            

        dsTarget = gdal.Open(self.targetPath, gdal.GA_Update )

        # Get the transformation
        pixW = float(dsTarget.RasterXSize-1) #width in pixel
        pixH = float(dsTarget.RasterYSize-1) #width in pixel
        mapW = float(dsTarget.RasterXSize)*dsTarget.GetGeoTransform()[1] #width in map units
        mapH = float(dsTarget.RasterYSize)*dsTarget.GetGeoTransform()[5] #width in map units
        offX = dsTarget.GetGeoTransform()[0] #offset in map units
        offY = dsTarget.GetGeoTransform()[3] #offset in map units



        def xyToQgsPoint(x, y):
            return QgsPoint( offX + mapW * (x/pixW), offY + mapH * (y/pixH) )
        def qgsPointToXY(qgspoint):
            return ( int((qgspoint.x() - offX) / mapW * pixW ) , int((qgspoint.y() - offY) / mapH * pixH ) )



        #Loop through every block
        blockSize = 1000
        blockCountX = dsTarget.RasterXSize//blockSize+1
        blockCountY = dsTarget.RasterYSize//blockSize+1
        blockCount = blockCountX*blockCountY
        blockI = 0

        displayTotal = dsTarget.RasterXSize*dsTarget.RasterYSize
        displayStep = min((blockSize**2)/10,5000) # update gui every n steps

        self.progress.emit( "Starting computation... %i points to compute !! This can take a while..."  % (displayTotal), 0.0, 0.0)        

        for blockNumY in range(0, blockCountX ):
            blockOffsetY = blockNumY*blockSize
            blockH = min( blockSize, dsTarget.RasterYSize-blockOffsetY )
            if blockH <= 0: continue

            for blockNumX in range(0, blockCountY ):
                blockOffsetX = blockNumX*blockSize
                blockW = min( blockSize, dsTarget.RasterXSize-blockOffsetX )
                if blockW <= 0: continue

                blockI += 1
                pixelCount = blockW*blockH
                pixelI = 0

                # We check if the block intersects the hull, if not, we skip it
                hull = self.transformer.expandedHull if self.transformer.expandedHull is not None else self.transformer.hull
                if not hull.intersects( QgsRectangle( xyToQgsPoint(blockOffsetX, blockOffsetY), xyToQgsPoint(blockOffsetX+blockW, blockOffsetY+blockH) ) ):
                    self.progress.emit( "Block %i out of %i is out of the convex hull, we skip it..."  % (blockI, blockCount ), 0.0, blockI/float(blockCount) )
                    continue

                # We get a list of triangles that intersect the block, since we don't want to search through all triangles if there's only few in the box

                targetDataR = numpy.ndarray( (blockH, blockW) )
                targetDataG = numpy.ndarray( (blockH, blockW) )
                targetDataB = numpy.ndarray( (blockH, blockW) )

                # Loop through every pixel
                for y in range(0, blockH):
                    for x in range(0, blockW):

                        if self._abort:
                            self.error.emit( "Aborted on pixel %i out of %i on block %i out of %i..."  % (pixelI, pixelCount, blockI, blockCount ))
                            return


                        pixelI+=1
                        if pixelI%displayStep == 0:
                            self.progress.emit("Working on pixel %i out of %i on block %i out of %i..."  % (pixelI, pixelCount, blockI, blockCount ), float(pixelI)/float(pixelCount),float(blockI)/float(blockCount) )
                            

                        newX, newY = qgsPointToXY(  self.transformer.map( xyToQgsPoint(blockOffsetX+x,blockOffsetY+y) )  )

                        # TODO : this would maybe get interpolated results
                        #ident = sourceRaster.dataProvider().identify( pt, QgsRaster.IdentifyFormatValue)
                        #targetDataR[y][x] = ident.results()[1]
                        #targetDataG[y][x] = ident.results()[2]
                        #targetDataB[y][x] = ident.results()[3]

                        try:
                            if newY<0 or newX<0: raise IndexError() #avoid looping
                            targetDataR[y][x] = sourceDataR[newY][newX]
                            targetDataG[y][x] = sourceDataG[newY][newX]
                            targetDataB[y][x] = sourceDataB[newY][newX]
                        except IndexError, e:
                            targetDataR[y][x] = 0
                            targetDataG[y][x] = 0
                            targetDataB[y][x] = 0


                gdalnumeric.BandWriteArray(dsTarget.GetRasterBand(1), targetDataR, blockOffsetX, blockOffsetY)  
                gdalnumeric.BandWriteArray(dsTarget.GetRasterBand(2), targetDataG, blockOffsetX, blockOffsetY)  
                gdalnumeric.BandWriteArray(dsTarget.GetRasterBand(3), targetDataB, blockOffsetX, blockOffsetY)

        self.finished.emit()
        return


