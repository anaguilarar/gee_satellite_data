import datetime
import ee
import collections
import os
import wget
import pandas as pd
import numpy as np
import shutil
import warnings
import folium
import geehydro
import time

from datetime import timedelta
from scripts import gee_functions, s2_functions
from scripts import gis_functions
from scripts import general_functions
from scripts import l8_functions

warnings.simplefilter(action='ignore', category=FutureWarning)

ee.Initialize()

missions_bands = {
    'sentinel1': ['VV', 'VH'],
    'landsat8_t1sr': ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B10', 'B11', 'sr_aerosol', 'pixel_qa', 'radsat_qa'],
    'sentinel2_sr': ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A', 'B9', 'B11', 'B12',
                     'QA60', 'MSK_CLDPRB', "SCL"],
    'sentinel2_toa': ['QA60', 'B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A', 'B9', 'B10', 'B11', 'B12']
}

l8_stdnames = {
    'B1': 'coastal', 'B2': 'blue', 'B3': 'green', 'B4': 'red', 'B5': 'nir', 'B10': 'swir1', 'B11': 'swir2',
    'pixel_qa': 'pixel_qa', 'radsat_qa': 'qa_class'
}

s2_stdnames = {
    'B1': 'coastal', 'B2': 'blue', 'B3': 'green', 'B4': 'red',
    'B5': 'rededge1', 'B6': 'rededge2', 'B7': 'rededge3', 'B8': 'nir',
    'B8A': 'nir2', 'B9': 'water_vapour', 'B11': 'swir1', 'B12': 'swir2',
    'MSK_CLDPRB': 'pixel_qa', 'SCL': 'qa_class', 'QA60': 'pixel_qa_2'
}

s2_toa_stdnames = {
    'B1': 'cb', 'B2': 'blue', 'B3': 'green', 'B4': 'red',
    'B5': 're1', 'B6': 're2', 'B7': 're3', 'B8': 'nir',
    'B8A': 're4', 'B9': 'waterVapor', 'B10': 'cirrus', 'B11': 'swir1', 'B12': 'swir2',
    'QA60': 'QA60'
}


