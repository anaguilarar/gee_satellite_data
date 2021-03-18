import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon

def geometry_center(geometry):
    longs = []
    lats = []
    for i in geometry:
        long = i[0]
        lat = i[1]
        longs.append(long)
        lats.append(lat)

    return(np.mean(longs), np.mean(lats))


def polygon_fromgeometry(geometry, crs='epsg:4326'):
    """Get a polygon feature from geometry points.
    Args:
      params: An object containing request parameters with the
          following possible values:
              geometry (list) The geomtry points
              crs (string) the coordinates system code

    Returns:
      The list call results.
    """

    polygon_geom = Polygon(geometry)

    # crs = {'init': crs}
    polygon = gpd.GeoDataFrame(index=[0], crs=crs, geometry=[polygon_geom])
    return polygon


# covert the lat, lon and array into an image
def toImage(lats, lons, data):
    # get the unique coordinates
    uniqueLats = np.unique(lats)
    uniqueLons = np.unique(lons)

    # get number of columns and rows from coordinates
    ncols = len(uniqueLons)
    nrows = len(uniqueLats)

    # create an array with dimensions of image
    arr = np.zeros([nrows, ncols], np.float32)  # -9999

    # fill the array with values
    counter = 0
    for y in range(0, len(arr), 1):
        for x in range(0, len(arr[0]), 1):
            if lats[counter] == uniqueLats[y] and lons[counter] == uniqueLons[x] and counter < len(lats) - 1:
                counter += 1
                arr[len(uniqueLats) - 1 - y, x] = data[counter]  # we start from lower left corner
    return arr


def split_into_tiles(bounding_box, num_cells=2, alpha=0.0000001):
    """
    function that split a geometry into a certain tiles
    :param bounding_box: list that contains long and lat data
    :param num_cells: how many cells
    :param alpha:
    :return:
    """
    ## get limits from bounding box
    lat_start = np.array([i[1] for i in bounding_box]).min()
    lat_end = np.array([i[1] for i in bounding_box]).max()
    lon_start = np.array([i[0] for i in bounding_box]).min()
    lon_end = np.array([i[0] for i in bounding_box]).max()

    lon_edge = (lon_end - lon_start) / num_cells
    lat_edge = (lat_end - lat_start) / num_cells

    # 3) Create the grid
    polys = [];
    polys_line = [];
    lon = lon_start

    while (lon < (lon_end - alpha)):
        x1 = lon
        x2 = lon + lon_edge
        lat = lat_start
        while (lat < (lat_end - alpha)):
            y1 = lat
            y2 = lat + lat_edge
            polys.append([x1, y1, x2, y2])
            lat += lat_edge

        lon += lon_edge

    return polys