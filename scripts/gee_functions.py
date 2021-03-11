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
    imgcollection = imgcollection.sort('system:time_start', True)
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
    ### read csv fileget_band_timeseries_summary
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
    if len(json.loads(sp_geometry.to_json())['features']) > 1:
        jsoncoordinates = define_wrap_box(json.loads(sp_geometry.to_json())['features'])
        output = [ee.Geometry.Polygon(jsoncoordinates),
                  [[ee.Geometry.Polygon(json.loads(sp_geometry.to_json()
                                                  )['features'][i]['geometry']['coordinates'])
                   for i in range(len(json.loads(sp_geometry.to_json())['features']))],
                   [json.loads(sp_geometry.to_json())['features'][i]['properties']
                       for i in range(len(json.loads(sp_geometry.to_json())['features']))]
                  ]]

    else:
        jsoncoordinates = json.loads(sp_geometry.to_json()
                                     )['features'][0]['geometry']['coordinates']
        output = [ee.Geometry.Polygon(jsoncoordinates)]

    return output


def define_wrap_box(json_coordinates):
    lonmins = []
    longmax = []
    latmin = []
    latmax = []
    for i in range(len(json_coordinates)):
        boundbox = json_coordinates[i]['geometry']['coordinates']
        lonmins.append(np.array(boundbox).T[0].min())
        longmax.append(np.array(boundbox).T[0].max())
        latmin.append(np.array(boundbox).T[1].min())
        latmax.append(np.array(boundbox).T[1].max())

    return [[[np.array(longmax).max(), np.array(latmin).min()],
             [np.array(longmax).max(), np.array(latmax).max()],
             [np.array(lonmins).min(), np.array(latmax).max()],
             [np.array(lonmins).min(), np.array(latmin).min()]]]


def getfeature_fromeedict(eecollection, attribute, featname):
    """get image collection properties"""
    aux = []
    for feature in range(len(eecollection['features'])):
        ## get data from the dictionary
        datadict = eecollection['features'][feature][attribute][featname]
        ## check if it has info
        aux.append(datadict)
    return (aux)


def reduceregion_totable(geedataclass, band, eegeom):
    """ Reduce data to region  """

    if type(band) is list:
        meanDictionary = geedataclass.image_collection.map(lambda img:
                                                           reduce_tosingle_columns(img.select(band),
                                                                                   eegeom)).flatten()
        band_data = fromeedict_totimeseriesfeatures(meanDictionary.getInfo(), band)
        #band_data.columns = ['date', band]
        band_data = band_data.loc[np.logical_not(band_data[band[0]].isnull())]

    else:
        meanDictionary = geedataclass.image_collection.map(lambda img:
                                                       reduce_tosingle_columns(img.select([band]),
                                                                               eegeom)).flatten()
        band_data = fromeedict_totimeseriesfeatures(meanDictionary.getInfo(), 'mean')
        band_data.columns = ['date', band]

        ## filtering na values
        band_data = band_data.loc[np.logical_not(band_data[band].isnull())]
    return band_data


def get_band_timeseries_summary(gee_satellite_class, vi_name, buffer=100):
    """get a band time series summary using a single point"""
    band_data = np.nan

    if np.logical_not(np.isnan(gee_satellite_class._querypoint[0])):
        ee_point = coords_togeepoint(gee_satellite_class._querypoint, buffer)
        band_data = reduceregion_totable(gee_satellite_class, vi_name,
                                         ee_point)

    elif len(gee_satellite_class._multiple_polygons)==1:
        band_data = reduceregion_totable(gee_satellite_class, vi_name,
                                         gee_satellite_class._ee_sp)

    elif len(gee_satellite_class._multiple_polygons)==2:
        polygons = gee_satellite_class._multiple_polygons[0]

        features = gee_satellite_class._multiple_polygons[1]
        outtables = []
        for i in range(len(polygons)):

            outtable = reduceregion_totable(gee_satellite_class, vi_name,
                                             polygons[i])
            outtable['properties'] = str(features[i])
            outtables.append(outtable)
        band_data= pd.concat(outtables)

    else:
        return print('this function only works using a query point so far')

    return band_data


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


