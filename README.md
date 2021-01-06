# GEE Satellite data
<p align="center">
<img src="https://ciat.cgiar.org/wp-content/uploads/Alliance_logo.png" alt="CIAT" id="logo" data-height-percentage="90" data-actual-width="140" data-actual-height="55">
</p>

**Contact:** Andrés Aguilar (a.aguilar@cgiar.org)

## 1. Purpose

This repository was created for downloading and processing satellite data. The required inputs are the path, in which contains a vector file in ESRI-Shapefile format for the region of interest, and the satellite mission index. 

## 2. Usage

* **Step 1:** [Sign up](https://earthengine.google.com/signup/) for [Google Earth Engine](https://earthengine.google.com/).
* **Step 2:** Install conda or minicoda.
* **Step 3:** Install the [Google Earth Engine Plugin for python](https://developers.google.com/earth-engine/python_install-conda)
* **Step 4:** Git clone or [download](https://github.com/anaguilarar/gee_satellite_data.git) this repository.

## 3. Requirements

* Python Version >= 3.6
* Libraries:
    *   earthengine-api==0.1.211
    *   pyproj==2.6.1
    *   pandas 
    *   geopandas==0.7.0 
    *   numpy
    *   folium
    *   geehydro
    *   wget
    *   json

## Get started

The following example shows a workflow for querying, previewing and downloading satellite data from Google Earth Engine using Python.
Currently, there are available three different missions. 
  * [Sentinel 2 level-2A](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR)
  * [Sentinel 1 GRD](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S1_GRD)
  * [Landsat 8 surface reflectance](https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LC08_C01_T1_SR)


###  Sentinel - 2 query

The first step is to check how many images suit in the query requirements 

```python
from scripts import gee_satellite_data

sentinel2 = gee_satellite_data.get_gee_data("2019-06-01", ## start date
                                            "2019-09-28", ## end query date
                                            "data/col_t3.shp", ## region of interest
                                            "sentinel2_sr", ## mission
                                            cloud_percentage= 80 ## cloud percetage per image 
                                           )
```
### Visualization

The visualization is done throughout the folium library (please check out the requirements). Once an image of interest was chosen, you must indicate which is the image number that is going to be plot. 

```python
## print a query summary table
print(sentinel2.summary)

## visualization parameters
truecolorParams = {'gamma': 1.3, 
                   'min': 57,
                   'max': 2000,
                   'bands': ['B4','B3','B2']
                   }

imageindex = 9

imagetoplot = sentinel2.image_collection.toList(sentinel2.image_collection.size()).get(imageindex)

gee_satellite_data.plot_eeimage(imagetoplot, truecolorParams, sentinel2.geometry, zoom = 11)

```

### Vegetation indices aggregation

In order to visualice the crop plants vigorosity, the code allows to add a NDVI band. 

```python
### adding a NDVI layer
sentinel2.add_vi_layer("ndvi")

ndviParams = {     'min': 0,
                   'max': 1,
                   'palette': ['#FF0000', '#00FF00'],
                   'bands': ['ndvi']
                   }


imageindex = 9

imagetoplot = sentinel2.image_collection.toList(sentinel2.image_collection.size()).get(imageindex)

gee_satellite_data.plot_eeimage(imagetoplot, 
                                ndviParams, 
                                sentinel2.geometry, 
                                zoom = 11)
```

### Images downloading

Finally, you can download the images by pointing out which is going to be the destination folder path and.

```python
gee_satellite_data.download_gee_tolocal(sentinel2, ## 
                                        'gee_satellitedata/s2_processed', ## outputpath 
                                        "col_t3", ## a suffix reference for the area that was query
                                        10, ## the spatial resolution in meters
                                        bands = ['B2', 'B3', 'B4', 'B8', 'ndvi']
                                       )
```


