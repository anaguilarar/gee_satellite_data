import datetime
import ee
import json
import os
import wget
import pandas as pd
import numpy as np
import geopandas as gpd
from zipfile import ZipFile

from scripts import gee_functions

ee.Initialize()

missions_bands = {
    'sentinel1': ['VV', 'VH']
}


#TODO: Create an imagery directory



class get_gee_data:
    """Download optical and radar data from Google Earth Engine platform.

           the final output will be a pool of images.


           Parameters
           ----------

           start_date : str
                   The start of the time period used for data extraction, it must have the folowing format "YYYY-MM-DD"

           end_date : str
                  The end of the time period used for data extraction., it must have the following format "YYYY-MM-DD"

           roi_filename : str
                   string path to a shape file that must conatains limited the region of interest

           bands : list str
                   a list of bands that are going to be selected for its download

           output_path : str
                   string path to a destination folder

           mission : str
                   id reference to the satellite which will be processed:
                       - Sentinel 2 - surface reflectance level: "sentinel2_sr"
                       - Sentinel 2 - top of atmosphere reflectance: "sentinel2_toa"
                       - Sentinel 1: "sentinel1"
                       - Landsat 8:

           Attributes
           ----------
           products : dict
               Filtered copy of `product_list` passed to the object containing only
               products generated between `start_date` and `end_date`.
           product_boundaries : dict
               Contains `shapely.geometry.Polygon` objects describing the boundaries
               of each of the products in `products`.
    """

    @property
    def dates(self):
        dates = pd.Series(
            gee_functions.getfeature_fromeedict(self.image_collection.getInfo(),
                                                'properties',
                                                'system:time_start')
        )

        return dates.apply(lambda x: datetime.datetime.fromtimestamp(np.round(x / 1000.0)))

    @property
    def orbit(self):
        return pd.Series(gee_functions.getfeature_fromeedict(self.image_collection.getInfo(),
                                                             'properties',
                                                             'orbitProperties_pass'))

    @property
    def length(self):
        return self.image_collection.size().getInfo()

    def _get_dates_afterreduction(self, days):
        dates = date_listperdays(self.image_collection, days)

        refdates = [datetime.datetime.timestamp(datetime.datetime.strptime(str(x), '%Y-%m-%d %H:%M:%S'))
                    for x in self.dates]
        datesreduce = []
        for i in dates.getInfo():
            initref = i[0]['value'] / 1000
            endref = i[1]['value'] / 1000
            datestest = []
            for refdate in refdates:
                if initref <= refdate <= endref:
                    datestest.append(refdate)

            if len(datestest) > 1:
                datesreduce.append(datetime.datetime.fromtimestamp(np.round(np.array(datestest).mean())))
            #elif isinstance(datestest, float):
            #    datesreduce.append(datetime.datetime.fromtimestamp(datestest))
            elif len(datestest) == 1:
                datesreduce.append(datetime.datetime.fromtimestamp(datestest[0]))
        return pd.Series(datesreduce)

    def _poperties_mission(self):

        self._prefix = None
        if self.mission == "sentinel1":
            self._mission = 'COPERNICUS/S1_GRD'
            self._prefix = 's1_grd'

        if self.mission == 'sentinel2_toa':
            self._mission = 'COPERNICUS/S2'
            self._prefix = 's2_l1c'

        if self.mission == 'sentinel2_sr':
            self._mission = 'COPERNICUS/S2_SR'
            self._prefix = 's2_l2a'


    def reduce_by_days(self, days):

        ## remove those elements with null data
        self._imagreducedbydays = ee.ImageCollection(
            reduce_imgs_by_days(self.image_collection, days)).map(lambda image:
                                                                  image.set(
                                                                      'count',
                                                                      ee.Image(
                                                                          image).bandNames().length())
                                                                  ).filter(
            ee.Filter.eq('count', len(self._bands))).map(lambda img:
                                                         img.divide(10).multiply(10)
                                                         )
        self._dates_reduced = self._get_dates_afterreduction(days)
        return self._imagreducedbydays

    def __init__(self, start_date,
                 end_date,
                 roi_filename,
                 mission,
                 bands=None):

        ### set initial properties
        self.mission = mission

        self._dates = [start_date, end_date]
        ## get spatial points
        self._ee_sp = geometry_as_ee(roi_filename)

        if bands is None:
            self._bands = missions_bands[mission]
        else:
            self._bands = bands

        ### mission reference setting
        self._poperties_mission()
        ###
        self.image_collection = query_image_collection(ee.Date(start_date),
                                                       ee.Date(end_date),
                                                       self._mission,
                                                       self._ee_sp).select(self._bands)

        self._imagreducedbydays = None
        self._dates_reduced = None

        if mission == "sentinel1":
            for band in self._bands:
                self.image_collection = self.image_collection.filter(
                    ee.Filter.eq('instrumentMode', 'IW')
                ).filter(
                       ee.Filter.listContains('transmitterReceiverPolarisation', band)
                )


### functions


### ee geometry
def geometry_as_ee(filename):
    '''transform shapefile format to ee geometry'''
    ### read csv file
    sp_geometry = gpd.read_file(filename)
    ## reproject spatial data
    if sp_geometry.crs['init'] != 'epsg:4326':
        sp_geometry = sp_geometry.to_crs({'init': 'epsg:4326'})

    ## get geometry points in json format
    jsonFormat = json.loads(sp_geometry.to_json())['features'][0]['geometry']

    return ee.Geometry.Polygon(jsonFormat['coordinates'])


