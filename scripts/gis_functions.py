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
