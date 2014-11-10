# -*- coding: utf-8 -*-

from qgis.core import *

import algorithm_constrained_delaunay as algDelaunay


def triangulate( pairsLayer, pairsLimitToSelection, constraintsLayer, constraintsLimitToSelection, bufferValue ):

    # Get the features of the pair layer and store them in two arrays
    pointsA = []
    pointsB = []
    constraints = [] # will hold a list of list of points to represent the linestrings constraints

    pairsFeatures = pairsLayer.getFeatures() if not pairsLimitToSelection else pairsLayer.selectedFeatures()
    for feature in pairsFeatures:
        geom = feature.geometry().asPolyline()
        pointsA.append( QgsPoint(geom[0]) )
        pointsB.append( QgsPoint(geom[-1]) )

    def findNearestPointIndex(point):
        nearestIndex = None
        nearestDist = None
        for i,otherPoint in enumerate(pointsA):
            dist = point.sqrDist( otherPoint )
            if nearestIndex is None or dist<nearestDist:
                nearestIndex = i
                nearestDist = dist
        return nearestIndex


    if constraintsLayer is not None:
        constraintsFeatures = constraintsLayer.getFeatures() if not constraintsLimitToSelection else constraintsLayer.selectedFeatures()
        for feature in constraintsFeatures:
            geom = feature.geometry().asPolyline()
            constraint = []
            for point in geom:
                constraint.append( findNearestPointIndex(point) )
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
    