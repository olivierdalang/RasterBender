# -*- coding: utf-8 -*-

from PyQt4 import uic
from PyQt4.QtCore import *
from PyQt4.QtGui import *

from qgis.core import *
from qgis.gui import *

import os.path

# Other classes
import triangulate # it seems we can't import fTools' voronoi directly, so we ship a copy of the file
from rasterbenderworkerthread import RasterBenderWorkerThread


class RasterBenderDialog(QWidget):
    def __init__(self, iface, rb):
        QWidget.__init__(self)
        uic.loadUi(os.path.join(os.path.dirname(__file__),'ui_main.ui'), self)
        self.setFocusPolicy(Qt.ClickFocus)
        #self.setWindowModality( Qt.ApplicationModal )

        self.iface = iface
        self.rb = rb
        self.worker = None
        self.workerThread = None

        # Keeps three rubberbands for delaunay's peview
        self.rubberBands = None

        # Connect the UI buttons
        self.previewButton.pressed.connect(self.showPreview)
        self.previewButton.released.connect(self.hidePreview)

        self.createMemoryLayerButton.clicked.connect(self.createMemoryLayer)

        self.pairsLayerEditModeButton.clicked.connect( self.toggleEditMode )

        self.sourceRasterComboBox.activated.connect( self.loadSourcePath )
        self.targetRasterComboBox.activated.connect( self.loadTargetPath )

        self.runButton.clicked.connect(self.run)
        self.abortButton.clicked.connect(self.abort)

        # When those are changed, we refresh the states
        self.sourceRasterPathLineEdit.textChanged.connect( self.refreshStates )
        self.targetRasterPathLineEdit.textChanged.connect( self.refreshStates )
        self.pairsLayerComboBox.activated.connect( self.refreshStates )
        self.pairsLayerRestrictToSelectionCheckBox.stateChanged.connect( self.refreshStates )

        # Create an event filter to update on focus
        self.installEventFilter(self)


    # UI Getters
    def sourceRaster(self):
        """
        Returns the current toBend layer depending on what is choosen in the pairsLayerComboBox
        """
        layerId = self.sourceRasterComboBox.itemData(self.sourceRasterComboBox.currentIndex())
        return QgsMapLayerRegistry.instance().mapLayer(layerId)
    def targetRaster(self):
        """
        Returns the current toBend layer depending on what is choosen in the pairsLayerComboBox
        """
        layerId = self.targetRasterComboBox.itemData(self.targetRasterComboBox.currentIndex())
        return QgsMapLayerRegistry.instance().mapLayer(layerId)
    def sourceRasterPath(self):
        """
        Returns the current source raster path
        """
        return self.sourceRasterPathLineEdit.text()
    def targetRasterPath(self):
        """
        Returns the current target raster path
        """
        return self.targetRasterPathLineEdit.text()
    def pairsLayer(self):
        """
        Returns the current pairsLayer layer depending on what is choosen in the pairsLayerComboBox
        """
        layerId = self.pairsLayerComboBox.itemData(self.pairsLayerComboBox.currentIndex())
        return QgsMapLayerRegistry.instance().mapLayer(layerId)
    def restrictToSelection(self):
        """
        Returns the current restrict to selection depending on the input in the checkbox
        """
        return self.pairsLayerRestrictToSelectionCheckBox.isChecked()
    def bufferValue(self):
        """
        Returns the current buffer value depending on the input in the spinbox
        """
        return self.bufferSpinBox.value()
    def blockSizeValue(self):
        """
        Returns the current blockSize value depending on the input in the spinbox
        """
        return self.blockSizeSpinBox.value()

    # Thread management
    def run(self):
        self.endThread()

        if self.worker is None or not self.worker.isRunning():

            self.runButton.setEnabled(False)
            self.abortButton.setEnabled(True)

            self.workerThread = RasterBenderWorkerThread( self.pairsLayer(), self.restrictToSelection(), self.bufferValue(), self.blockSizeValue(), self.sourceRasterPath(), self.targetRasterPath() )

            self.workerThread.finished.connect( self.finish )
            self.workerThread.error.connect( self.error )
            self.workerThread.progress.connect( self.progress )

            self.workerThread.start()

    def abort(self):
        if self.workerThread is not None:
            self.workerThread.abort()
    def endThread(self):
        if self.workerThread is not None:
            self.workerThread.quit()
            self.workerThread.wait()
            self.workerThread.deleteLater()
            self.workerThread = None


    # Thread slots
    def progress(self, string, progPixel, progBlock):
        self.pixelProgressBar.setValue( int(progPixel*100) )
        self.blockProgressBar.setValue( int(progBlock*100) )
        self.displayMsg( string )    
    def error(self, string):
        self.displayMsg( string, True )
        self.runButton.setEnabled(True)
        self.abortButton.setEnabled(False)
        self.endThread()
    def finish(self):
        self.displayMsg( "Done !" )
        self.blockProgressBar.setValue( 100 )
        self.pixelProgressBar.setValue( 100 )
        self.runButton.setEnabled(True)
        self.abortButton.setEnabled(False)
        self.endThread()



    # Updaters
    def refreshStates(self):
        """
        Updates the UI values, to be used upon opening / activating the window
        """

        # Update the comboboxes
        self.updateLayersComboboxes()

        # Update the edit mode buttons
        self.updateEditState_pairsLayer()

        # Chech the requirements
        self.checkRequirements()

    def updateLayersComboboxes(self):
        """
        Recreate the comboboxes to display existing layers.
        """
        oldPairsLayer = self.pairsLayer()

        self.sourceRasterComboBox.clear()
        self.targetRasterComboBox.clear()
        self.pairsLayerComboBox.clear()

        self.sourceRasterComboBox.addItem( "- loaded rasters -" )
        self.targetRasterComboBox.addItem( "- loaded rasters -" )

        for layer in self.iface.legendInterface().layers():
            if layer.type() == QgsMapLayer.VectorLayer:
                if layer.geometryType() == QGis.Line :
                    self.pairsLayerComboBox.addItem( layer.name(), layer.id() )
            elif layer.type() == QgsMapLayer.RasterLayer:
                self.sourceRasterComboBox.addItem( layer.name(), layer.id() )
                self.targetRasterComboBox.addItem( layer.name(), layer.id() )

        if oldPairsLayer is not None:
            index = self.pairsLayerComboBox.findData(oldPairsLayer.id())
            self.pairsLayerComboBox.setCurrentIndex( index )
    def updateEditState_pairsLayer(self):
        """
        Update the edit state button for pairsLayer
        """
        l = self.pairsLayer()
        self.pairsLayerEditModeButton.setChecked( False if (l is None or not l.isEditable()) else True )
    
    def checkRequirements(self):
        """
        To be run after changes have been made to the UI. It enables/disables the run button and display some messages.
        """
        # Checkin requirements
        self.runButton.setEnabled(False)

        srcL = self.sourceRasterPath()
        tarL = self.targetRasterPath()
        pL = self.pairsLayer()

        if not QFile(srcL).exists or not QgsRasterLayer.isValidRasterFileName(srcL):
            self.displayMsg( "You must select a valid and existing source raster path !", True )
            return
        if tarL=="":
            self.displayMsg( "You must select a valid target raster path !", True )
            return
        if pL is None:
            self.displayMsg( "You must define a pairs layer.", True)
            return
        if len(pL.allFeatureIds()) < 3:
            self.displayMsg( "The pairs layers must have at least 3 pairs.", True)
            return
        if self.restrictToSelection() and len(pL.selectedFeaturesIds()) < 3:
            self.displayMsg( "You must select at least 3 pairs.", True)
            return
        if self.workerThread is not None and self.workerThread.isRunning():
            self.displayMsg( "The algorithm is already running", True)
            return
        if srcL == tarL:
            self.displayMsg( "The source raster will be overwritten !", True)
        else:        
            self.displayMsg("Ready to go...")
        self.runButton.setEnabled(True)

    # UI Setters
    def loadSourcePath(self):
        if self.sourceRaster() is not None:
            self.sourceRasterPathLineEdit.setText( self.sourceRaster().dataProvider().dataSourceUri() )
    def loadTargetPath(self):
        if self.targetRaster() is not None:
            self.targetRasterPathLineEdit.setText( self.targetRaster().dataProvider().dataSourceUri() )

    # Togglers
    def toggleEditMode(self, checked):
        l = self.pairsLayer()
        if l is None:
            return 

        if checked:
            l.startEditing()
        else:
            if not l.isModified():
                l.rollBack()
            else:
                retval = QMessageBox.warning(self, "Stop editting", "Do you want to save the changes to layer %s ?" % l.name(), QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)

                if retval == QMessageBox.Save:
                    l.commitChanges()
                elif retval == QMessageBox.Discard:
                    l.rollBack()
        self.refreshStates()

    # Misc
    def createMemoryLayer(self):
        """
        Creates a new memory layer to be used as pairLayer, and selects it in the ComboBox.
        """

        suffix = ""
        name = "Raster Bender"
        while len( QgsMapLayerRegistry.instance().mapLayersByName( name+suffix ) ) > 0:
            if suffix == "": suffix = " 1"
            else: suffix = " "+str(int(suffix)+1)

        newMemoryLayer = QgsVectorLayer("Linestring", name+suffix, "memory")
        newMemoryLayer.loadNamedStyle(os.path.join(os.path.dirname(__file__),'PairStyle.qml'), False)
        QgsMapLayerRegistry.instance().addMapLayer(newMemoryLayer)

        self.updateLayersComboboxes()

        index = self.pairsLayerComboBox.findData(newMemoryLayer.id())
        self.pairsLayerComboBox.setCurrentIndex( index )
        
        newMemoryLayer.startEditing()
        self.refreshStates()
    


    def displayMsg(self, msg, error=False):
        if error:
            #QApplication.beep()
            msg = "<font color='red'>"+msg+"</font>"
        self.statusLabel.setText( msg )  
    def hidePreview(self):
        if self.rubberBands is not None:
            self.rubberBands[0].reset(QGis.Polygon)
            self.rubberBands[1].reset(QGis.Polygon)
            self.rubberBands[2].reset(QGis.Polygon)
            self.rubberBands[3].reset(QGis.Polygon)
            self.rubberBands[4].reset(QGis.Polygon)
            self.rubberBands = None
    def showPreview(self):

        self.rubberBands = (QgsRubberBand(self.iface.mapCanvas(), QGis.Polygon),
                            QgsRubberBand(self.iface.mapCanvas(), QGis.Polygon),
                            QgsRubberBand(self.iface.mapCanvas(), QGis.Polygon),
                            QgsRubberBand(self.iface.mapCanvas(), QGis.Line),
                            QgsRubberBand(self.iface.mapCanvas(), QGis.Line))

        self.rubberBands[0].reset(QGis.Polygon)
        self.rubberBands[1].reset(QGis.Polygon)
        self.rubberBands[2].reset(QGis.Polygon)
        self.rubberBands[3].reset(QGis.Line)
        self.rubberBands[4].reset(QGis.Line)

        self.rubberBands[0].setColor(QColor(255,255,255,175))
        self.rubberBands[1].setColor(QColor(255,0,0,50))
        self.rubberBands[2].setColor(QColor(0,255,0,150))
        self.rubberBands[3].setColor(QColor(0,0,255,255))
        self.rubberBands[4].setColor(QColor(0,0,0,255))

        self.rubberBands[0].setBrushStyle(Qt.SolidPattern)        
        self.rubberBands[1].setBrushStyle(Qt.Dense4Pattern)
        self.rubberBands[2].setBrushStyle(Qt.NoBrush)
        self.rubberBands[4].setLineStyle(Qt.DashLine)

        self.rubberBands[1].setWidth(3)
        self.rubberBands[2].setWidth(1)  
        self.rubberBands[3].setWidth(5)  
        self.rubberBands[4].setWidth(2)      

        triangles, pointsA, pointsB, hull, constraints = triangulate.triangulate( self.pairsLayer(), self.restrictToSelection(), self.bufferValue() )

        for i,tri in enumerate(triangles):
            #draw the source triangles
            #self.rubberBands[2].addPoint( pointsA[tri[0]], False, i  )
            #self.rubberBands[2].addPoint( pointsA[tri[1]], False, i  )
            #self.rubberBands[2].addPoint( pointsA[tri[2]], True, i  ) #TODO : this refreshes the rubber band on each triangle, it should be updated only once after this loop       

            #draw the target triangles
            self.rubberBands[1].addPoint( pointsB[tri[0]], False, i  )
            self.rubberBands[1].addPoint( pointsB[tri[1]], False, i  )
            self.rubberBands[1].addPoint( pointsB[tri[2]], True, i  ) #TODO : this refreshes the rubber band on each triangle, it should be updated only once after this loop       
        
        #draw the constraints
        multiPolylineConstraints = []
        for constraint in constraints:
            multiPolylineConstraint = []
            for pID in constraint:
                multiPolylineConstraint.append( pointsB[pID] )
            multiPolylineConstraints.append( multiPolylineConstraint )
        self.rubberBands[4].setToGeometry( QgsGeometry.fromMultiPolyline(multiPolylineConstraints), None  )

        #draw the pairs
        multiPolylinePairs = []
        for i,p in enumerate(pointsA):
            multiPolylinePairs.append( [pointsA[i],pointsB[i]] )
        self.rubberBands[3].setToGeometry( QgsGeometry.fromMultiPolyline(multiPolylinePairs), None  )

        #draw the expanded hull
        for p in hull.asPolygon()[0]:
            self.rubberBands[0].addPoint( p, True, 0  )

    # Events
    def eventFilter(self,object,event):
        if QEvent is None:
            return False # there's a strange bug where QEvent is sometimes None ?!
        if event.type() == QEvent.FocusIn:
            self.refreshStates()
        return False


