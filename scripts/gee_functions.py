import ee
import json
import geopandas as gpd
import numpy as np
from datetime import timedelta
import pandas as pd
from scripts import gis_functions

ee.Initialize()


def add_vegetation_index(image, vi_name, img_bandnames=None,
                         std_names=None, equation=None):
    img_copy = image.select(img_bandnames, std_names)
    kwargs = None

    if vi_name == "ndvi":
        equation = '(NIR - RED)/(NIR + RED)'
        kwargs = {'RED': img_copy.select('red'),
                  'NIR': img_copy.select('nir')}

    if vi_name == "gndvi":
        equation = '(NIR - GREEN)/(NIR + GREEN)'
        kwargs = {'NIR': img_copy.select('nir'),
                  'GREEN': img_copy.select('green')}

    if vi_name == "lswi":
        equation = '(NIR - SWIR1)/(NIR + SWIR1)'
        kwargs = {'NIR': img_copy.select('nir'),
                  'SWIR1': img_copy.select('swir1')}

    return image.addBands(img_copy.expression(equation, kwargs).rename(vi_name))


def calculate_displacement(eeimage, eeimageref, maxoffset=200, patchwidth=400):
    refimageproj = eeimageref.reproject(crs=eeimage.projection())

    displacement = eeimage.displacement(referenceImage=refimageproj,
                                        maxOffset=maxoffset,
                                        patchWidth=patchwidth)
    return displacement


def dates_maxcover(df, limit=80, numdays=20):
    datasummary = df.loc[df.cover_percentage >= limit].reset_index()
    datemin = datemax = None
    if (datasummary.shape[0] > 0):
        datemaxcover = datasummary.dates.iloc[datasummary.cover_percentage.idxmax()]

        datemin = (datemaxcover - timedelta(days=numdays)).strftime("%Y-%m-%d")
        datemax = (datemaxcover + timedelta(days=numdays)).strftime("%Y-%m-%d")

    return [datemin,
            datemax]


def date_listperdays(imgcollection, ndays):
    days = ee.List.sequence(0, ee.Date(ee.Image(imgcollection.sort('system:time_start', False)
                                                .first()).get('system:time_start'))
                            .difference(ee.Date(ee.Image(imgcollection.first())
                                                .get('system:time_start')), 'day'), ndays).map(
        lambda x: ee.Date(ee.Image(imgcollection.first())
                          .get('system:time_start')).advance(x, "day"))

    return days.slice(0, -1).zip(days.slice(1))


### ee geometry
def geometry_as_ee(filename):
    """transform shapefile format to ee geometry"""
    ### read csv file
    if (type(filename) == str):
        sp_geometry = gpd.read_file(filename)
        ## reproject spatial data
        if str(gpd.__version__) == "0.6.2":
            if sp_geometry.crs[[*sp_geometry.crs][0]] != 'epsg:4326':
                sp_geometry = sp_geometry.to_crs('epsg:4326')
        #
        else:
            if sp_geometry.crs != 'epsg:4326':
                sp_geometry = sp_geometry.to_crs('epsg:4326')

    if type(filename) == gpd.geodataframe.GeoDataFrame:
        sp_geometry = filename

    ## get geometry points in json format
    jsonFormat = json.loads(sp_geometry.to_json())['features'][0]['geometry']

    return ee.Geometry.Polygon(jsonFormat['coordinates'])


def getfeature_fromeedict(eecollection, attribute, featname):
    """get image collection properties"""
    aux = []
    for feature in range(len(eecollection['features'])):
        ## get data from the dictionary
        datadict = eecollection['features'][feature][attribute][featname]
        ## check if it has info
        aux.append(datadict)
    return (aux)

def get_band_timeseries_summary(gee_satellite_class, vi_name):
    """get a band time series summary using a single point"""

    if np.logical_not(np.isnan(gee_satellite_class._querypoint[0])):
        ee_point = coords_togeepoint(gee_satellite_class._querypoint, 100)

        meanDictionary = gee_satellite_class.image_collection.map(lambda img:
                                           reduce_tosingle_columns(img.select([vi_name]),
                                                                                 ee_point)).flatten()

        band_data = fromeedict_totimeseriesfeatures(meanDictionary.getInfo(), 'mean')
        band_data.columns = ['date', vi_name]
        ## filtering na values
        band_data = band_data.loc[np.logical_not(band_data[vi_name].isnull())]
        
        return (band_data)
    else:
        return print('this function only works using a query point so far')


