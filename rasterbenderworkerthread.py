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
import osgeo, osgeo.gdalnumeric
import os.path, shutil
import sys
import math
import numpy
import subprocess

# Other classes
import triangulate


class RasterBenderWorkerThread(QThread):

    finished = pyqtSignal()
    error = pyqtSignal(str)
    progress = pyqtSignal(str, float) #message, progress percentage

    def __init__(self, pairsLayer, pairsLimitToSelection, constraintsLayer, constraintsLimitToSelection, bufferValue, samplingMethod, sourcePath, targetPath):
        QThread.__init__(self)

        self.pairsLayer = pairsLayer
        self.pairsLimitToSelection = pairsLimitToSelection
        self.constraintsLayer = constraintsLayer
        self.constraintsLimitToSelection = constraintsLimitToSelection
        self.bufferValue = bufferValue
        self.samplingMethod = samplingMethod

        self.sourcePath = sourcePath
        self.targetPath = targetPath

        self._abort = False



    def abort(self):
        self._abort = True
    
    def run(self):

        self._abort = False

        self.progress.emit("Starting RasterBender", float(0))

        #####################################
        # Step 1 : create the delaunay mesh #
        #####################################

        self.progress.emit( "Loading delaunay mesh...", float(0) )

        # Create the delaunay triangulation
        triangles, pointsA, pointsB, hull, constraints = triangulate.triangulate( self.pairsLayer, self.pairsLimitToSelection, self.constraintsLayer, self.constraintsLimitToSelection, self.bufferValue )


        ###############################
        # Step 2. Opening the dataset #
        ###############################

        self.progress.emit( "Opening the dataset... This shouldn't be too long...", float(0) )

        #Open the dataset
        osgeo.gdal.UseExceptions()

        # Read the source data into numpy arrays
        dsSource = osgeo.gdal.Open( self.sourcePath, osgeo.gdal.GA_ReadOnly )

        # Get the transformation
        pixW = float(dsSource.RasterXSize-1) #width in pixel
        pixH = float(dsSource.RasterYSize-1) #width in pixel
        rezX = dsSource.GetGeoTransform()[1] #horizontal resolution
        rezY = dsSource.GetGeoTransform()[5] #vertical resolution
        mapW = float(dsSource.RasterXSize)*rezX #width in map units
        mapH = float(dsSource.RasterYSize)*rezY #width in map units
        offX = dsSource.GetGeoTransform()[0] #offset in map units
        offY = dsSource.GetGeoTransform()[3] #offset in map units

        dsSource = None # close the source

        # We copy the origin to the destination raster
        # Every succequent drawing will happen on this raster, so that areas that don't move are already ok.

        shutil.copyfile(self.sourcePath, self.targetPath)



        def qgsPointToXY(qgspoint):
            """
            Returns a point in pixels coordinates given a point in map coordinates
            """
            return ( (qgspoint.x() - offX) / mapW * pixW + 1.0 , (qgspoint.y() - offY) / mapH * pixH + 1.0 )

        # We loop through every triangle to create a GDAL affine transformation
        count = len(triangles)
        for i,triangle in enumerate(triangles):

            if self._abort:
                self.error.emit( "Aborted on triangle %i out of %i..."  % (i, count))
                return

            self.progress.emit( "Computing triangle %i out of %i..." % (i, count), float(i)/float(count) )

            # aX are the pixels points of the initial triangles
            a0 = qgsPointToXY(pointsA[triangle[0]])
            a1 = qgsPointToXY(pointsA[triangle[1]])
            a2 = qgsPointToXY(pointsA[triangle[2]])
            # bx are the map points of the destination triangle
            b0 = pointsB[triangle[0]]
            b1 = pointsB[triangle[1]]
            b2 = pointsB[triangle[2]]

            

            # Step 1 : we do an affine transformation by providing 3 -gcp points

            # here we compute the parameters for srcwin, so that we don't compute the transformation on the whole raster
            # we have a 2 pixels margins, hence the +/- 2 and the enclosing max/min (to avoid overbound)
            xoff = max(    min(a0[0],a1[0],a2[0])-2    ,0)
            yoff = max(    min(a0[1],a1[1],a2[1])-2    ,0)
            xsize = min(    max(a0[0],a1[0],a2[0])+2-xoff    ,pixW-xoff)
            ysize = min(    max(a0[1],a1[1],a2[1])+2-yoff    ,pixH-yoff)

            tempTranslated = QTemporaryFile()
            tempTranslated.open()


            args = ['gdal_translate',
                '-gcp', a0[0]-xoff,a0[1]-yoff,b0[0],b0[1],
                '-gcp', a1[0]-xoff,a1[1]-yoff,b1[0],b1[1],
                '-gcp', a2[0]-xoff,a2[1]-yoff,b2[0],b2[1], 
                '-srcwin', xoff, yoff, xsize, ysize, 
                self.sourcePath,
                tempTranslated.fileName(),
            ]

            try:
                subprocess.check_output([str(a) for a in args], shell=True)
            except subprocess.CalledProcessError as e:
                self.error.emit( "Error on triangle %i out of %i : \"%s\" (%s)"  % (i, count, e.output, e.cmd))
                return



            # Step 2 : we draw the transformed layer on the target layer by providing a cutline (corresponding to the destination triangle)

            # We create a vector polygon to feed into GDAL's -cutline argument
            clip = QgsGeometry.fromPolygon([[b0,b1,b2,b0]]).buffer(.5*abs(rezX)+.5*abs(rezY),2)

            # Since it must be a GDAL format, we have to create a .csv file (hah, command line tools...)
            tempWKT = QTemporaryFile( os.path.join(QDir.tempPath(),'XXXXXX.csv') )
            tempWKT.open()
            content = 'WKT\tID\n"%s"\t1' % (clip.exportToWkt())
            tempWKT.write(content)
            tempWKT.close()
            

            args = [ 'gdalwarp',
                '-cutline', tempWKT.fileName(),
                '-cblend', '1', 
                '-dstnodata', '-999',
                '-r', self.samplingMethod,
                tempTranslated.fileName(),
                self.targetPath,
            ]

            try:
                subprocess.check_output([str(a) for a in args], shell=True)
            except subprocess.CalledProcessError as e:
                self.error.emit( "Error on triangle %i out of %i : \"%s\" (%s)"  % (i, count, e.output, e.cmd))
                return


            tempWKT.close()
            tempTranslated.close()


        self.finished.emit()
        return