###

#def mask_noise_s1(image):
#    edge = ee.Image(image).lt(-30.0)
#    maskedImage = ee.Image(image).mask().and(edge.not())
#    return image.updateMask(maskedImage)


def unzip_files(filepath, outputpath):
    with ZipFile(filepath, 'r') as zipObj:
        # Get list of files names in zip
        filesunzipped = zipObj.namelist()
        zipObj.extractall(outputpath)

    return filesunzipped


def get_imageprperties(filename,outputfolder, scale):
    datestr = filename[filename.index('_20') + 1:filename.index('_20') + 9]
    prefixgee = filename[len(outputfolder) + 1:filename.index('_20')]
    regionid = filename[filename.index(datestr) + 9:filename.index(str(scale) + 'm') - 1]
    return [prefixgee, datestr, regionid]

def s1_imagesunzip(zipfilename, outputfolder, imgbands, scale):
    filenamesunzipped = unzip_files(zipfilename + '.zip', outputfolder)
    imgargs = get_imageprperties(zipfilename,outputfolder, scale)
    for bandsindex in range(len(imgbands)):

        filesperband = np.array([x for x in filenamesunzipped if imgbands[bandsindex] in x])
        suffixraster = [x[x.index(imgbands[bandsindex] + '.') + len(imgbands[bandsindex]):] for x in filesperband]

        newnames_perband = []
        for i in range(len(suffixraster)):
            newnames_perband.append(os.path.join(outputfolder,
                                                 '{}_{}_{}_{}_{}m{}'
                                                 .format(imgargs[0], imgbands[bandsindex], imgargs[1], imgargs[2],
                                                         str(scale), suffixraster[i])))

        for j, i in zip(filesperband, newnames_perband):
            os.rename(os.path.join(outputfolder, j), i)

    os.remove(zipfilename + '.zip')


def get_eeurl(imagecollection, geometry, scale=10):
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


def download_gee_tolocal(geedata_class, outputfolder, regionid="", scale=10):
    if isinstance(geedata_class, get_gee_data):

        if geedata_class._imagreducedbydays is None:
            imgcollection = geedata_class.image_collection
            dates = geedata_class.dates
        else:
            imgcollection = geedata_class._imagreducedbydays
            dates = geedata_class._dates_reduced

        ## get urls list from gee
        urls_list = get_eeurl(imgcollection, geedata_class._ee_sp['coordinates'], scale)

        ## change dates format

        dates_str = [datetime.datetime.strptime(str(dates[i]), '%Y-%m-%d %H:%M:%S').strftime("%Y%m%d") for i in
                     range(len(dates))]

        ## donwload each image

        filenames = [os.path.join(outputfolder,
                                  ('{}_{}_{}_{}m').format(geedata_class._prefix, dates_str[i], regionid, str(scale)))
                     for i in range(len(dates_str))]
        for url, filename in zip(urls_list, filenames):
            wget.download(url, filename + '.zip')
            print('the {} file was downloaded'.format(filename))

        if geedata_class.mission == 'sentinel1':
            wrongfiles = []
            for zipfilepath in filenames:

                try:
                    s1_imagesunzip(zipfilepath, outputfolder, geedata_class._bands, scale)
                except:
                    wrongfiles.append(wrongfiles)

        print('these files created a conflict at the moment of its download')



    else:
        print("the input file must be a get_gee_data class")


def query_image_collection(initdate, enddate, satellite_mission, ee_sp):
    '''mission data query'''

    ## mission data query
    return ee.ImageCollection(satellite_mission).filterDate(initdate, enddate).filterBounds(ee_sp)


def reduce_meanimagesbydates(satcollection, date_init, date_end):
    # imagesfiltered = ee.ImageCollection(satcollection.filterDate(date_init, date_end))

    #datefirst_image = ee.Number(ee.Image(satcollection.filterDate(date_init, date_end).first().get('system:time_start')))
    outputimage = ee.Image(satcollection.filterDate(date_init, date_end).mean())

    return outputimage


def date_listperdays(imgcollection, ndays):
    days = ee.List.sequence(0, ee.Date(ee.Image(imgcollection.sort('system:time_start', False)
                                                .first()).get('system:time_start'))
                            .difference(ee.Date(ee.Image(imgcollection.first())
                                                .get('system:time_start')), 'day'), ndays).map(
        lambda x: ee.Date(ee.Image(imgcollection.first())
                          .get('system:time_start')).advance(x, "day"))

    return days.slice(0, -1).zip(days.slice(1))


def reduce_imgs_by_days(image_collection, days):
    dates = date_listperdays(image_collection, days)
    datelist = ee.List.sequence(0, ee.Number(dates.size().subtract(ee.Number(1))))
    return datelist.map(lambda n:
                        reduce_meanimagesbydates(image_collection,
                                                 ee.List(dates.get(ee.Number(n))).get(0),
                                                 ee.List(dates.get(ee.Number(n))).get(1)))


# def download_images(image_list):

def LatLonImg(img, geometry, scale):
    img = img.addBands(ee.Image.pixelLonLat())

    img = img.reduceRegion(reducer=ee.Reducer.toList(), geometry=geometry, maxPixels=1e13, scale=scale)

    data = np.array((ee.Array(img.get("result")).getInfo()))
    lats = np.array((ee.Array(img.get("latitude")).getInfo()))
    lons = np.array((ee.Array(img.get("longitude")).getInfo()))
    return lats, lons, data


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
