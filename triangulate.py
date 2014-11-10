# -*- coding: utf-8 -*-

from qgis.core import *

import algorithm_constrained_delaunay as algDelaunay


def triangulate( pairsLayer, limitToSelection, bufferValue, closeExpression):

    # Get the features of the pair layer and store them in two arrays
    pointsA = []
    pointsB = []
    constraints = [] # will hold a list of list of points to represent the linestrings constraints
    expression = QgsExpression(closeExpression) # this hold the expression determining whether we close the feature or not

    features = pairsLayer.getFeatures() if not limitToSelection else pairsLayer.selectedFeatures()
    for feature in features:
        constraint = []
        lastPoint = None
        geom = feature.geometry().asPolyline()
        for i in range(0,len(geom)//2):
            pointsA.append( QgsPoint(geom[2*i]) )
            pointsB.append( QgsPoint(geom[2*i+1]) )

            if lastPoint is None:
                lastPoint = len(pointsA)-1

            constraint.append( len(pointsA)-1 )

        # We close the feature if it's a triangle (or more) and if the closeExpression returns true
        if len(constraint)>2:
            if expression.evaluate(feature):
                constraint.append( lastPoint )


        if len(constraint)>2:    
            constraints.append( constraint )

    # Make sure data is valid
    assert len(pointsA)>=3
    assert len(pointsA)==len(pointsB)

    # Compute the hull
    hull = QgsGeometry.fromMultiPoint( pointsA ).convexHull()

    # If there is a buffer, we add a ring outside the hull so that the transformation smoothly stops
    if bufferValue>0:
        expandedHull = hull.buffer(bufferValue, 2)
        for p in expandedHull.asPolygon()[0][:-1]: #we don't take the last point since it's a duplicate
            pointsA.append( p )
            pointsB.append( p )
        hull = expandedHull

    # Create the delaunay triangulation
    delaunay = algDelaunay.computeConstrainedDelaunayTriangulation( pointsA, constraints )

    return [delaunay, pointsA, pointsB, hull, constraints]
    