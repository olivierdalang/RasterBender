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
import traceback
import math
import numpy
import subprocess
import json

# Other classes
import triangulate


class RasterBenderWorkerThread(QThread):

    finished = pyqtSignal()
    error = pyqtSignal(str)
    progress = pyqtSignal(str, float) #message, progress percentage

    def __init__(self, pairsLayer, pairsLimitToSelection, constraintsLayer, constraintsLimitToSelection, bufferValue, samplingMethod, sourcePath, targetPath, debug):
        QThread.__init__(self)

        self.pairsLayer = pairsLayer
        self.pairsLimitToSelection = pairsLimitToSelection
        self.constraintsLayer = constraintsLayer
        self.constraintsLimitToSelection = constraintsLimitToSelection
        self.bufferValue = bufferValue
        self.samplingMethod = samplingMethod

        self.sourcePath = sourcePath
        self.targetPath = targetPath

        self.debug = debug

        self._abort = False


    def log(self,message, debug_only=False):
        if debug_only is False or self.debug is True:
            QgsMessageLog.logMessage(message,'RasterBender')
    def log_gdal(self,message):
        if self.debug is True:
            QgsMessageLog.logMessage(message,'RasterBender-gdal')


    def runCommand(self, args, operation_name = 'run the command'):
        str_args = [str(a) for a in args]
        try:
            self.log_gdal('# COMMAND   : '+operation_name)
            self.log_gdal(subprocess.list2cmdline(str_args))
            result = subprocess.check_output(str_args, shell=True, stderr=subprocess.STDOUT) 
            self.log_gdal('# OUTPUT    : '+operation_name)           
            self.log_gdal(result)
            return (True,result)
        except subprocess.CalledProcessError as e: 
            self.log_gdal('# ERROR     : '+operation_name)           
            self.log_gdal(e.output)
            self.error.emit( "Could not %s ! : \"%s\" [%s]"  % (operation_name, e.output, subprocess.list2cmdline(e.cmd)))
            return (False, e.output)
        except Exception as e:
            self.log_gdal('# EXCEPTION : '+operation_name)           
            self.log_gdal(str(e))
            self.error.emit( "Could not %s ! : \"%s\""  % (operation_name,str(e),))
            return (False, None)

    def abort(self):
        self._abort = True

    def run(self):
        try:
            self.doRun()
        except Exception as e:
            self.error.emit('An unexpected exception occured ! See QGIS log for details.')
            self.log(traceback.format_exc())
    
    def doRun(self):

        self._abort = False

        if self.debug:
            args = ['gdalinfo',
                '--version',
            ]
            sucess, result = self.runCommand(args, 'get GDAL version')


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
        rezY = dsSource.GetGeoTransform()[5] #vertical resolution # this should give -1 if the raster has no geotransform, but it does not...
        mapW = float(dsSource.RasterXSize)*rezX #width in map units
        mapH = float(dsSource.RasterYSize)*rezY #width in map units
        offX = dsSource.GetGeoTransform()[0] #offset in map units
        offY = dsSource.GetGeoTransform()[3] #offset in map units

        self.log('pixW:{} pixH:{} rezX:{} rezY:{} mapW:{} mapH:{} offX:{} offY:{}'.format(pixW,pixH,rezX,rezY,mapW,mapH,offX,offY), True )

        dsSource = None # close the source

        # We copy the origin to the destination raster
        # Every succequent drawing will happen on this raster, so that areas that don't move are already ok.

        # We get the informations of the source layer to use the same format for output
        args = ['gdalinfo',
                # '-json', # -json doesn't exist in GDAL<2.0
                self.sourcePath,
            ]

        sucess, result = self.runCommand(args, 'get the file infos')
        # output_format = json.loads(result)['driverShortName'] # -json doesn't exist in GDAL<2.0, so we use this:
        if not sucess: return
        output_format = None
        geotransform_found = False
        for line in result.split('\n'):
            if line[0:8]=='Driver: ':
                output_format = line[8:].split('/')[0]
            if line[0:13]=='Pixel Size = ':
                geotransform_found=True


        # And we create a copy
        args = ['gdal_translate', 
                self.sourcePath,
                self.targetPath,
            ]
        # If we has an input format, we set it using -of parameter
        if output_format:
            self.log('Output format was found : {}'.format(output_format), True)
            args.extend(['-of',output_format])
        else:
            self.log('Output format was not found.', True)
        if geotransform_found:
            self.log('Geotransform was found.', True)
        else:
            # If we have no geotransform, we use GCPs to match 1 pixel = 1 map unit.
            args.extend(['-gcp',0,0,0,0])
            args.extend(['-gcp',0,1,0,-1])
            args.extend(['-gcp',1,0,1,0])
            rezY = -rezY # hack, see above
            self.log('Geotransform was not found. We created GCPs', True)

        sucess, result = self.runCommand(args, 'copy the file')
        if not sucess: return


        def qgsPointToXY(qgspoint):
            """
            Returns a point in pixels coordinates given a point in map coordinates
            """
            return ( (qgspoint.x() - offX) / rezX + 1.0 , (qgspoint.y() - offY) / rezY + 1.0 )

        # We loop through every triangle to create a GDAL affine transformation
        count = len(triangles)
        for i,triangle in enumerate(triangles):

            if self._abort:
                self.error.emit( "Aborted on triangle %i out of %i..."  % (i+1, count))
                return

            self.progress.emit( "Computing triangle %i out of %i..." % (i+1, count), float(i)/float(count) )

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

            xMin = min(a0[0],a1[0],a2[0])
            yMin = min(a0[1],a1[1],a2[1])
            xMax = max(a0[0],a1[0],a2[0])
            yMax = max(a0[1],a1[1],a2[1])

            xoff = xMin-2
            yoff = yMin-2
            xsize = xMax-xMin+4
            ysize = yMax-yMin+4

            tempTranslated = QTemporaryFile()
            if self.debug: tempTranslated.setAutoRemove(False)
            tempTranslated.open()

            args = ['gdal_translate',
                '-gcp', a0[0]-xoff,a0[1]-yoff,b0[0],b0[1],
                '-gcp', a1[0]-xoff,a1[1]-yoff,b1[0],b1[1],
                '-gcp', a2[0]-xoff,a2[1]-yoff,b2[0],b2[1], 
                '-srcwin', xoff, yoff, xsize, ysize, 
                self.sourcePath,
                tempTranslated.fileName(),
            ]

            sucess, result = self.runCommand(args, 'create the temporaray file %i out of %i' % (i+1, count))
            if not sucess: return



            # Step 2 : we draw the transformed layer on the target layer by providing a cutline (corresponding to the destination triangle)

            # We create a vector polygon to feed into GDAL's -cutline argument
            clip = QgsGeometry.fromPolygon([[b0,b1,b2,b0]]).buffer(.5*abs(rezX)+.5*abs(rezY),2)

            # Since it must be a GDAL format, we have to create a .csv file (hah, command line tools...)
            tempWKT = QTemporaryFile( os.path.join(QDir.tempPath(),'XXXXXX.csv') )
            if self.debug: tempWKT.setAutoRemove(False)
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

            sucess, result = self.runCommand(args, 'patch the triangle %i out of %i' % (i+1, count))
            if not sucess: return




        self.finished.emit()
        return


