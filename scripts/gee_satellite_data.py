import datetime
import ee
import collections
import os
import wget
import pandas as pd
import numpy as np
import warnings
import folium
import geehydro

from datetime import timedelta
from scripts import gee_functions
from scripts import gis_functions
from scripts import general_functions
from scripts import l8_functions

warnings.simplefilter(action='ignore', category=FutureWarning)

ee.Initialize()

missions_bands = {
    'sentinel1': ['VV', 'VH'],
    'landsat8_t1sr': ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B10', 'B11', 'sr_aerosol', 'pixel_qa', 'radsat_qa'],
    'sentinel2_sr': ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A','B9', 'B11', 'B12',
                    'QA60', 'MSK_CLDPRB', "SCL"]
}

landsat_stdnames = {
    'B1': 'coastal', 'B2': 'blue', 'B3': 'green', 'B4': 'red', 'B5': 'nir', 'B10': 'swir1', 'B11': 'swir2',
    'pixel_qa': 'pixel_qa', 'radsat_qa': 'qa_class'
}

s2_stdnames = {
    'B1': 'coastal', 'B2': 'blue', 'B3': 'green', 'B4': 'red',
    'B5': 'rededge1', 'B6': 'rededge2', 'B7': 'rededge3', 'B8': 'nir',
    'B8A': 'nir2', 'B9': 'water_vapour', 'B11': 'swir1', 'B12': 'swir2',
    'MSK_CLDPRB': 'pixel_qa', 'SCL': 'qa_class'
}

