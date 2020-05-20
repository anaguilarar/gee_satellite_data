import ee
from scripts import gee_satellite_data
from scripts import gee_functions
from scripts import gis_functions

ee.Initialize()

def getS2_comparable_image(dfsummary, spgeometry):
    s2imgdatmin = s2imgdatemax = None
    l8indexsummary = 0
    while (s2imgdatmin is None):

        datmin, datmax = gee_functions.dates_maxcover(dfsummary, limit=90)
        if datmin is not None:
            ## sentine 2 query for the dates wich less clioud cover in landsat images
            gets2ref = gee_satellite_data.get_gee_data(datmin,
                                                       datmax,
                                                       gis_functions.polygon_fromgeometry(spgeometry),
                                                       "sentinel2_sr",
                                                       cloud_percentage=80)

            s2summary = gets2ref.summary.copy()

            s2summary = s2summary.loc[s2summary.cover_percentage > 90]

            if (s2summary.shape[0] > 0):

                s2imgdatmin, s2imgdatemax = gee_functions.dates_maxcover(s2summary, numdays=1)
                l8indexsummary = dfsummary.cover_percentage.idxmax()

            else:
                dfsummary = dfsummary.drop(dfsummary.cover_percentage.idxmax())
        else:
            s2imgdatmin = 0

    return [s2imgdatmin, s2imgdatemax, l8indexsummary]



def maskL8sr(image):
    # Bits 3 and 5 are cloud shadow and cloud, respectively.
    cloudShadowBitMask = (1 << 3)
    cloudsBitMask = (1 << 5)
    # Get the pixel QA band.
    qa = image.select('pixel_qa')
    # Both flags should be set to zero, indicating clear conditions.
    mask1 = qa.bitwiseAnd(ee.Number(cloudShadowBitMask)).eq(0)
    mask2 = qa.bitwiseAnd(ee.Number(cloudsBitMask)).eq(0)
    return image.updateMask(mask1).updateMask(mask2)