### TODO: Create an imagery directory
### TODO: DOWNLOAD DATA AS XARRAY
### TODO: DOWNLOAD DATA AS TIF


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
           dates : dict
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
        dates = gee_functions.date_listperdays(self.image_collection, days)

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

    def add_vi_layer(self, vegetation_index="ndvi"):

        currentbands = ee.Image(self.image_collection.first()).bandNames().getInfo()

        if vegetation_index not in currentbands:
            if self.mission == "sentinel2_sr":
                std_names = [s2_stdnames[i] for i in self._bands]

            if self.mission == "landsat8_t1sr":
                std_names = [l8_stdnames[i] for i in self._bands]

            if self.mission == "sentinel2_toa":
                std_names = [s2_toa_stdnames[i] for i in self._bands]

            self.image_collection = self.image_collection.map(lambda img:
                                                              gee_functions.add_vegetation_index(img, vegetation_index,
                                                                                                 self._bands, std_names)
                                                              )
        else:
            print("{} was already computed, the current bands are {}".format(vegetation_index, currentbands))

    def check_duplicated_tiles(self):

        ## take the dates from filenames

        dates_str_format = [date_i.strftime('%Y%m%d') for date_i in self.dates]
        dates_duplicated = []
        ## compare number of elements
        if (len(dates_str_format) != len(set(dates_str_format))):
            dates_duplicated = [item for item, count in collections.Counter(dates_str_format).items() if count > 1]
            dates_noduplicate = [item for item, count in collections.Counter(dates_str_format).items() if count == 1]
        else:
            dates_noduplicate = dates_str_format
        return [len(dates_str_format) != len(set(dates_str_format)), dates_duplicated, dates_noduplicate]

    def l8_displacement(self, initdate='2018-01-01', enddate='2018-12-31'):

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
                scale=1000
            )
            avgdisplacement = pixelvalue.get(ee.Image(displacement).bandNames().get(0)).getInfo()
            if (avgdisplacement == 0):
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

    def reduce_collection_by_days(self, days):
        """Reduce a collection based on a time window.
        Args:
          params: An object containing request parameters with the
              following possible values:
                  days (integer) size of the time window in days
        Returns:
          image_collection reduced by a time window where their dates and images are the average.
        """

        ## remove those elements with null data
        self._imagreducedbydays = ee.ImageCollection(
            gee_functions.reduce_imgs_by_days(self.image_collection, days)).map(lambda image:
                                                                                image.set(
                                                                                    'count',
                                                                                    ee.Image(
                                                                                        image).bandNames().length())
                                                                                ).filter(
            ee.Filter.eq('count', len(self._bands))).map(lambda img:
                                                         img.divide(10).multiply(10)
                                                         )
        self._dates_reduced = self._get_dates_afterreduction(days)

        ## set new dates as a property
        imgcolllist = self._imagreducedbydays.toList(self._imagreducedbydays.size())
        reducedimages = []
        for dateindex in range(len(self._dates_reduced)):
            img = imgcolllist.get(ee.Number(int(dateindex)))

            datetoimage = datetime.datetime.timestamp(
                datetime.datetime.strptime(str(self._dates_reduced[dateindex])[:10], '%Y-%m-%d')) * 1000

            reducedimages.append(ee.Image(img).set('system:time_start', ee.Number(datetoimage)))

        self.image_collection = ee.ImageCollection(ee.List(reducedimages)).sort('system:time_start')
        self._set_coverpercentageasproperty()

    def reduce_duplicatedates(self):
        reducedimages = []
        for dateindex in range(len(self._checkmultyple_tiles[1])):
            ## get indexes from summary
            indexesdup = list(self.dates.loc[self.dates.apply(
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
                datetime.datetime.strptime(str(self._checkmultyple_tiles[1][dateindex]), '%Y%m%d')) * 1000
            reducedimages.append(imagereduced.set('system:time_start', ee.Number(datetoimage)))

        for dateindex in range(len(self._checkmultyple_tiles[2])):
            indexesdup = list(self.dates.loc[self.dates.apply(
                lambda x: x.strftime("%Y%m%d")) ==
                                             self._checkmultyple_tiles[2][dateindex]].index)

            reducedimages.append(self.image_collection.toList(self.image_collection.size()).get(indexesdup[0]))

        imagecollection = ee.ImageCollection(ee.List(reducedimages)).sort('system:time_start')
        return imagecollection

    def displace_landsatcollection(self, displacement=None):

        if displacement is not None:
            self.image_collection = self.image_collection.map(lambda img:
                                                              img.displace(displacement))
            print("the image collection was resgistered")

        else:
            print("you must provide an ee image displacement reference first")

    def __init__(self, start_date,
                 end_date,
                 roi_filename=None,
                 mission=None,
                 point_coordinates=None,
                 bands=None,
                 cloud_percentage=100,
                 remove_clouds=True,
                 buffer=50,
                 _zScoreThresh=-2,
                 _shadowSumThresh=0.15,
                 _cloudScoreThresh= 8,
                 _cloudscores2toa= False):

        ### set initial properties
        self.mission = mission
        self._querypoint = [np.nan, np.nan]
        self._dates = [start_date, end_date]
        self._multiple_polygons = [np.nan]

        ## get spatial points

        if roi_filename is not None:
            ee_geometry = gee_functions.geometry_as_ee(roi_filename)
            if len(ee_geometry) > 1:
                self._multiple_polygons = ee_geometry[1]
            self._ee_sp = ee_geometry[0]

        ## setting a single point as geometry
        if point_coordinates is not None:
            if len(point_coordinates) == 2:
                self._ee_sp = gee_functions.coords_togeepoint(point_coordinates, buffer)
                self._querypoint = point_coordinates

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
            self.image_collection = self.image_collection.select(self._bands)

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
            self.image_collection = self.image_collection.select(self._bands).filterMetadata('CLOUDY_PIXEL_PERCENTAGE',
                                                                                             'less_than',
                                                                                             cloud_percentage)
            if remove_clouds is True:
                self.image_collection = self.image_collection.map(
                    lambda img: s2_functions.maskS2sr(img))

            if bands is not None:
                self._bands = bands

        if mission == "sentinel2_toa":
            self.image_collection = self.image_collection.select(self._bands
                                                                 ).filterMetadata('CLOUDY_PIXEL_PERCENTAGE',
                                                                                  'less_than',
                                                                                  cloud_percentage
                                                                                  ).filterMetadata(
                'CLOUD_COVERAGE_ASSESSMENT',
                'less_than',
                cloud_percentage)

            def scaleBands(image):
                metadata = image.toDictionary()
                t = image.select(
                    ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A', 'B9', 'B10', 'B11', 'B12']
                ).divide(10000)
                t = t.addBands(image.select(['QA60'])).set(metadata
                                                         ).copyProperties(image,
                                                                          ['system:time_start', 'system:footprint'])
                return ee.Image(t)

            self._bands = ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8',
                           'B8A', 'B9', 'B10', 'B11', 'B12', 'QA60']

            std_names = [s2_toa_stdnames[i] for i in self._bands]

            self.image_collection = self.image_collection.map(lambda img:
                                                              scaleBands(img))

            self.image_collection = self.image_collection.select(self._bands, std_names)

            if remove_clouds is True:
                self.image_collection = s2_functions.shadowMask(self.image_collection, self._ee_sp,
                                                                zScoreThresh=_zScoreThresh,
                                                                shadowSumThresh=_shadowSumThresh)
                self.image_collection = s2_functions.QAMaskCloud(self.image_collection)
                if _cloudscores2toa:
                    self.image_collection = s2_functions.sentinelCloudScore(self.image_collection,
                                                                            cloudScoreThresh=_cloudScoreThresh)
                #self.image_collection = s2_functions.topoCorrection(self.image_collection)

            self.image_collection = self.image_collection.select(std_names, self._bands)

            if bands is not None:
                self._bands = bands

        self._checkmultyple_tiles = self.check_duplicated_tiles()

        if self._checkmultyple_tiles[0] == True and (mission == "sentinel2_sr" or
                                                     mission == "landsat8_t1sr" or
                                                     mission == "sentinel2_toa"):
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

def download_gee_tolocal(geedata_class, outputfolder, regionid="",
                         scale=10, bands=None, cover_percentage=None):
    """Download gee satellite collection to local storage.
    Args:
      params: An object containing request parameters with the
          following possible values:
              geedata_class (get_gee_data) the gee class that contains all gee data.
              outputfolder (string) the path in which will be stored the data.
              regionid (string) an id for images identification
              scale (integer) the spatial resolution, 10 is the default number
              bands (list) a list with the bands that will be selected. None is the dafault
              cover_percentage (integer) a limit for coverage
    Returns:
      None.
    """

    if isinstance(geedata_class, get_gee_data):

        ## check the folder existence
        if os.path.exists(outputfolder) is False:
            os.mkdir(outputfolder)
            print('the {} was created'.format(outputfolder))

        #        if geedata_class._imagreducedbydays is None:
        #            imgcollection = geedata_class.image_collection
        #            dates = geedata_class.dates
        # else:
        #    imgcollection = geedata_class._imagreducedbydays
        #    dates = geedata_class._dates_reduced

        imgcollection = geedata_class.image_collection
        dates = geedata_class.dates

        collsummary = geedata_class.summary.copy()
        if bands is not None:
            imgcollection = imgcollection.select(bands)
        else:
            bands = geedata_class._bands

        if cover_percentage is not None:
            listofindexes = collsummary.loc[collsummary.cover_percentage > cover_percentage].index.values
            dates = dates.loc[collsummary.cover_percentage > cover_percentage]
            imgcollection = gee_functions.select_imagesfromcollection(imgcollection, listofindexes)

        ## get urls list from gee
        urls_list = gee_functions.get_eeurl(imgcollection, geedata_class._ee_sp['coordinates'], scale)

        ## change dates format

        # dates_str = [datetime.datetime.strptime(str(dates[i]), '%Y-%m-%d %H:%M:%S').strftime("%Y%m%d") for i in
        #             range(len(dates))]
        dates_str = general_functions.to_stringdates(dates)

        ## donwload each image

        filenames = [os.path.join(outputfolder,
                                  ('{}_{}_{}_{}m').format(geedata_class._prefix, dates_str[i], regionid, str(scale)))
                     for i in range(len(dates_str))]
        wrongfiles = []
        for url, filename in zip(urls_list, filenames):
            try:
                wget.download(url, filename + '.zip')
                general_functions.unzip_geeimages(filename, outputfolder, bands, scale)
                print('the {} file was downloaded'.format(filename))

            except:
                wrongfiles.append(filename)

        if len(wrongfiles) > 0:
            print('these {} files created a conflict at the moment of its download'.format(wrongfiles))



    else:
        print("the input file must be a get_gee_data class")


def download_gee_todrive(geedata_class, outputdrive_folder="satellite_images", regionid="",
                         scale=10, bands=None, cover_percentage=None):
    """Download gee satellite collection to google drive storage.
    Args:
      params: An object containing request parameters with the
          following possible values:
              geedata_class (get_gee_data) the gee class that contains all gee data.
              regionid (string) an id for images identification
              scale (integer) the spatial resolution, 10 is the default number
              bands (list) a list with the bands that will be selected. None is the dafault
              cover_percentage (integer) a limit for coverage

    Returns:
      None.
    """

    if isinstance(geedata_class, get_gee_data):

        #        if geedata_class._imagreducedbydays is None:
        #            imgcollection = geedata_class.image_collection
        #            dates = geedata_class.dates
        # else:
        #    imgcollection = geedata_class._imagreducedbydays
        #    dates = geedata_class._dates_reduced

        imgcollection = geedata_class.image_collection
        dates = geedata_class.dates

        collsummary = geedata_class.summary.copy()
        if bands is not None:
            imgcollection = imgcollection.select(bands)
        else:
            bands = geedata_class._bands

        if cover_percentage is not None:
            listofindexes = collsummary.loc[collsummary.cover_percentage > cover_percentage].index.values
            dates = dates.loc[collsummary.cover_percentage > cover_percentage]
            imgcollection = gee_functions.select_imagesfromcollection(imgcollection, listofindexes)

        ## change dates format

        dates_str = general_functions.to_stringdates(dates)

        ## donwload each image

        filenames = [('{}_{}_{}_{}m').format(geedata_class._prefix, dates_str[i], regionid, str(scale)) for i in
                     range(len(dates_str))]

        wrongfiles = []
        for i in range(len(filenames)):
            image_todownload = imgcollection.toList(imgcollection.size()).get(i)
            task = ee.batch.Export.image.toDrive(**{
                'image': ee.Image(image_todownload),
                'description': filenames[i],
                'folder': outputdrive_folder,
                'scale': scale,
                'region': geedata_class._ee_sp['coordinates']
            })
            task.start()
            while task.active():
                print('Polling for task (id: {}).'.format(filenames[i]))
                time.sleep(20)
        #            except:
        #               wrongfiles.append(filenames[i])

        if len(wrongfiles) > 0:
            print('these {} files created a conflict at the moment of its download'.format(wrongfiles))



    else:
        print("the input file must be a get_gee_data class")


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
        eegeom = gee_functions.geometry_as_ee(eegeom)[0]
        Map.addLayer(ee.Image().paint(eegeom, 1, 3), {}, 'region of interest:')

    Map.setControlVisibility(layerControl=True, fullscreenControl=True, latLngPopup=True)
    return (Map)


# def download_images(image_list):


def merge_eeimages(eelist, bandnames):
    meannames = [i + "_mean" for i in bandnames]
    return ee.ImageCollection(eelist).reduce(ee.Reducer.mean()).select(meannames, bandnames)
