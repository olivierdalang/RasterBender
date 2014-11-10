# -*- coding: utf-8 -*-

from qgis.core import *

import algorithm_voronoi as voronoi

def computeConstrainedDelaunayTriangulation(points, constraints):
    """
    This will return a constrained Delaunay triangulation.

    Input
    points: array of QgsPoint
    constraints: array of linestrings that form the constrains

    Returns a list of 3 uples being the indices of the points forming the triangles
    """

    # We get the normal delaunay triangulation
    triangles = voronoi.computeDelaunayTriangulation( [voronoi.Site(p.x(), p.y()) for p in points] )


    # QgsMessageLog.logMessage("\n\n\nAll the triangles : %s" % str(triangles))

    # Now we have to constrain the delaunay triangulation.
    # For each needed segment, we'll delete the intersecting triangles to make room for the constrain, and retriangulate it.
    

    # Utils functions
    def intersects(seg1, seg2):
        seg1Geom = QgsGeometry.fromPolyline( [points[pID] for pID in seg1] )
        seg2Geom = QgsGeometry.fromPolyline( [points[pID] for pID in seg2] )
        return seg1Geom.crosses(seg2Geom)

    def isPointLeftOfRay(point, segmentPointA, segmentPointB):
        x = point.x()
        y = point.y()
        raySx = segmentPointA.x()
        raySy = segmentPointA.y()
        rayEx = segmentPointB.x()
        rayEy = segmentPointB.y()
        return ((y-raySy)*(rayEx-raySx)) > ((x-raySx)*(rayEy-raySy))


    # Each linestring is a constraint
    for constraint in constraints:

        # For each segment, we must delete and retriangulate the triangles that it crosses
        for i,point in enumerate(constraint):

            segment = [constraint[i-1],constraint[i]]


            # QgsMessageLog.logMessage("Segment is %s" % str(segment))

            trianglesToRemove = [] # This will store the triangles that must be deleted

            # We check for intersection 
            for triangle in triangles:
                for edge in [ [triangle[0],triangle[1]], [triangle[1],triangle[2]], [triangle[2],triangle[0]] ]:
                    if intersects(segment, edge):
                        # QgsMessageLog.logMessage("We must remove %s" % str(triangle) )
                        trianglesToRemove.append(triangle) # If there is an intersection between the segment and an edge of the triangle, we have to remove it
                        break


            # Now we're going to remove all the triangles, and retriangulate the left and the right part of the segment
            if len(trianglesToRemove)>0:

                pointsLeft = set() # This will hold the list of points IDs consituing the part to be retriangulated on the left side of the segment
                pointsRight = set() # This will hold the list of points IDs consituing the part to be retriangulated on the right side of the segment

                pointsLeft.add(segment[0])
                pointsLeft.add(segment[1])
                pointsRight.add(segment[0])
                pointsRight.add(segment[1])

                # QgsMessageLog.logMessage("%s was added to the left as part of the segment" % str(pointsLeft))
                # QgsMessageLog.logMessage("%s was added to the right as part of the segment" % str(pointsRight))

                for triToRemove in trianglesToRemove:

                    # QgsMessageLog.logMessage("We remove %s" % str(triToRemove))
                    triangles.remove( triToRemove ) # We remove the triangles

                    for pID in triToRemove: # And for each poiont
                        if isPointLeftOfRay( points[pID], points[segment[0]], points[segment[1]]):
                            pointsLeft.add(pID)
                            # QgsMessageLog.logMessage("%i was added to the left" % pID)
                        else:
                            pointsRight.add(pID)
                            # QgsMessageLog.logMessage("%i was added to the right" % pID)

                    
                # QgsMessageLog.logMessage("Pointsleft is %s" % str(pointsLeft) )
                # QgsMessageLog.logMessage("Pointsright is %s" % str(pointsRight) )

                # We compute the delaunay triangulation for the left side
                arrayLeft = list(pointsLeft)
                trianglesLeft = voronoi.computeDelaunayTriangulation( [voronoi.Site(points[pID].x(), points[pID].y()) for pID in pointsLeft] )
                # QgsMessageLog.logMessage("%i triangles computed for the left (%s)" % (len(trianglesLeft),trianglesLeft))  
                for tri in trianglesLeft:
                    # And map the triangles point indices to the actual point indices
                    mappedTri = [ arrayLeft[tri[0]],arrayLeft[tri[1]],arrayLeft[tri[2]] ]
                    # And add the triangles to the list
                    # QgsMessageLog.logMessage("%s triangles added for the left" % str(mappedTri) )  
                    triangles.append( mappedTri )


                # We compute the delaunay triangulation for the right side
                arrayRight = list(pointsRight)
                trianglesRight = voronoi.computeDelaunayTriangulation( [voronoi.Site(points[pID].x(), points[pID].y()) for pID in arrayRight] )
                # QgsMessageLog.logMessage("%i triangles computed for the right (%s)" % (len(trianglesRight),trianglesRight))  
                for tri in trianglesRight:
                    # And map the triangles point indices to the actual point indices
                    mappedTri = [ arrayRight[tri[0]],arrayRight[tri[1]],arrayRight[tri[2]] ]
                    # And add the triangles to the list
                    # QgsMessageLog.logMessage("%s triangles added for the right" % str(mappedTri) ) 
                    triangles.append( mappedTri )


    return triangles
