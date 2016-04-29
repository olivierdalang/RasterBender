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
import triangulate # it seems we can't import fTools' voronoi directly, so we ship a copy of the file


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
        osgeo.gdal.UseExceptions()

        # Read the source data into numpy arrays
        dsSource = osgeo.gdal.Open( self.sourcePath, osgeo.gdal.GA_ReadOnly )

        sourceDataR = osgeo.gdalnumeric.BandReadAsArray(dsSource.GetRasterBand(1))
        sourceDataG = osgeo.gdalnumeric.BandReadAsArray(dsSource.GetRasterBand(2))
        sourceDataB = osgeo.gdalnumeric.BandReadAsArray(dsSource.GetRasterBand(3))

        # Get the transformation
        pixW = float(dsSource.RasterXSize-1) #width in pixel
        pixH = float(dsSource.RasterYSize-1) #width in pixel
        mapW = float(dsSource.RasterXSize)*dsSource.GetGeoTransform()[1] #width in map units
        mapH = float(dsSource.RasterYSize)*dsSource.GetGeoTransform()[5] #width in map units
        offX = dsSource.GetGeoTransform()[0] #offset in map units
        offY = dsSource.GetGeoTransform()[3] #offset in map units

        # We copy the origin to the destination raster
        shutil.copyfile(self.sourcePath, self.targetPath)



        def qgsPointToXY(qgspoint):
            return ( (qgspoint.x() - offX) / mapW * pixW , (qgspoint.y() - offY) / mapH * pixH )


        for triangle in triangles:

            a0 = qgsPointToXY(pointsA[triangle[0]])
            b0 = pointsB[triangle[0]]
            a1 = qgsPointToXY(pointsA[triangle[1]])
            b1 = pointsB[triangle[1]]
            a2 = qgsPointToXY(pointsA[triangle[2]])
            b2 = pointsB[triangle[2]]


            # tempWKT = QTemporaryFile()
            # tempWKT.open()
            tempWKT = open(self.targetPath+'_tempwkt.csv','w')
            content = 'WKT\tID\n"POLYGON((%s %s,%s %s,%s %s,%s %s))"\t1' % (b0[0],b0[1],b1[0],b1[1],b2[0],b2[1],b0[0],b0[1])
            tempWKT.write(content)
            tempWKT.close()


            tempTranslated = QTemporaryFile()
            tempTranslated.open()



            args = 'C:\\OSGeo4W\\bin\\gdal_translate -gcp %f %f %f %f -gcp %f %f %f %f -gcp %f %f %f %f %s %s' % (
                a0[0],a0[1],b0[0],b0[1],
                a1[0],a1[1],b1[0],b1[1],
                a2[0],a2[1],b2[0],b2[1], 
                self.sourcePath,
                tempTranslated.fileName(),
            )

            try:
                subprocess.check_output(args)
            except subprocess.CalledProcessError as e:
                QgsMessageLog.logMessage( str(e.cmd) )
                QgsMessageLog.logMessage( e.output )
                raise e

            
            # args = 'C:\\OSGeo4W\\bin\\gdalwarp -cutline %s -crop_to_cutline -overwrite -dstnodata "-999" %s %s' % (
            #     # tempWKT.fileName(),
            #     self.targetPath+'_tempwkt.csv',
            #     tempTranslated.fileName(),
            #     self.targetPath+'_tempcropped_'+str(i),
            # )

            args = 'C:\\OSGeo4W\\bin\\gdalwarp -cutline %s -dstnodata "-999" -r bilinear %s %s' % (
                # tempWKT.fileName(),
                self.targetPath+'_tempwkt.csv',
                tempTranslated.fileName(),
                self.targetPath,
            )

            try:
                subprocess.check_output(args)
            except subprocess.CalledProcessError as e:
                QgsMessageLog.logMessage( str(e.cmd) )
                QgsMessageLog.logMessage( e.output )
                raise e

            
            # args = 'python C:\\OSGeo4W\\bin\\gdal_merge.py %s %s' % (
            #     self.targetPath+'_tempcropped_'+str(i),
            #     self.targetPath,
            # )

            # try:
            #     subprocess.check_output(args)
            # except subprocess.CalledProcessError as e:
            #     QgsMessageLog.logMessage( str(e.cmd) )
            #     QgsMessageLog.logMessage( e.output )
            #     raise e



            # C:\OSGeo4W\bin\gdal_translate -gcp 52 203 239298 1630759 -gcp 74 168 239313 1630778 -gcp 84 208 239317 1630756 C:/Users/Olivier/Desktop/RasterBenderTests/ORIG.tif 
            # C:\OSGeo4W\bin\gdalwarp -cutlineC:/Users/Olivier/Desktop/RasterBenderTests/TEST.tif_clip.csv -crop_to_cutline  C:/Users/Olivier/Desktop/RasterBenderTests/TEST.tif

            tempWKT.close()
            tempTranslated.close()


        self.finished.emit()


