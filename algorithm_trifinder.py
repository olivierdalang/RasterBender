# -*- coding: utf-8 -*-

#############################################################################
#
# This defines a Trifinder class, which takes a list of Sites and a list
# of triangles, and allows to find in which triangle a point lies. If the list
# of triangles is omitted, a delaunay triangulation is made.
#
#############################################################################

from qgis.core import *
from qgis.gui import *

class Trifinder(object):
    """Object to find in which triangle a point lies"""

    def __init__(self, sites, triangles=None, boundingBox=None):
        """Constructor

        Args:
            sites: list of points (must have x and y members)
            triangles: list of 3uples with the index of sites that form the triangles
            boundingBox: QgsRectangle, if provided, rectangle that do not intersect with it will be discarded to optimize
        """

        super(Trifinder, self).__init__()
        self.sites = sites
        self.triangles = triangles

        if boundingBox is None:
            self.triangles = triangles
        else:
            self.triangles = []
            for tri in triangles:
                if Trifinder.triangleRectangleOverlap( boundingBox, self.sites[tri[0]], self.sites[tri[1]], self.sites[tri[2]] ):
                    self.triangles.append(tri)

        self.lastIndex = None

    def find(self, site):
        #we start by searching the last triangle since it's very possible that it's the same
        if self.lastIndex is not None:
            lastTri = self.triangles[ self.lastIndex ]
            if Trifinder.pointInTriangle( site, self.sites[lastTri[0]], self.sites[lastTri[1]], self.sites[lastTri[2]] ):
                return self.triangles[self.lastIndex]

        for i,tri in enumerate(self.triangles):
            if Trifinder.pointInTriangle( site, self.sites[tri[0]], self.sites[tri[1]], self.sites[tri[2]] ):
                self.lastIndex = i
                return self.triangles[i]
        self.lastIndex = None
        return None

    @staticmethod
    def sign(p1, p2, p3):
        return (p1.x() - p3.x()) * (p2.y() - p3.y()) - (p2.x() - p3.x()) * (p1.y() - p3.y())
    @staticmethod
    def pointInTriangle(pt, v1, v2, v3):
        b1 = Trifinder.sign(pt, v1, v2) < 0.0
        b2 = Trifinder.sign(pt, v2, v3) < 0.0
        b3 = Trifinder.sign(pt, v3, v1) < 0.0
        return ((b1 == b2) and (b2 == b3))    
    @staticmethod
    def triangleRectangleOverlap(r, t1, t2, t3):
        return QgsGeometry.fromPolygon( [ [ t1,t2,t3 ] ] ).intersects( r )