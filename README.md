# GEE Satellite data

## Purpose

This repository was created for downloading and processing satellite data. The required inputs are the path, in which contains a vector file in ESRI-Shapefile format for the region of interest, and the satellite mission index.
<br/>
The code uses google earth engine API, for that reason, it is advisable to follow the GEE documentation for users registry and their respective authentication (https://developers.google.com/earth-engine/python_install-conda).
### Requirements

* Python Version >= 3.6

* Modules:
    *   earthengine-api 0.1.211
    *   pyproj > 2.6.1
    *   pandas 
    *   geopandas 0.7.0 
    *   numpy
    *   folium
    *   geehydro
    *   wget
    *   json


## how to use?

Please refers to the jupyter notebook example Download Satellite Data. 