
import algorithm_voronoi as voronoi

def computeConstrainedDelaunayTriangulation(points, neededSegments):
    """
    This will return a constrained Delaunay triangulation.

    Input
    points: array of QgsPoint
    neededSegments: array of 2uples being the index of the linked points

    Returns a list of 3 uples being the indices of the points forming the triangles
    """

    # We get the normal delaunay triangulation
    triangles = voronoi.computeDelaunayTriangulation( [voronoi.Site(p.x(), p.y()) for p in points] )

    # Now we have to constrain the delaunay triangulation.
    # For each needed segment, we'll delete the intersecting triangles to make room for the constrain, and retriangulate it.

    #for segment in neededSegment:


    return triangles
