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
from rasterbenderdialog import RasterBenderDialog
from rasterbenderhelp import RasterBenderHelp

class RasterBender:

    def __init__(self, iface):
        self.iface = iface
        self.dlg = RasterBenderDialog(iface,self)

        self._abort = False

        self.ptsA = []
        self.ptsB = []

        self.transformer = None

        self.aboutWindow = None


    def initGui(self):
        
        self.action = QAction( QIcon(os.path.join(os.path.dirname(__file__),'resources','icon.png')), "Raster Bender", self.iface.mainWindow())
        self.action.triggered.connect(self.showUi)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu(u"&Raster Bender", self.action)

        self.helpAction = QAction( QIcon(os.path.join(os.path.dirname(__file__),'resources','about.png')), "Raster Bender Help", self.iface.mainWindow())
        self.helpAction.triggered.connect(self.showHelp)
        self.iface.addPluginToMenu(u"&Raster Bender", self.helpAction)

    def showHelp(self):
        if self.aboutWindow is None:
            self.aboutWindow = RasterBenderHelp()
        self.aboutWindow.show()
        self.aboutWindow.raise_() 

    def unload(self):
        if self.dlg is not None:
            self.dlg.close()
            self.dlg = None

        if self.aboutWindow is not None:
            self.aboutWindow.close()
            self.aboutWindow = None

        self.iface.removePluginMenu(u"&Raster Bender", self.action)
        self.iface.removePluginMenu(u"&Raster Bender", self.helpAction)
        self.iface.removeToolBarIcon(self.action)

    def showUi(self):
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.refreshStates()

    def determineTransformationType(self):
        """Returns :
            0 if no pairs Found
            1 if one pair found => translation
            2 if two pairs found => linear
            3 if three or more pairs found => bending"""

        pairsLayer = self.dlg.pairsLayer()

        if pairsLayer is None:
            return 0

        featuresCount = len(pairsLayer.selectedFeaturesIds()) if self.dlg.pairsLayerRestrictToSelectionCheckBox.isChecked() else len(pairsLayer.allFeatureIds())
        
        if featuresCount == 1:
            return 1
        elif featuresCount == 2:
            return 2
        elif featuresCount >= 3:
            return 3

        return 0

    def abort(self):
        self._abort = True
    
    def run(self):
        self._abort = False

        self.dlg.pixelProgressBar.setValue( 0 )
        self.dlg.blockProgressBar.setValue( 0 )

        #targetRaster = self.dlg.targetRaster()
        #sourceRaster = self.dlg.sourceRaster()
        pairsLayer = self.dlg.pairsLayer()

        transType = self.determineTransformationType()

        # Loading the delaunay
        restrictToSelection = self.dlg.pairsLayerRestrictToSelectionCheckBox.isChecked()
        if transType==3:
            self.dlg.displayMsg( "Loading delaunay mesh (%i points) ..." % len(self.ptsA) )
            QCoreApplication.processEvents()
            self.transformer = BendTransformer( pairsLayer, restrictToSelection, self.dlg.bufferValue() )
        elif transType==2:
            self.dlg.displayMsg( "Loading linear transformation vectors..."  )
            self.transformer = LinearTransformer( pairsLayer, restrictToSelection )
        elif transType==1:
            self.dlg.displayMsg( "Loading translation vector..."  )
            self.transformer = TranslationTransformer( pairsLayer, restrictToSelection )
        else:
            self.dlg.displayMsg( "INVALID TRANSFORMATION TYPE - YOU SHOULDN'T HAVE BEEN ABLE TO HIT RUN" )
            return


        # Starting to through all target pixels

        #Open the dataset
        gdal.UseExceptions()

        # Read the source data into numpy arrays
        dsSource = gdal.Open( self.dlg.sourceRasterPath(), gdal.GA_ReadOnly )

        sourceDataR = gdalnumeric.BandReadAsArray(dsSource.GetRasterBand(1))
        sourceDataG = gdalnumeric.BandReadAsArray(dsSource.GetRasterBand(2))
        sourceDataB = gdalnumeric.BandReadAsArray(dsSource.GetRasterBand(3))

        # Open the target into numpy array
        if not QFile(self.dlg.targetRasterPath()).exists():
            shutil.copy( self.dlg.sourceRasterPath(), self.dlg.targetRasterPath() ) # if the target doesn't exist, we use the source target

        dsTarget = gdal.Open(self.dlg.targetRasterPath(), gdal.GA_Update )

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


        displayTotal = dsTarget.RasterXSize*dsTarget.RasterYSize
        displayStep = min(displayTotal/100,5000) # update gui every n steps

        #Loop through every block
        blockSize = 500
        blockCountX = dsTarget.RasterXSize/blockSize
        blockCountY = dsTarget.RasterYSize/blockSize
        blockCount = blockCountX*blockCountY
        blockI = 0

        self.dlg.displayMsg( "Starting computation... %i points to compute !! This can take a while..."  % (displayTotal))
        QCoreApplication.processEvents()

        for blockNumY in range(0, blockCountX+1 ):
            blockOffsetY = blockNumY*blockSize
            blockH = min( blockSize, dsTarget.RasterYSize-blockOffsetY )
            if blockH == 0: continue

            for blockNumX in range(0, blockCountY+1 ):
                blockOffsetX = blockNumX*blockSize
                blockW = min( blockSize, dsTarget.RasterXSize-blockOffsetX )
                if blockW == 0: continue

                blockI += 1
                pixelCount = blockW*blockH
                pixelI = 0

                targetDataR = numpy.ndarray( (blockH, blockW) )
                targetDataG = numpy.ndarray( (blockH, blockW) )
                targetDataB = numpy.ndarray( (blockH, blockW) )

                # Loop through every pixel
                for y in range(0, blockH):
                    for x in range(0, blockW):

                        if self._abort:
                            self.dlg.displayMsg( "Aborted on pixel %i out of %i on block %i out of %i..."  % (pixelI, pixelCount, blockI, blockCount ), True)
                            QCoreApplication.processEvents()
                            return


                        pixelI+=1
                        if pixelI%displayStep == 0:
                            self.dlg.pixelProgressBar.setValue( int(100.0*float(pixelI)/float(pixelCount)) )
                            self.dlg.blockProgressBar.setValue( int(100.0*float(blockI)/float(blockCount)) )
                            self.dlg.displayMsg( "Working on pixel %i out of %i on block %i out of %i..."  % (pixelI, pixelCount, blockI, blockCount ))
                            QCoreApplication.processEvents()

                        newX, newY = qgsPointToXY(  self.transformer.map( xyToQgsPoint(blockOffsetX+x,blockOffsetY+y) )  )

                        #ident = sourceRaster.dataProvider().identify( pt, QgsRaster.IdentifyFormatValue)

                        #targetDataR[y][x] = ident.results()[1]
                        #targetDataG[y][x] = ident.results()[2]
                        #targetDataB[y][x] = ident.results()[3]

                        try:
                            if newY<0 or newX<0: #avoid looping
                                raise IndexError()
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

        self.dlg.finish()


