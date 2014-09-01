
from qgis.core import *

import algorithm_voronoi as voronoi


def triangulate( pairsLayer, limitToSelection, bufferValue):

    # Get the features of the pair layer and store them in two arrays
    pointsA = []
    pointsB = []
    features = pairsLayer.getFeatures() if not limitToSelection else pairsLayer.selectedFeatures()
    for feature in features:
        geom = feature.geometry().asPolyline()
        pointsA.append( QgsPoint(geom[ 0]) )
        pointsB.append( QgsPoint(geom[-1]) )

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
    delaunay = voronoi.computeDelaunayTriangulation( [voronoi.Site(p.x(), p.y()) for p in pointsA] )

    return [delaunay, pointsA, pointsB, hull]
    