def get_eeimagecover_percentage(eeimage, eegeometry):
    imagewithdata = eeimage.clip(eegeometry).select(0).gt(ee.Number(-100))
    imagewithdatamasked = eeimage.clip(eegeometry).select(0).updateMask(imagewithdata)
    area = imagewithdatamasked.pixelArea()

    pixelareavalue = imagewithdata.multiply(area).reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=eegeometry,
        scale=100
    )

    ### calculate percentage using the geometry
    polarea = eegeometry.area()

    ## calculate image cover area
    areavaluelocal = ee.Number(pixelareavalue.get(ee.Image(eeimage).bandNames().get(0)))

    return areavaluelocal.divide(polarea).multiply(ee.Number(100))


def get_eeurl(imagecollection, geometry, scale=10):
    """get url for an individual image"""
    imagesurls = []

    listimages = imagecollection.toList(imagecollection.size());

    for i in range(imagecollection.size().getInfo()):
        try:
            imagesurls.append(ee.Image(listimages.get(ee.Number(i))).getDownloadUrl({
                'scale': scale,  # for resolution of image
                'crs': 'EPSG:4326',  # which crs-transformation should apply
                'region': geometry  # polygon region
            }))
        except:
            imagesurls.append(ee.Image(listimages.get(ee.Number(i))).getDownloadUrl({
                'scale': scale,  # for resolution of image
                'crs': 'EPSG:4326',  # which crs-transformation should apply
                'region': geometry  # polygon region
            }))
    return imagesurls


def query_image_collection(initdate, enddate, satellite_mission, ee_sp):
    """mission data query"""

    ## mission data query
    return ee.ImageCollection(satellite_mission).filterDate(initdate, enddate).filterBounds(ee_sp)


def LatLonImg(img, geometry, scale):
    img = img.addBands(ee.Image.pixelLonLat())

    img = img.reduceRegion(reducer=ee.Reducer.toList(), geometry=geometry, maxPixels=1e13, scale=scale)

    data = np.array((ee.Array(img.get("result")).getInfo()))
    lats = np.array((ee.Array(img.get("latitude")).getInfo()))
    lons = np.array((ee.Array(img.get("longitude")).getInfo()))
    return lats, lons, data


def reduce_meanimagesbydates(satcollection, date_init, date_end):
    # imagesfiltered = ee.ImageCollection(satcollection.filterDate(date_init, date_end))

    # datefirst_image = ee.Number(ee.Image(satcollection.filterDate(date_init, date_end).first().get('system:time_start')))
    outputimage = ee.Image(satcollection.filterDate(date_init, date_end).mean())

    return outputimage

def reduce_imgs_by_days(image_collection, days):
    dates = date_listperdays(image_collection, days)
    datelist = ee.List.sequence(0, ee.Number(dates.size().subtract(ee.Number(1))))
    return datelist.map(lambda n:
                        reduce_meanimagesbydates(image_collection,
                                                 ee.List(dates.get(ee.Number(n))).get(0),
                                                 ee.List(dates.get(ee.Number(n))).get(1)))


def select_imagesfromcollection(image_collection, indexes):
    """Reduce image collection using indexes as reference"""

    eelistimages = image_collection.toList(image_collection.size())
    imageslist = []

    for eeimageindex in indexes:
        imageslist.append(eelistimages.get(int(eeimageindex)))

    return ee.ImageCollection(ee.List(imageslist))


def coords_togeepoint(point_coordinates, buffer):
    """transforming from was84 coordnates to gee points"""
    return ee.Geometry.Point(point_coordinates[0], point_coordinates[1]).buffer(buffer);

    return None


def reduce_tosingle_columns(image, region):
    mean = image.reduceRegions(region, 'mean', 10);

    return mean.map(lambda f:
                    f.set('date', ee.Date(image.get('system:time_start')).
                          format('YYYY-MM-dd'))
                    )


def fromeedict_totimeseriesfeatures(ee_dict, featurename):
    dates = []
    feature_values = []
    for i in range(len(ee_dict['features'])):
        dates.append(ee_dict['features'][i]['properties']['date'])
        if len(ee_dict['features'][i]['properties']) > 1:
            feature_values.append(ee_dict['features'][i]['properties'][featurename])
        else:
            feature_values.append(np.nan)

    return pd.DataFrame({'date': dates, featurename: feature_values})