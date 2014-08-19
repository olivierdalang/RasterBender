# -*- coding: utf-8 -*-

from PyQt4 import uic
from PyQt4.QtCore import *
from PyQt4.QtGui import *

from qgis.core import *
from qgis.gui import *

import os.path

from rasterbendertransformers import *


class RasterBenderDialog(QWidget):
    def __init__(self, iface, rb):
        QWidget.__init__(self)
        uic.loadUi(os.path.join(os.path.dirname(__file__),'ui_main.ui'), self)
        self.setFocusPolicy(Qt.ClickFocus)
        #self.setWindowModality( Qt.ApplicationModal )

        self.iface = iface
        self.rb = rb

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
    def bufferValue(self):
        """
        Returns the current buffer value depending on the input in the spinbox
        """
        return self.bufferSpinBox.value()

    def run(self):
        self.runButton.setEnabled(False)
        self.abortButton.setEnabled(True)
        self.rb.run()
    def abort(self):
        self.runButton.setEnabled(True)
        self.abortButton.setEnabled(False)
        self.rb.abort()
    def finish(self):
        self.displayMsg( "Done !" )
        self.blockProgressBar.setValue( 100 )
        self.pixelProgressBar.setValue( 100 )
        self.runButton.setEnabled(True)
        self.abortButton.setEnabled(False)


    # Updaters
    def refreshStates(self):
        """
        Updates the UI values, to be used upon opening / activating the window
        """

        # Update the comboboxes
        self.updateLayersComboboxes()

        # Update the edit mode buttons
        self.updateEditState_pairsLayer()

        # Update the transformation type
        self.updateTransformationType()

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
    def updateTransformationType(self):
        """
        Update the stacked widget to display the proper transformation type. Also runs checkRequirements() 
        """
        self.stackedWidget.setCurrentIndex( self.rb.determineTransformationType() )

        self.checkRequirements()
    def checkRequirements(self):
        """
        To be run after changes have been made to the UI. It enables/disables the run button and display some messages.
        """
        # Checkin requirements
        self.runButton.setEnabled(False)

        srcL = self.sourceRasterPath()
        tarL = self.targetRasterPath()
        pl = self.pairsLayer()

        transType = self.rb.determineTransformationType()

        if not QFile(srcL).exists or not QgsRasterLayer.isValidRasterFileName(srcL):
            self.displayMsg( "You must select a valid and existing source raster path !", True )
            return
        if transType == 3 and tarL=="":
            self.displayMsg( "You must select a valid target raster path for a bending transformation !", True )
            return
        if transType == 0:
            self.displayMsg("Impossible to run with an invalid transformation type.", True)
            return 
        if srcL == tarL:
            self.displayMsg("The source raster will be overwritten !", True)
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
            self.rubberBands = None
    def showPreview(self):

        self.rubberBands = (QgsRubberBand(self.iface.mapCanvas(), QGis.Polygon),
                            QgsRubberBand(self.iface.mapCanvas(), QGis.Polygon),
                            QgsRubberBand(self.iface.mapCanvas(), QGis.Polygon),
                            QgsRubberBand(self.iface.mapCanvas(), QGis.Polygon))

        self.rubberBands[0].reset(QGis.Polygon)
        self.rubberBands[1].reset(QGis.Polygon)
        self.rubberBands[2].reset(QGis.Polygon)
        self.rubberBands[3].reset(QGis.Polygon)

        pairsLayer = self.pairsLayer()

        transformer = BendTransformer( pairsLayer, self.pairsLayerRestrictToSelectionCheckBox.isChecked() ,self.bufferValue() )

        self.rubberBands[0].setColor(QColor(220,220,255,175))
        self.rubberBands[1].setColor(QColor(255,255,255,215))
        self.rubberBands[2].setColor(QColor(255,0,0,50))
        self.rubberBands[3].setColor(QColor(0,255,0,150))

        self.rubberBands[0].setBrushStyle(Qt.SolidPattern)
        self.rubberBands[1].setBrushStyle(Qt.SolidPattern)
        self.rubberBands[2].setBrushStyle(Qt.NoBrush)
        self.rubberBands[3].setBrushStyle(Qt.NoBrush)

        self.rubberBands[2].setWidth(3)
        self.rubberBands[3].setWidth(1)      

        for i,tri in enumerate(transformer.delaunay):
            #draw the source triangles
            self.rubberBands[3].addPoint( transformer.pointsA[tri[0]], False, i  )
            self.rubberBands[3].addPoint( transformer.pointsA[tri[1]], False, i  )
            self.rubberBands[3].addPoint( transformer.pointsA[tri[2]], True, i  ) #TODO : this refreshes the rubber band on each triangle, it should be updated only once after this loop       

            #draw the target triangles
            self.rubberBands[2].addPoint( transformer.pointsB[tri[0]], False, i  )
            self.rubberBands[2].addPoint( transformer.pointsB[tri[1]], False, i  )
            self.rubberBands[2].addPoint( transformer.pointsB[tri[2]], True, i  ) #TODO : this refreshes the rubber band on each triangle, it should be updated only once after this loop       
        
        #draw the expanded hull
        if transformer.expandedHull is not None:
            for p in transformer.expandedHull.asPolygon()[0]:
                self.rubberBands[0].addPoint( p, True, 0  )
            for p in transformer.expandedHull.asPolygon()[0][0:1]:
                #we readd the first point since it's not possible to make true rings with rubberbands
                self.rubberBands[0].addPoint( p, True, 0  )

        #draw the hull
        for p in transformer.hull.asPolygon()[0]:
            self.rubberBands[0].addPoint( p, True, 0  ) #inner ring of rubberband 1
            self.rubberBands[1].addPoint( p, True, 0  )
        for p in transformer.hull.asPolygon()[0][0:1]:
            #we readd the first point since it's not possible to make true rings with rubberbands
            self.rubberBands[0].addPoint( p, True, 0  )
    # Events
    def eventFilter(self,object,event):
        if QEvent is None:
            return False # there's a strange bug where QEvent is sometimes None ?!
        if event.type() == QEvent.FocusIn:
            self.refreshStates()
        return False