# TODO: Create an imagery directory
#    :


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
                       - Landsat 8: "landsat8_t1sr"

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

    @property
    def geometry(self):
        return self._ee_sp.getInfo()['coordinates'][0]

    @property
    def summary(self):
        return pd.DataFrame({'dates': self.dates,
                             'cover_percentage': self.coverarea})

    @property
    def coverarea(self):

        coverareas = pd.Series(
            gee_functions.getfeature_fromeedict(self.image_collection.getInfo(),
                                                'properties',
                                                'cover_percentage')
        )

        return coverareas

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
            # elif isinstance(datestest, float):
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
        if self.mission == 'landsat8_t1sr':
            self._mission = 'LANDSAT/LC08/C01/T1_SR'
            self._prefix = 'l8_t1sr'

    def _set_coverpercentageasproperty(self):

        self.image_collection = self.image_collection.map(lambda img:
                                                          img.set('cover_percentage',
                                                                  gee_functions.get_eeimagecover_percentage(img,
                                                                                                            self._ee_sp)))

    def check_duplicated_tiles(self):

        ## take the dates from filenames

        dates_str_format = [date_i.strftime('%Y%m%d') for date_i in self.dates]
        dates_duplicated = []
        ## compare number of elements
        if (len(dates_str_format) != len(set(dates_str_format))):
            dates_duplicated = [item for item, count in collections.Counter(dates_str_format).items() if count > 1]
            dates_noduplicate =[item for item, count in collections.Counter(dates_str_format).items() if count == 1]
        else:
            dates_noduplicate = dates_str_format
        return [len(dates_str_format) != len(set(dates_str_format)), dates_duplicated,dates_noduplicate]

    def l8_displacement(self, initdate = '2018-01-01', enddate ='2018-12-31'):

        dfsum = self.summary.copy()
        s2imgdatmin, s2imgdatmax, idl8 = l8_functions.getS2_comparable_image(dfsum, self.geometry)

        newdateinit = initdate
        newdateend = enddate
        landsatimage = ee.Image(
            self.image_collection.toList(self.image_collection.size()).get(ee.Number(int(idl8))))
        landsatimage = landsatimage.clip(self._ee_sp)

        if s2imgdatmax is not None:

            gets2ref = get_gee_data(s2imgdatmin,
                                    s2imgdatmax,
                                    gis_functions.polygon_fromgeometry(self.geometry),
                                    "sentinel2_sr",
                                    cloud_percentage=80)

            s2refimage = ee.Image(gets2ref.image_collection.first()).clip(self._ee_sp)

            displacement = gee_functions.calculate_displacement(landsatimage.select('B5'), s2refimage.select('B8'))

            pixelvalue = displacement.select('dx').hypot(displacement.select('dy')).reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=self._ee_sp,
                scale=100
            )
            avgdisplacement = pixelvalue.get(ee.Image(displacement).bandNames().get(0)).getInfo()
            if(avgdisplacement == 0):
                s2imgdatmax = None

        ## for those cases where it was not possible to find a sentinel surface reflectance image reference
        ## the process is repeated but with a broadly query
        while s2imgdatmax is None:
            landsat2 = get_gee_data(newdateinit,
                                                       newdateend,
                                                       gis_functions.polygon_fromgeometry(self.geometry),
                                                       "landsat8_t1sr",
                                                       cloud_percentage=80)

            dfsum = landsat2.summary.copy()
            s2imgdatmin, s2imgdatmax, idl8 = l8_functions.getS2_comparable_image(dfsum, landsat2.geometry)

            newdateinit = (landsat2.dates[0] + timedelta(days=360)).strftime("%Y-%m-%d")
            newdateend = (landsat2.dates[0] + timedelta(days=720)).strftime("%Y-%m-%d")

            landsatimage = ee.Image(
                landsat2.image_collection.toList(landsat2.image_collection.size()).get(ee.Number(int(idl8))))
            landsatimage = landsatimage.clip(self._ee_sp)

        print('the S2 image reference was found in ' + s2imgdatmin)

        gets2ref = get_gee_data(s2imgdatmin,
                                                   s2imgdatmax,
                                                   gis_functions.polygon_fromgeometry(self.geometry),
                                                   "sentinel2_sr",
                                                   cloud_percentage=80)
        s2refimage = ee.Image(gets2ref.image_collection.first()).clip(self._ee_sp)

        displacement = gee_functions.calculate_displacement(landsatimage.select('B5'), s2refimage.select('B8'))



        return [displacement, s2refimage, landsatimage]

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

    def reduce_duplicatedates(self):
        reducedimages = []
        for dateindex in range(len(self._checkmultyple_tiles[1])):
            ## get indexes from summary
            indexesdup = list(self.summary.loc[self.summary.dates.apply(
                lambda x: x.strftime("%Y%m%d")) ==
                                                   self._checkmultyple_tiles[1][dateindex]].index)

            imageslist = []

            ## image reduction
            # get collection
            for eeimageindex in indexesdup:
                imageslist.append(self.image_collection.toList(self.image_collection.size()).get(eeimageindex))

            bandnames = ee.Image(
                self.image_collection.toList(self.image_collection.size()).get(eeimageindex)).bandNames()

            imagereduced = ee.ImageCollection(ee.List(imageslist)).reduce(ee.Reducer.mean())
            imagereduced = imagereduced.select(imagereduced.bandNames(), bandnames)

            ## set properties
            datetoimage = datetime.datetime.timestamp(
                datetime.datetime.strptime(str(self._checkmultyple_tiles[1][dateindex]), '%Y%m%d'))*1000
            reducedimages.append(imagereduced.set('system:time_start', ee.Number(datetoimage)))

        for dateindex in range(len(self._checkmultyple_tiles[2])):
            indexesdup = list(self.summary.loc[self.summary.dates.apply(
                lambda x: x.strftime("%Y%m%d")) ==
                                                   self._checkmultyple_tiles[2][dateindex]].index)

            reducedimages.append(self.image_collection.toList(self.image_collection.size()).get(indexesdup[0]))

        imagecollection = ee.ImageCollection(ee.List(reducedimages)).sort('system:time_start')
        return imagecollection
        

    def __init__(self, start_date,
                 end_date,
                 roi_filename,
                 mission,
                 bands=None,
                 cloud_percentage=100,
                 remove_clouds=True):

        ### set initial properties
        self.mission = mission

        self._dates = [start_date, end_date]
        ## get spatial points
        self._ee_sp = gee_functions.geometry_as_ee(roi_filename)

        self._bands = missions_bands[mission]

        ### mission reference setting
        self._poperties_mission()
        ###
        self.image_collection = gee_functions.query_image_collection(ee.Date(start_date),
                                                                     ee.Date(end_date),
                                                                     self._mission,
                                                                     self._ee_sp)

        self._imagreducedbydays = None
        self._dates_reduced = None

        if mission == "sentinel1":
            if bands is not None:
                self._bands = bands

            for band in self._bands:
                self.image_collection = self.image_collection.filter(
                    ee.Filter.eq('instrumentMode', 'IW')
                ).filter(
                    ee.Filter.listContains('transmitterReceiverPolarisation', band)
                )

        if mission == "landsat8_t1sr":
            self.image_collection = self.image_collection.select(self._bands).filterMetadata('CLOUD_COVER', 'less_than',
                                                                                             cloud_percentage)
            if remove_clouds is True:
                self.image_collection = self.image_collection.map(
                    lambda img: l8_functions.maskL8sr(img))

            if bands is not None:
                self._bands = bands
                self.image_collection = self.image_collection.select(self._bands).map(
                    lambda image:
                    image.resample('bilinear')
                )


        if mission == "sentinel2_sr":
            self.image_collection = self.image_collection.select(self._bands).filterMetadata('CLOUDY_PIXEL_PERCENTAGE', 'less_than',
                                                                                             cloud_percentage)
            if remove_clouds is True:
                self.image_collection = self.image_collection.map(
                    lambda img: maskS2sr(img))

            if bands is not None:
                self._bands = bands


        self._set_coverpercentageasproperty()

        self._checkmultyple_tiles = self.check_duplicated_tiles()
        if self._checkmultyple_tiles[0] == True and (mission == "sentinel2_sr" or mission == "landsat8_t1sr"):
            self.image_collection = self.reduce_duplicatedates()
            self._set_coverpercentageasproperty()

    @orbit.setter
    def orbit(self, value):
        self._orbit = value


