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
        self.rubberBands = (QgsRubberBand(self.iface.mapCanvas(), QGis.Polygon),
                            QgsRubberBand(self.iface.mapCanvas(), QGis.Polygon))

        # Connect the UI buttons
        self.previewSlider.sliderPressed.connect(self.showPreview)
        self.previewSlider.sliderReleased.connect(self.hidePreview)
        self.previewSlider.sliderMoved.connect(self.updatePreview)

        self.createPairsLayerButton.clicked.connect(self.createPairsLayer)
        self.createConstraintsLayerButton.clicked.connect(self.createConstraintsLayer)

        self.pairsLayerEditModeButton.clicked.connect( self.toggleEditMode )

        self.sourceRasterComboBox.activated.connect( self.loadSourcePath )
        self.targetRasterComboBox.activated.connect( self.loadTargetPath )

        self.styleLayerPair.clicked.connect( self.loadStyleForPair )
        self.styleLayerConstraint.clicked.connect( self.loadStyleForConstraint )

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
    def constraintsLayer(self):
        """
        Returns the current constraintsLayer layer depending on what is choosen in the constraintsLayerComboBox
        """
        layerId = self.constraintsLayerComboBox.itemData(self.constraintsLayerComboBox.currentIndex())
        return QgsMapLayerRegistry.instance().mapLayer(layerId)
    def pairsLayerRestrictToSelection(self):
        """
        Returns the current restrict to selection depending on the input in the checkbox
        """
        return self.pairsLayerRestrictToSelectionCheckBox.isChecked()
    def constraintsLayerRestrictToSelection(self):
        """
        Returns the current restrict to selection depending on the input in the checkbox
        """
        return self.constraintsLayerRestrictToSelectionCheckBox.isChecked()
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

            self.displayMsg("Starting the process !")

            self.runButton.setEnabled(False)
            self.abortButton.setEnabled(True)

            self.workerThread = RasterBenderWorkerThread( self.pairsLayer(), self.pairsLayerRestrictToSelection(), self.constraintsLayer(), self.constraintsLayerRestrictToSelection(), self.bufferValue(), self.blockSizeValue(), self.sourceRasterPath(), self.targetRasterPath() )

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
        self.updateEditStates()

        # Chech the requirements
        self.checkRequirements()

    def updateLayersComboboxes(self):
        """
        Recreate the comboboxes to display existing layers.
        """
        oldPairsLayer = self.pairsLayer()
        oldConstraintsLayer = self.constraintsLayer()

        self.sourceRasterComboBox.clear()
        self.targetRasterComboBox.clear()
        self.pairsLayerComboBox.clear()
        self.constraintsLayerComboBox.clear()

        self.sourceRasterComboBox.addItem( "- loaded rasters -" )
        self.targetRasterComboBox.addItem( "- loaded rasters -" )
        self.constraintsLayerComboBox.addItem( "- none -", None )

        for layer in self.iface.legendInterface().layers():
            if layer.type() == QgsMapLayer.VectorLayer:
                if layer.geometryType() == QGis.Line :
                    self.pairsLayerComboBox.addItem( layer.name(), layer.id() )
                    self.constraintsLayerComboBox.addItem( layer.name(), layer.id() )
            elif layer.type() == QgsMapLayer.RasterLayer:
                self.sourceRasterComboBox.addItem( layer.name(), layer.id() )
                self.targetRasterComboBox.addItem( layer.name(), layer.id() )

        # We switch back to the previously selected layer
        if oldPairsLayer is not None:
            index = self.pairsLayerComboBox.findData(oldPairsLayer.id())
            self.pairsLayerComboBox.setCurrentIndex( index )
        else:
            # If there was no previously selected layer, we make a clever guess using the layers title
            allItems = [ self.pairsLayerComboBox.itemText(i) for i in range(self.pairsLayerComboBox.count())]
            for i,item in enumerate(allItems):
                if item.find("pair") != -1:
                    self.pairsLayerComboBox.setCurrentIndex( i )
                    break

        # We switch back to the previously selected layer
        if oldConstraintsLayer is not None:
            index = self.constraintsLayerComboBox.findData(oldConstraintsLayer.id())
            self.constraintsLayerComboBox.setCurrentIndex( index )
        else:
            # If there was no previously selected layer, we make a clever guess using the layers title
            allItems = [ self.constraintsLayerComboBox.itemText(i) for i in range(self.constraintsLayerComboBox.count())]
            for i,item in enumerate(allItems):
                if item.find("constraint") != -1:
                    self.constraintsLayerComboBox.setCurrentIndex( i )
                    break

    def updateEditStates(self):
        """
        Update the edit state button for layers
        """
        l = self.pairsLayer()
        self.pairsLayerEditModeButton.setChecked( False if (l is None or not l.isEditable()) else True )

        l = self.constraintsLayer()
        self.constraintsLayerEditModeButton.setChecked( False if (l is None or not l.isEditable()) else True )
    
    def checkRequirements(self):
        """
        To be run after changes have been made to the UI. It enables/disables the run button and display some messages.
        """

        canRun = True
        canPreview = True
        errors = []

        # Checkin requirements
        self.runButton.setEnabled(False)
        self.previewSlider.setEnabled(False)

        srcL = self.sourceRasterPath()
        tarL = self.targetRasterPath()
        pL = self.pairsLayer()

        if not QFile(srcL).exists or not QgsRasterLayer.isValidRasterFileName(srcL):
            errors.append( "You must select a valid and existing source raster path !" )
            canRun = False
        if tarL=="":
            errors.append( "You must select a valid target raster path !" )
            canRun = False
        if pL is None:
            errors.append( "You must define a pairs layer.")
            canRun, canPreview = False, False
        elif len(pL.allFeatureIds()) < 3:
            errors.append( "The pairs layers must have at least 3 pairs.")
            canRun, canPreview = False, False
        elif self.pairsLayerRestrictToSelection() and len(pL.selectedFeaturesIds()) < 3:
            errors.append( "You must select at least 3 pairs.")
            canRun, canPreview = False, False
        if self.workerThread is not None and self.workerThread.isRunning():
            errors.append( "The algorithm is already running")
            canRun = False
        if srcL == tarL:
            errors.append( "The source raster will be overwritten !")

        if canPreview:
            self.previewSlider.setEnabled(True)
        if canRun:
            self.runButton.setEnabled(True)

        if len(errors)>0:
            self.displayMsg( "<br/>".join(errors), True)
        else:
            self.displayMsg("Ready to go...")


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
    def createConstraintsLayer(self):
        """
        Creates a new memory layer to be used as pairLayer, and selects it in the ComboBox.
        """

        name="Raster Bender - constraints"
        suffix = ""
        while len( QgsMapLayerRegistry.instance().mapLayersByName( name+suffix ) ) > 0:
            if suffix == "": suffix = " 1"
            else: suffix = " "+str(int(suffix)+1)

        newMemoryLayer = QgsVectorLayer("Linestring", name+suffix, "memory")
        newMemoryLayer.loadNamedStyle(os.path.join(os.path.dirname(__file__),"ConstraintsStyle.qml"), False)
        QgsMapLayerRegistry.instance().addMapLayer(newMemoryLayer)

        self.updateLayersComboboxes()

        index = self.constraintsLayerComboBox.findData(newMemoryLayer.id())
        self.constraintsLayerComboBox.setCurrentIndex( index )
        
        newMemoryLayer.startEditing()
        self.refreshStates()
    def createPairsLayer(self):
        """
        Creates a new memory layer to be used as pairLayer, and selects it in the ComboBox.
        """

        name="Raster Bender - pairs"
        suffix = ""
        while len( QgsMapLayerRegistry.instance().mapLayersByName( name+suffix ) ) > 0:
            if suffix == "": suffix = " 1"
            else: suffix = " "+str(int(suffix)+1)

        newMemoryLayer = QgsVectorLayer("Linestring", name+suffix, "memory")
        newMemoryLayer.loadNamedStyle(os.path.join(os.path.dirname(__file__),"PairStyle.qml"), False)
        QgsMapLayerRegistry.instance().addMapLayer(newMemoryLayer)

        self.updateLayersComboboxes()

        index = self.pairsLayerComboBox.findData(newMemoryLayer.id())
        self.pairsLayerComboBox.setCurrentIndex( index )
        
        newMemoryLayer.startEditing()
        self.refreshStates()

    def loadStyleForConstraint(self):
        layer = self.constraintsLayer()
        if layer is not None:
            layer.loadNamedStyle(os.path.join(os.path.dirname(__file__),"ConstraintsStyle.qml"), False)
        
    def loadStyleForPair(self):
        layer = self.pairsLayer()
        if layer is not None:
            layer.loadNamedStyle(os.path.join(os.path.dirname(__file__),"PairStyle.qml"), False)
        


    


    def displayMsg(self, msg, error=False):
        if error:
            #QApplication.beep()
            msg = "<font color='red'>"+msg+"</font>"
        self.statusLabel.setText( msg )  
    def hidePreview(self):
        self.triangles = None
        self.hull = None
        self.pointsA = None
        self.pointsB = None
        if self.rubberBands is not None:
            self.rubberBands[0].reset(QGis.Polygon)
            self.rubberBands[1].reset(QGis.Polygon)
    def showPreview(self):
        self.triangles, self.pointsA, self.pointsB, self.hull, constraints = triangulate.triangulate( self.pairsLayer(), self.pairsLayerRestrictToSelection(),self.constraintsLayer(), self.constraintsLayerRestrictToSelection(), self.bufferValue() )
        self.updatePreview()
        
    def updatePreview(self):

        if self.rubberBands is not None:
            self.rubberBands[0].reset(QGis.Polygon)
            self.rubberBands[1].reset(QGis.Polygon)

        if self.triangles is None or self.hull is None:
            return

        percent = float(self.previewSlider.sliderPosition()-self.previewSlider.minimum()) / float( self.previewSlider.maximum()-self.previewSlider.minimum() )

        self.rubberBands[0].setColor(QColor(255,255,255,180))
        self.rubberBands[1].setColor(QColor( int((1.0-percent)*255.0),int(percent*170.0),0,255))

        self.rubberBands[0].setBrushStyle(Qt.SolidPattern)        
        self.rubberBands[1].setBrushStyle(Qt.NoBrush)

        self.rubberBands[1].setWidth(2)

        def interpolatePoints(pA, pB, ratio):
            return QgsPoint( (1.0-ratio)*pA.x()+ratio*pB.x(), (1.0-ratio)*pA.y()+ratio*pB.y() )
        
        for i,tri in enumerate(self.triangles):
            #draw the triangles
            self.rubberBands[1].addPoint( interpolatePoints(self.pointsA[tri[0]],self.pointsB[tri[0]],percent), False, i )
            self.rubberBands[1].addPoint( interpolatePoints(self.pointsA[tri[1]],self.pointsB[tri[1]],percent), False, i )
            self.rubberBands[1].addPoint( interpolatePoints(self.pointsA[tri[2]],self.pointsB[tri[2]],percent), True, i ) #TODO : this refreshes the rubber band on each triangle, it should be updated only once after this loop       
            

        #draw the expanded hull
        for p in self.hull.asPolygon()[0]:
            self.rubberBands[0].addPoint( p, True, 0  )


    # Events
    def eventFilter(self,object,event):
        if QEvent is None:
            return False # there's a strange bug where QEvent is sometimes None ?!
        if event.type() == QEvent.FocusIn:
            self.refreshStates()
        return False


