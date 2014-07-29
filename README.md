# ![create pairs layers](resources/icon.png) ![create pairs layers](resources/icon.png) ![create pairs layers](resources/icon.png) RasterBender ![create pairs layers](resources/icon.png) ![create pairs layers](resources/icon.png) ![create pairs layers](resources/icon.png)

RasterBender is an __EXPERIMENTAL__ QGIS Python plugin allowing to transform vector layers to match another geometry. Depening on the number of input points defined, the plugin chooses on of the three transformation types : translation, uniform, or bending.

The first two allow for quick alignement of non georeferenced data, where as the third allows to match data that has complex non-uniform and non-linear deformations (historical maps, hand drawn sketches, poorly digitized layers...). 

[Have a look at version 0.1 presentation video !](https://vimeo.com/96142479)


## How to use

Launch RasterBender from the plugins menu or from the plugin toolbar.

RasterBender works a bit like the georeferencer : you have to create pairs of points, the first one being the original location, and the second one being the target location.

To do so, RasterBender uses plain Linestring layers. Each pair is defined by the starting point and ending point of a Line in this layer.
You can either use one of your own Linestring layers, or use the ![create pairs layers](resources/mActionCaptureLine.png) button from the RasterBender window.

If you use RasterBender's layers, I recommend installing the "Save memory layer" plugin which will allow to save your work.

Depending on the number of created (or selected, if you choose "restrict to selection") pairs, one of the three methods (explained below) will be used.

Checking the "change pairs to pins" checkbox will transform every inputted pair into a pin, allowing to work in an incremental way very efficiently.

Once the layer to bend and the pairs layer are chosen, simply hit "run", and voilà ! the layer is modified.
You can still undo / revert the changes if you like.


### Translation (exactly 1 pair defined/seleced)

The vector layer will simply be offsetted according to the pair of points.

### Uniform (exactly 2 pairs defined/seleced)

The vector layer will be translated, scaled (uniformly), and rotated so that both pairs match

### Bending (3 or more pairs defined/selected)

The first points of all pairs will be triangulated, and this triangulation will be mapped on the last points of all pairs. The vector layer will then be deformed by matching the triangulation.

The "buffer" parameters sets a buffer around the triangulation, so that the transformation ends more smoothely on the edges. Hold the "preview" button to see the size of the buffer.

Using this method will __INDUCE DEFORMATIONS__. You should __ONLY__ use it if your data is already deformed, and not to accomplish CRS transformations nor linear/affine transformations.


### Bending transformation unavailable because you miss dependencies ?!

This plusing relies on matplotlib 1.3.0, which itself relies on other libraries. Unfortunately, it seems OSGeo4W installs old version of them, at least under windows, which prevents from using the bending transformation type.

On my setup (windows, QGIS-dev 2.3), I had to install those packages (for python 2.7) manually :
- matplotlib 1.3.1 : http://matplotlib.org/downloads.html
- pyparsing 1.5.6 : http://sourceforge.net/projects/pyparsing/files/pyparsing/pyparsing-1.5.6/
- numpy 1.8.1 : http://sourceforge.net/projects/numpy/files/NumPy/

Please send me an email me if you encoutered this problem and solved it in an easier way or for another setup, so I can update this readme.


## Feedback / Bugs / Contribute

Please report bugs and ideas on the issue tracker : https://github.com/olivierdalang/RasterBender/issues

Or send me some feedback at : olivier.dalang@gmail.com


## Version history

- 2014-05-22 - Version 0.0 : intial release
- 2014-05-25 - Version 0.1 : linear and uniform transformation method, scipy dependency no more needed, better management of pinned points
- 2014-07-17 - Version 0.1.1 : fixed bug due to misspelling


## Roadmap

### Not confirmed

- remove matplotlib dependency


## How it works (internally)

Here's how it works :

Preparing the mesh

1. Get a triangular mesh by doing a Delaunay triangulation of all original input points (starting points of the lines in the Raster Bender layer)
2. Adapt this mesh on the ending points of the lines
3. Get the convex hull of the points, offset it by some factor to have a smooth transition on the borders.

Doing the transformation

1. For each point of the target layer, find in which triangle it lies, and get it's barycentric coordinates in that triangle. apply those barycentric coordinates to the adapted mesh.