def LatLonImg(img, geometry, scale):
    img = img.addBands(ee.Image.pixelLonLat())

    img = img.reduceRegion(reducer=ee.Reducer.toList(), geometry=geometry, maxPixels=1e13, scale=scale)

    data = np.array((ee.Array(img.get("result")).getInfo()))
    lats = np.array((ee.Array(img.get("latitude")).getInfo()))
    lons = np.array((ee.Array(img.get("longitude")).getInfo()))
    return lats, lons, data


def query_image_collection(initdate, enddate, satellite_mission, ee_sp):
    """mission data query"""

    ## mission data query
    return ee.ImageCollection(satellite_mission).filterDate(initdate, enddate).filterBounds(ee_sp)


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
            if type(featurename) is list:
                values = []
                for j in featurename:
                    val = ee_dict['features'][i]['properties'][j]

                    values.append(val)
                tempdf = pd.DataFrame(values).transpose()
                tempdf.columns = featurename
                # print(tempdf)
                feature_values.append(values)

            else:
                feature_values.append(ee_dict['features'][i]['properties'][featurename])

        else:
            if type(featurename) is list:
                feature_values.append([np.nan for i in range(len(featurename))])
            else:
                feature_values.append(np.nan)
    if type(featurename) is list:

        df_band_values = pd.DataFrame(np.array(feature_values), columns=featurename)
        df_band_values['date'] = dates

    else:
        df_band_values = pd.DataFrame({'date': dates, featurename: feature_values})

    return df_band_values


def filtering_bycoverpercentage(geedata_class, cover_percentage=95):
    imgcollection = geedata_class.image_collection
    dates = geedata_class.dates
    orig_date_size = len(dates)
    collsummary = geedata_class.summary.copy()
    listofindexes = collsummary.loc[collsummary.cover_percentage > cover_percentage].index.values
    #dates = dates.loc[collsummary.cover_percentage > cover_percentage]
    imgcollection = select_imagesfromcollection(imgcollection, listofindexes)
    ### TODO: image indexes distributed across time
    print("total images: {} \ntotal images after cover filter: {}".format(orig_date_size, len(listofindexes)))

    return imgcollection

########## IMAGE SEGMENTATION


def gee_snic(imgcollection, gee_geometry,
             bands = ["B4", "B8"],
             seeds=16,
             snic_kwargs={
                 'size': 8,
                 'compactness': 3,
                 'connectivity': 8,
                 'neighborhoodSize': 128
             }):
    # bansaftersnic = [i+'_mean' for i in bands]
    # bansaftersnic.append('clusters')

    seeds = ee.Algorithms.Image.Segmentation.seedGrid(seeds)

    snic = ee.Algorithms.Image.Segmentation.SNIC(
        image=imgcollection.select(bands).median().clip(gee_geometry),
        size=snic_kwargs['size'],
        compactness=snic_kwargs['compactness'],
        connectivity=snic_kwargs['connectivity'],
        neighborhoodSize=snic_kwargs['neighborhoodSize'],
        seeds=seeds
    )

    # .select(bansaftersnic, bands.append('clusters'))

    return snic


def raster_to_polygons(gee_snic, gee_image, gee_geometry, scale=8):
    """
    Trasnform an segmented image into polygons
    :param gee_snic: Segmented image ee.Image()
    :param gee_image: a reference image which will be used for polygons metrics ee.Image()
    :param gee_geometry:
    :param scale:
    :return:
    """
    vectors = gee_snic.select('clusters').addBands(
        gee_image).reduceToVectors(
        geometry=gee_geometry,
        crs=gee_snic.projection(),
        scale=scale,
        geometryType='polygon',
        eightConnected=False,
        labelProperty='zone',
        reducer=ee.Reducer.mean(),
        maxPixels=120000000,
        bestEffort=True
    )
    return vectors


def reduce_image_to_superpixel(image, polygons):
    img = ee.Image(image).reduceRegions(polygons, ee.Reducer.mean(), scale=10)
    img = img.reduceToImage(
        properties=['mean'],
        reducer=ee.Reducer.first())
    return img

