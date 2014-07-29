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
import os.path
import sys
import math

# More tricky dependencies
from distutils.version import StrictVersion
dependenciesStatus = 2 # 2: ok, 1: too old, 0: missing
try:
    import matplotlib.tri
    minVersion = '1.3.0'
    if StrictVersion(matplotlib.__version__) < StrictVersion(minVersion):
        dependenciesStatus=1
        QgsMessageLog.logMessage("Matplotlib version too old (%s instead of %s). You won't be able to use the bending algorithm" % (matplotlib.__version__,minVersion), 'RasterBender')
except Exception, e:
    QgsMessageLog.logMessage("Matplotlib is missing. You won't be able to use the bending algorithm", 'RasterBender')
    dependenciesStatus = 0

# Other classes
from rasterbendertransformers import *
from rasterbenderdialog import RasterBenderDialog
from rasterbenderhelp import RasterBenderHelp

class RasterBender:

    def __init__(self, iface):
        self.iface = iface
        self.dlg = RasterBenderDialog(iface,self)

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
            3 if three or more pairs found => bending
            4 if bending but unmet dependencies"""

        pairsLayer = self.dlg.pairsLayer()

        if pairsLayer is None:
            return 0

        featuresCount = len(pairsLayer.selectedFeaturesIds()) if self.dlg.restrictBox_pairsLayer.isChecked() else len(pairsLayer.allFeatureIds())
        
        if featuresCount == 1:
            return 1
        elif featuresCount == 2:
            return 2
        elif featuresCount >= 3:
            if dependenciesStatus != 2:
                return 4
            else:
                return 3

        return 0
    
    def run(self):

        self.dlg.progressBar.setValue( 0 )

        toBendLayer = self.dlg.toBendLayer()
        pairsLayer = self.dlg.pairsLayer()

        transType = self.determineTransformationType()

        # Loading the delaunay
        restrictToSelection = self.dlg.restrictBox_pairsLayer.isChecked()
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

        # Starting to iterate
        features = toBendLayer.getFeatures() if not self.dlg.restrictBox_toBendLayer.isChecked() else toBendLayer.selectedFeatures()

        count = toBendLayer.pendingFeatureCount() if not self.dlg.restrictBox_toBendLayer.isChecked() else len(features)
        self.dlg.displayMsg( "Starting to iterate through %i features..." % count )
        QCoreApplication.processEvents()

        toBendLayer.beginEditCommand("Feature bending")
        for i,feature in enumerate(features):

            self.dlg.progressBar.setValue( int(100.0*float(i)/float(count)) )
            self.dlg.displayMsg( "Aligning features %i out of %i..."  % (i, count))
            QCoreApplication.processEvents()

            geom = feature.geometry()

            #TODO : this cood be much simple if we could iterate through to vertices and use QgsGeometry.moveVertex(x,y,index), but QgsGeometry.vertexAt(index) doesn't tell wether the index exists, so there's no clean way to iterate...

            if geom.type() == QGis.Point:

                if not geom.isMultipart():
                    # SINGLE PART POINT
                    p = geom.asPoint()
                    newGeom = QgsGeometry.fromPoint( self.transformer.map(p) )

                else:
                    # MULTI PART POINT
                    listA = geom.asMultiPoint()
                    newListA = []
                    for p in listA:
                        newListA.append( self.transformer.map(p) )
                    newGeom = QgsGeometry.fromMultiPoint( newListA )

            elif geom.type() == QGis.Line:

                if not geom.isMultipart():
                    # SINGLE PART LINESTRING
                    listA = geom.asPolyline()
                    newListA = []
                    for p in listA:
                        newListA.append( self.transformer.map(p) )
                    newGeom = QgsGeometry.fromPolyline( newListA )

                else:
                    # MULTI PART LINESTRING
                    listA = geom.asMultiPolyline()
                    newListA = []
                    for listB in listA:
                        newListB = []
                        for p in listB:
                            newListB.append( self.transformer.map(p) )
                        newListA.append( newListB )
                    newGeom = QgsGeometry.fromMultiPolyline( newListA )

            elif geom.type() == QGis.Polygon:

                if not geom.isMultipart():
                    # SINGLE PART POLYGON
                    listA = geom.asPolygon()
                    newListA = []
                    for listB in listA:
                        newListB = []
                        for p in listB:
                            newListB.append( self.transformer.map(p) )
                        newListA.append( newListB )
                    newGeom = QgsGeometry.fromPolygon( newListA )

                else:
                    # MULTI PART POLYGON
                    listA = geom.asMultiPolygon()
                    newListA = []
                    for listB in listA:
                        newListB = []
                        for listC in listB:
                            newListC = []
                            for p in listC:
                                newListC.append( self.transformer.map(p) )
                            newListB.append( newListC )
                        newListA.append( newListB )
                    newGeom = QgsGeometry.fromMultiPolygon( newListA )

            else:
                # FALLBACK, JUST IN CASE ;)
                newGeom = geom

            toBendLayer.changeGeometry( feature.id(), newGeom )

        toBendLayer.endEditCommand()
        toBendLayer.repaintRequested.emit()


        #Transforming pairs to pins
        if self.dlg.pairsToPinsCheckBox.isChecked():

            features = pairsLayer.getFeatures() if not self.dlg.restrictBox_pairsLayer.isChecked() else pairsLayer.selectedFeatures()

            count = pairsLayer.pendingFeatureCount() if not self.dlg.restrictBox_pairsLayer.isChecked() else len(features)
            self.dlg.progressBar.setValue( 0 )
            self.dlg.displayMsg( "Starting to transform %i pairs to pins..." % count )
            QCoreApplication.processEvents()

            pairsLayer.beginEditCommand("Transforming pairs to pins")
            for i,feature in enumerate(features):

                self.dlg.progressBar.setValue( int(100.0*float(i)/float(count)) )
                self.dlg.displayMsg( "Transforming pair to pin %i out of %i..."  % (i, count))
                QCoreApplication.processEvents()

                geom = feature.geometry().asPolyline()

                newGeom = QgsGeometry.fromPolyline( [geom[-1],geom[-1]] )
                pairsLayer.changeGeometry( feature.id(), newGeom )

            pairsLayer.endEditCommand()

        self.dlg.displayMsg( "Finished !" )
        self.dlg.progressBar.setValue( 100 )
        pairsLayer.repaintRequested.emit()
