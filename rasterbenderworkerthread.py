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
import triangulate # it seems we can't import fTools' voronoi directly, so we ship a copy of the file
import algorithm_trifinder as trifinder
import algorithm_trimapper as trimapper


class RasterBenderWorkerThread(QThread):

    finished = pyqtSignal()
    error = pyqtSignal(str)
    progress = pyqtSignal(str, float, float) #message, pixel progress, block progress

    def __init__(self, pairsLayer, pairsLimitToSelection, constraintsLayer, constraintsLimitToSelection, bufferValue, blockSize, sourcePath, targetPath):
        QThread.__init__(self)

        self.pairsLayer = pairsLayer
        self.pairsLimitToSelection = pairsLimitToSelection
        self.constraintsLayer = constraintsLayer
        self.constraintsLimitToSelection = constraintsLimitToSelection
        self.bufferValue = bufferValue
        self.blockSize = blockSize

        self.sourcePath = sourcePath
        self.targetPath = targetPath

        self._abort = False



    def abort(self):
        self._abort = True
    
    def run(self):

        self._abort = False

        self.progress.emit("Starting RasterBender", float(0), float(0))

        #####################################
        # Step 1 : create the delaunay mesh #
        #####################################

        self.progress.emit( "Loading delaunay mesh...", float(0), float(0) )

        # Create the delaunay triangulation
        triangles, pointsA, pointsB, hull, constraints = triangulate.triangulate( self.pairsLayer, self.pairsLimitToSelection, self.constraintsLayer, self.constraintsLimitToSelection, self.bufferValue )


        ###############################
        # Step 2. Opening the dataset #
        ###############################

        self.progress.emit( "Opening the dataset... This shouldn't be too long...", float(0), float(0) )

        #Open the dataset
        gdal.UseExceptions()

        # Read the source data into numpy arrays
        dsSource = gdal.Open( self.sourcePath, gdal.GA_ReadOnly )

        sourceDataR = gdalnumeric.BandReadAsArray(dsSource.GetRasterBand(1))
        sourceDataG = gdalnumeric.BandReadAsArray(dsSource.GetRasterBand(2))
        sourceDataB = gdalnumeric.BandReadAsArray(dsSource.GetRasterBand(3))

        # Get the transformation
        pixW = float(dsSource.RasterXSize-1) #width in pixel
        pixH = float(dsSource.RasterYSize-1) #width in pixel
        mapW = float(dsSource.RasterXSize)*dsSource.GetGeoTransform()[1] #width in map units
        mapH = float(dsSource.RasterYSize)*dsSource.GetGeoTransform()[5] #width in map units
        offX = dsSource.GetGeoTransform()[0] #offset in map units
        offY = dsSource.GetGeoTransform()[3] #offset in map units

        # Open the target into numpy array
        #dsTarget = gdal.Open(self.targetPath, gdal.GA_Update )
        driver = gdal.GetDriverByName( "GTiff" )
        dsTarget = driver.CreateCopy( self.targetPath, dsSource, 0 )
        #dsTarget.SetGeoTransform( dsSource.GetGeoTransform() )
        dsTarget = None #close



        def xyToQgsPoint(x, y):
            return QgsPoint( offX + mapW * (x/pixW), offY + mapH * (y/pixH) )
        def qgsPointToXY(qgspoint):
            return ( int((qgspoint.x() - offX) / mapW * pixW ) , int((qgspoint.y() - offY) / mapH * pixH ) )


        #######################################
        # Step 3A. Looping through the blocks #
        #######################################

        #Loop through every block
        blockCountX = dsSource.RasterXSize//self.blockSize+1
        blockCountY = dsSource.RasterYSize//self.blockSize+1
        blockCount = blockCountX*blockCountY
        blockI = 0

        displayTotal = dsSource.RasterXSize*dsSource.RasterYSize
        displayStep = min((self.blockSize**2)/20,10000) # update gui every n steps

        self.progress.emit( "Starting computation... This can take a while..." , float(0), float(0))        

        for blockNumY in range(0, blockCountY ):
            blockOffsetY = blockNumY*self.blockSize
            blockH = min( self.blockSize, dsSource.RasterYSize-blockOffsetY )
            if blockH <= 0: continue

            for blockNumX in range(0, blockCountX ):
                blockOffsetX = blockNumX*self.blockSize
                blockW = min( self.blockSize, dsSource.RasterXSize-blockOffsetX )
                if blockW <= 0: continue

                blockI += 1
                pixelCount = blockW*blockH
                pixelI = 0

                blockRectangle = QgsRectangle(  xyToQgsPoint(blockOffsetX, blockOffsetY), 
                                                xyToQgsPoint(blockOffsetX+blockW, blockOffsetY+blockH) ) # this is the shape of the block, used for optimization

                # We check if the block intersects the hull, if not, we skip it
                if not hull.intersects( blockRectangle ):
                    self.progress.emit( "Block %i out of %i is out of the convex hull, we skip it..."  % (blockI, blockCount), float(0), float(blockI/float(blockCount) ) )
                    continue

                # We create the trifinder for the block
                blockTrifinder = trifinder.Trifinder( pointsB, triangles, blockRectangle )

                targetDataR = gdalnumeric.BandReadAsArray(dsSource.GetRasterBand(1),blockOffsetX,blockOffsetY,blockW,blockH)
                targetDataG = gdalnumeric.BandReadAsArray(dsSource.GetRasterBand(2),blockOffsetX,blockOffsetY,blockW,blockH)
                targetDataB = gdalnumeric.BandReadAsArray(dsSource.GetRasterBand(3),blockOffsetX,blockOffsetY,blockW,blockH)


                #######################################
                # Step 3B. Looping through the pixels #
                #######################################

                # Loop through every pixel
                for y in range(0, blockH):
                    for x in range(0, blockW):
                        # If abort was called, we finish the process
                        if self._abort:
                            self.error.emit( "Aborted on pixel %i out of %i on block %i out of %i..."  % (pixelI, pixelCount, blockI, blockCount ), float(0), float(0))
                            return

                        pixelI+=1

                        # Ever now and then, we update the status
                        if pixelI%displayStep == 0:
                            self.progress.emit("Working on pixel %i out of %i on block %i out of %i... Trifinder has %i triangles"  % (pixelI, pixelCount, blockI, blockCount,len(blockTrifinder.triangles) ), float(pixelI)/float(pixelCount),float(blockI)/float(blockCount) )
                            
                        # We find in which triangle the point lies using the trifinder.
                        p = xyToQgsPoint(blockOffsetX+x, blockOffsetY+y)
                        tri = blockTrifinder.find( p )
                        if tri is None:
                            # If it's in no triangle, we don't change it
                            continue

                        # If it's in a triangle, we transform the coordinates
                        newP = trimapper.map(  p, 
                                                                            pointsB[tri[0]], pointsB[tri[1]], pointsB[tri[2]],
                                                                            pointsA[tri[0]], pointsA[tri[1]], pointsA[tri[2]] )

                    

                        newX, newY = qgsPointToXY(  newP  )

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

                # Write to the image

                dsTarget = gdal.Open(self.targetPath, gdal.GA_Update )

                gdalnumeric.BandWriteArray(dsTarget.GetRasterBand(1), targetDataR, blockOffsetX, blockOffsetY)  
                gdalnumeric.BandWriteArray(dsTarget.GetRasterBand(2), targetDataG, blockOffsetX, blockOffsetY)  
                gdalnumeric.BandWriteArray(dsTarget.GetRasterBand(3), targetDataB, blockOffsetX, blockOffsetY)

                dsTarget = None


        self.finished.emit()
        return