### functions


###

# def mask_noise_s1(image):
#    edge = ee.Image(image).lt(-30.0)
#    maskedImage = ee.Image(image).mask().and(edge.not())
#    return image.updateMask(maskedImage)


def add_normalized_vegetation_indexes(image, bands, viname):
    return image.addBands(
        image.normalizedDifference([bands[0], bands[1]]).rename(viname))


def get_imageprperties(filename, outputfolder, scale):
    datestr = filename[filename.index('_20') + 1:filename.index('_20') + 9]
    prefixgee = filename[len(outputfolder) + 1:filename.index('_20')]
    regionid = filename[filename.index(datestr) + 9:filename.index(str(scale) + 'm') - 1]
    return [prefixgee, datestr, regionid]


def s1_imagesunzip(zipfilename, outputfolder, imgbands, scale):
    filenamesunzipped = general_functions.unzip_files(zipfilename + '.zip', outputfolder)
    imgargs = get_imageprperties(zipfilename, outputfolder, scale)
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


def download_gee_tolocal(geedata_class, outputfolder, regionid="", scale=10):
    if isinstance(geedata_class, get_gee_data):

        if geedata_class._imagreducedbydays is None:
            imgcollection = geedata_class.image_collection
            dates = geedata_class.dates
        else:
            imgcollection = geedata_class._imagreducedbydays
            dates = geedata_class._dates_reduced

        ## get urls list from gee
        urls_list = gee_functions.get_eeurl(imgcollection, geedata_class._ee_sp['coordinates'], scale)

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


def reduce_meanimagesbydates(satcollection, date_init, date_end):
    # imagesfiltered = ee.ImageCollection(satcollection.filterDate(date_init, date_end))

    # datefirst_image = ee.Number(ee.Image(satcollection.filterDate(date_init, date_end).first().get('system:time_start')))
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


def plot_eeimage(imagetoplot, visparameters=None, geometry=None, zoom=9.5):
    ## get the map center coordinates from the geometry
    centergeometry = gis_functions.geometry_center(geometry)
    Map = folium.Map(location=[centergeometry[1],
                               centergeometry[0]], zoom_start=zoom)

    if visparameters is not None:
        Map.addLayer(ee.Image(imagetoplot), visparameters, 'gee image')
    else:
        Map.addLayer(ee.Image(imagetoplot), {}, 'gee image')

    ## add geometry
    if geometry is not None:
        eegeom = gis_functions.polygon_fromgeometry(geometry)
        eegeom = gee_functions.geometry_as_ee(eegeom)
        Map.addLayer(ee.Image().paint(eegeom, 1, 3), {}, 'region of interest:')

    Map.setControlVisibility(layerControl=True, fullscreenControl=True, latLngPopup=True)
    return (Map)


# def download_images(image_list):


def maskS2sr(image):
    # Bits 10 and 11 are clouds and cirrus, respectively.
    cloudBitMask = ee.Number(2).pow(10).int()
    cirrusBitMask = ee.Number(2).pow(11).int()
    qa = image.select('QA60')
    mask0 = qa.bitwiseAnd(cloudBitMask).eq(0)
    mask1 = qa.bitwiseAnd(cirrusBitMask).eq(0)
    ## filtering using the scene layer classification
    scl = image.select('SCL')
    masknodata = scl.eq(0)
    maskshadow = scl.eq(3)
    maskclouds = scl.gte(8)
    imageaftermask0 = ee.Image(image).updateMask(mask0)
    imageaftermaskshadow = imageaftermask0.mask(maskshadow.eq(0))
    imageafterclouds = imageaftermaskshadow.mask(maskclouds.eq(0))

    return imageafterclouds.updateMask(mask1)

def merge_eeimages(eelist, bandnames):

    meannames = [i + "_mean" for i in bandnames]
    return ee.ImageCollection(eelist).reduce(ee.Reducer.mean()).select(meannames, bandnames)



