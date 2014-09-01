
from qgis.core import *

def map(p, a1, a2, a3, b1, b2, b3):
    """Applies transformation from triangle A to B to point P"""
    cT = fromCartesianToTriangular( p, a1, a2, a3  )
    cC = fromTriangularToCartesian( cT, b1, b2, b3  )
    return cC

def fromCartesianToTriangular(p, t1, t2, t3):
    """ Returns triangular coordinates (l1, l2, l3) for a given point in a given triangle """
    """ p is a duplet for cartesian coordinates coordinates """
    x,y = p
    x1,y1 = t1.x(),t1.y()
    x2,y2 = t2.x(),t2.y()
    x3,y3 = t3.x(),t3.y()
    l1 = ((y2-y3)*(x-x3)+(x3-x2)*(y-y3))/((y2-y3)*(x1-x3)+(x3-x2)*(y1-y3))
    l2 = ((y3-y1)*(x-x3)+(x1-x3)*(y-y3))/((y2-y3)*(x1-x3)+(x3-x2)*(y1-y3))
    l3 = 1-l1-l2
    return (l1,l2,l3)

def fromTriangularToCartesian(l,t1,t2,t3):
    """ l is a triplet for barycentric coordinates """
    x = l[0]*t1.x()+l[1]*t2.x()+l[2]*t3.x()
    y = l[0]*t1.y()+l[1]*t2.y()+l[2]*t3.y()
    return QgsPoint(x,y)