# GEE Satellite data
<p align="center">
<img src="https://ciat.cgiar.org/wp-content/uploads/Alliance_logo.png" alt="CIAT" id="logo" data-height-percentage="90" data-actual-width="140" data-actual-height="55">
<img src="images/CCAFS.png" alt="CCAFS" id="logo2" data-height-percentage="90" width="230" height="52">
</p>


## 1. Introduction

Crops are exposed to several factors that affect their profitability. High production cost, fluctuation in prices, climate change, disease outbreaks, and overproduction are some of the challenges that growers must face. For that reason, it is important to have initiatives that leverage farmers' production conditions. In this sense, crop data is valuable to bring farmers support at the moment to make decisions on their agronomical practices. Besides crop mapping provides a basic regional context useful for production plannig. Due to the relevance of getting data about crop development, many efforts have been carried out to get accurate and timely information. One of the most common methods is through surveys. Regardless of its high accuracy, this methodology is time-consuming and hard to implement on a large scale. For that reason, new sources of information are required to obtain high-frequency data at a low cost. 

During the last decade, several studies have successfully proved the remote sensing capability on monitoring vegetation, creating valuable data for characterizing crop conditions.


## 2. Purpose

The purpose of this repository is to provide alternatives for easy satellite missions data access throughout google earth engine project.

This repository was created for downloading and processing satellite data. The required inputs are the path, in which contains a vector file in ESRI-Shapefile format for the region of interest, and the satellite mission index. 

## 3. Usage

* **Step 1:** [Sign up](https://earthengine.google.com/signup/) for [Google Earth Engine](https://earthengine.google.com/).
* **Step 2:** Install conda or minicoda.
* **Step 3:** Install the [Google Earth Engine Plugin for python](https://developers.google.com/earth-engine/python_install-conda)
* **Step 4:** Git clone or [download](https://github.com/anaguilarar/gee_satellite_data.git) this repository.

## 4. Requirements

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
Currently, there are four different missions available. 
  * [Sentinel 2 level-2A](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR)
  * [Sentinel 2 level-1C](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2)
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

More examples are shown in following colabs:
* [Download satellite data](https://github.com/anaguilarar/gee_satellite_data/blob/master/Download%20Satellite%20Data.ipynb)
* [Extracting data using spatial features](github.com/anaguilarar/gee_satellite_data/blob/master/examples/query_using_a_single_point.ipynb)
