import ee

ee.Initialize()


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
    imageaftermask0 = ee.Image(image).updateMask(mask0).updateMask(mask1)
    imageaftermaskshadow = imageaftermask0.mask(maskshadow.eq(0))
    # imageaftermaskshadow = imageaftermask0.updateMask(maskshadow)
    # imageafterclouds = imageaftermaskshadow.mask(maskclouds.eq(0))
    imageafterclouds = imageaftermask0.mask(maskclouds.eq(0))

    return imageafterclouds


def shadowMask(collection, studyArea,
               zScoreThresh=-1.5,
               shadowSumThresh=0.16,
               contractPixels=1.5,
               dilatePixels=2.5):
    ## taken from: For information and issues please contact: Ate Poortinga (apoortinga@sig-gis.com)
    ## Python implementation can be found on github: https://github.com/sig-gis/Ecuador_SEPAL

    inBands = ["B8", 'B11']
    shadowSumBands = ['nir', 'swir1']

    allCollection = ee.ImageCollection('COPERNICUS/S2').filterBounds(studyArea).select(inBands, shadowSumBands)
    # Get some pixel-wise stats for the time series
    irStdDev = allCollection.select(shadowSumBands).reduce(ee.Reducer.stdDev())
    irMean = allCollection.select(shadowSumBands).mean()

    def maskDarkOutliers(img):
        zScore = img.select(shadowSumBands).subtract(irMean).divide(irStdDev)
        irSum = img.select(shadowSumBands).reduce(ee.Reducer.sum())
        TDOMMask = zScore.lt(zScoreThresh).reduce(ee.Reducer.sum()).eq(2).And(irSum.lt(shadowSumThresh))

        TDOMMask = TDOMMask.focal_min(contractPixels).focal_max(dilatePixels).rename('TDOMMask')
        return img.updateMask(TDOMMask.Not()).addBands(TDOMMask)

    # Mask out dark dark outliers
    collection = collection.map(lambda image:
                                maskDarkOutliers(image))

    return collection


def QAMaskCloud(collection):
    def maskClouds(image):
        qa = image.select('QA60').int16()
        ## Bits 10 and 11 are clouds and cirrus, respectively.
        cloudBitMask = ee.Number(2).pow(10).int()
        cirrusBitMask = ee.Number(2).pow(11).int()

        # Both flags should be set to zero, indicating clear conditions
        mask = qa.bitwiseAnd(cloudBitMask).eq(0).And(qa.bitwiseAnd(cirrusBitMask).eq(0))
        # Return the masked and scaled data.
        return image.updateMask(mask)

    collection = collection.map(lambda img:
                                maskClouds(img))
    return collection


def sentinelCloudScore(s2s,
                       cloudScoreThresh=10,
                       contractPixels=1.5,
                       dilatePixels=2.5):
    def maskScore(img):
        cloudMask = img.select(['cloudScore']).lt(
            cloudScoreThresh).focal_max(
            contractPixels).focal_min(dilatePixels).rename('cloudMask')
        return img.updateMask(cloudMask).addBands(cloudMask)

    def getCloudScore(img):
        # Compute several indicators of cloudyness and take the minimum of them.
        def rescale(img, exp, thresholds):
            return img.expression(exp, {img: img}
                                  ).subtract(thresholds[0]).divide(thresholds[1] - thresholds[0])

        score = ee.Image(1)
        blueCirrusScore = ee.Image(0)
        # Clouds are reasonably bright in the blue or cirrus bands.
        # Use.max as a pseudo OR conditional
        blueCirrusScore = blueCirrusScore.max(rescale(img, 'img.blue', [0.1, 0.5]))
        blueCirrusScore = blueCirrusScore.max(rescale(img, 'img.cb', [0.1, 0.5]))
        blueCirrusScore = blueCirrusScore.max(rescale(img, 'img.cirrus', [0.1, 0.3]))

        score = score.min(blueCirrusScore)
        # Clouds are reasonably bright in all visiblebands.
        score = score.min(rescale(img, 'img.red + img.green + img.blue', [0.2, 0.8]))
        # Clouds are reasonably bright in all infrared bands.
        score = score.min(rescale(img, 'img.nir + img.swir1 + img.swir2', [0.3, 0.8]))
        # However, clouds are not snow.
        ndsi = img.normalizedDifference(['green', 'swir1'])
        score = score.min(rescale(ndsi, 'img', [0.8, 0.6]))
        score = score.multiply(100).byte()
        score = score.clamp(0, 100)
        return img.addBands(score.rename(['cloudScore']))

    s2s = s2s.map(lambda img:
                  getCloudScore(img))
    # Find low cloud score pctl for each pixel to avoid comission errors

    # minCloudScore = s2s.select(['cloudScore']).reduce(ee.Reducer.percentile([cloudScorePctl]));

    s2s = s2s.map(lambda img: maskScore(img))

    return s2s


#def rescale(img, exp, thresholds):
#    return img.expression(exp, {img: img}
#                          ).subtract(thresholds[0]).divide(thresholds[1] - thresholds[0])


PI = ee.Number(3.14159265359)
MAX_SATELLITE_ZENITH = 7.5

MAX_DISTANCE = 1000000
UPPER_LEFT = 0
LOWER_LEFT = 1
LOWER_RIGHT = 2
UPPER_RIGHT = 3


def brdfS2(collection):
    collection = collection.map(lambda img:
                                applyBRDF(img))
    return collection


def applyBRDF(image):
    date = image.date()
    footprint = ee.List(image.geometry().bounds().bounds().coordinates().get(0))
    angles = getsunAngles(date, footprint)

    sunAz = angles[0]
    sunZen = angles[1]

    viewAz = azimuth(footprint)
    viewZen = zenith(footprint)
    kval = _kvol(sunAz, sunZen, viewAz, viewZen)
    kvol = kval[0]
    kvol0 = kval[1]
    result = _apply(image, kvol.multiply(PI), kvol0.multiply(PI))
    return result


# Get sunAnglesfrom the map given the data.
# date: ee.date object footprint: geometry of the image

def getsunAngles(date, footprint):
    jdp = date.getFraction('year')
    seconds_in_hour = 3600
    hourGMT = ee.Number(date.getRelative('second', 'day')).divide(seconds_in_hour)
    latRad = ee.Image.pixelLonLat().select('latitude').multiply(PI.divide(180))
    longDeg = ee.Image.pixelLonLat().select('longitude')

    # Julian day proportion in radians
    jdpr = jdp.multiply(PI).multiply(2)
    a = ee.List([0.000075, 0.001868, 0.032077, 0.014615, 0.040849])
    meanSolarTime = longDeg.divide(15.0).add(ee.Number(hourGMT))
    localSolarDiff1 = value(a, 0).add(value(a, 1).multiply(jdpr.cos())
                                      ).subtract(value(a, 2).multiply(jdpr.sin())
                                                 ).subtract(value(a, 3).multiply(
        jdpr.multiply(2).cos())).subtract(value(a, 4).multiply(jdpr.multiply(2).sin()))

    localSolarDiff2 = localSolarDiff1.multiply(12 * 60)
    localSolarDiff = localSolarDiff2.divide(PI)
    trueSolarTime = meanSolarTime.add(localSolarDiff.divide(60)).subtract(12.0)
    # Hour as an angle;
    ah = trueSolarTime.multiply(ee.Number(MAX_SATELLITE_ZENITH * 2).multiply(PI.divide(180)))
    b = ee.List([0.006918, 0.399912, 0.070257, 0.006758, 0.000907, 0.002697, 0.001480])
    delta = value(b, 0).subtract(value(b, 1).multiply(
        jdpr.cos())).add(value(b, 2).multiply(
        jdpr.sin())).subtract(value(b, 3).multiply(
        jdpr.multiply(2).cos())).add(value(b, 4).multiply(
        jdpr.multiply(2).sin())).subtract(value(b, 5).multiply(
        jdpr.multiply(3).cos())).add(value(b, 6).multiply(jdpr.multiply(3).sin()));

    cosSunZen = latRad.sin().multiply(delta.sin()
                                      ).add(latRad.cos().multiply(ah.cos()).multiply(delta.cos()))
    sunZen = cosSunZen.acos()
    # sun azimuth from south, turning west
    sinSunAzSW = ah.sin().multiply(delta.cos()).divide(sunZen.sin())
    sinSunAzSW = sinSunAzSW.clamp(-1.0, 1.0)

    cosSunAzSW = (latRad.cos().multiply(-1).multiply(
        delta.sin()).add(latRad.sin().multiply(
        delta.cos()).multiply(ah.cos()))).divide(sunZen.sin())

    sunAzSW = sinSunAzSW.asin()
    sunAzSW = where(cosSunAzSW.lte(0), sunAzSW.multiply(-1).add(PI), sunAzSW)
    sunAzSW = where(cosSunAzSW.gt(0).And(sinSunAzSW.lte(0)), sunAzSW.add(PI.multiply(2)), sunAzSW)
    sunAz = sunAzSW.add(PI)
    # Keep within [0, 2pi] range
    sunAz = where(sunAz.gt(PI.multiply(2)), sunAz.subtract(PI.multiply(2)), sunAz)
    footprint_polygon = ee.Geometry.Polygon(footprint)
    sunAz = sunAz.clip(footprint_polygon)
    sunAz = sunAz.rename(['sunAz'])
    sunZen = sunZen.clip(footprint_polygon).rename(['sunZen'])
    return [sunAz, sunZen]


# Get azimuth. footprint: geometry of the image
def azimuth(footprint):
    def x(point):
        return ee.Number(ee.List(point).get(0))

    def y(point):
        return ee.Number(ee.List(point).get(1))

    upperCenter = line_from_coords(footprint, UPPER_LEFT, UPPER_RIGHT).centroid().coordinates()
    lowerCenter = line_from_coords(footprint, LOWER_LEFT, LOWER_RIGHT).centroid().coordinates()
    slope = ((y(lowerCenter)).subtract(y(upperCenter))).divide((x(lowerCenter)).subtract(x(upperCenter)))
    slopePerp = ee.Number(-1).divide(slope)
    azimuthLeft = ee.Image(PI.divide(2).subtract((slopePerp).atan()))
    return azimuthLeft.rename(['viewAz'])


##Get zenith. footprint: geometry of the image

def zenith(footprint):
    leftLine = line_from_coords(footprint, UPPER_LEFT, LOWER_LEFT)
    rightLine = line_from_coords(footprint, UPPER_RIGHT, LOWER_RIGHT)
    leftDistance = ee.FeatureCollection(leftLine).distance(MAX_DISTANCE)
    rightDistance = ee.FeatureCollection(rightLine).distance(MAX_DISTANCE)
    viewZenith = rightDistance.multiply(ee.Number(MAX_SATELLITE_ZENITH * 2)
                                        ).divide(rightDistance.add(leftDistance)
                                                 ).subtract(ee.Number(MAX_SATELLITE_ZENITH)
                                                            ).clip(ee.Geometry.Polygon(footprint)
                                                                   ).rename(['viewZen'])
    return viewZenith.multiply(PI.divide(180))


# apply function to all bands
# http://www.mdpi.com/2072-4292/9/12/1325/htm#sec3dot2-remotesensing-09-01325
# https://www.sciencedirect.com/science/article/pii/S0034425717302791
# image: the image to apply the function
# to kvol: kvol0

def _apply(image, kvol, kvol0):
    f_iso = 0
    f_geo = 0
    f_vol = 0
    blue = _correct_band(image, 'blue', kvol, kvol0, f_iso=0.0774, f_geo=0.0079, f_vol=0.0372)
    green = _correct_band(image, 'green', kvol, kvol0, f_iso=0.1306, f_geo=0.0178, f_vol=0.0580)
    red = _correct_band(image, 'red', kvol, kvol0, f_iso=0.1690, f_geo=0.0227, f_vol=0.0574)
    re1 = _correct_band(image, 're1', kvol, kvol0, f_iso=0.2085, f_geo=0.0256, f_vol=0.0845)
    re2 = _correct_band(image, 're2', kvol, kvol0, f_iso=0.2316, f_geo=0.0273, f_vol=0.1003)
    re3 = _correct_band(image, 're3', kvol, kvol0, f_iso=0.2599, f_geo=0.0294, f_vol=0.1197)
    nir = _correct_band(image, 'nir', kvol, kvol0, f_iso=0.3093, f_geo=0.0330, f_vol=0.1535)
    re4 = _correct_band(image, 're4', kvol, kvol0, f_iso=0.2907, f_geo=0.0410, f_vol=0.1611)
    swir1 = _correct_band(image, 'swir1', kvol, kvol0, f_iso=0.3430, f_geo=0.0453, f_vol=0.1154)
    swir2 = _correct_band(image, 'swir2', kvol, kvol0, f_iso=0.2658, f_geo=0.0387, f_vol=0.0639)

    return image.select([]).addBands([blue, green, red, nir, re1, re2, re3, nir, re4, swir1, swir2]);


# correct bandfunction image: the imageto apply the function to band_name * kvol* kvol0* f_iso* f_geo* f_vol
def _correct_band(image, band_name, kvol, kvol0, f_iso, f_geo, f_vol):
    """fiso + fvol * kvol + fgeo * kgeo"""
    iso = ee.Image(f_iso)
    geo = ee.Image(f_geo)
    vol = ee.Image(f_vol)
    pred = vol.multiply(kvol).add(geo.multiply(kvol)).add(iso).rename(['pred'])
    pred0 = vol.multiply(kvol0).add(geo.multiply(kvol0)).add(iso).rename(['pred0'])
    cfac = pred0.divide(pred).rename(['cfac'])
    corr = image.select(band_name).multiply(cfac).rename([band_name])
    return corr


# calculate kvol and kvol0 * sunAZ sunZen* viewAz* viewZen
def _kvol(sunAz, sunZen, viewAz, viewZen):
    """Calculate kvol kernel.
	    From Lucht et al. 2000
		Phase angle = cos(solar zenith) cos(view zenith) + sin(solar zenith) sin(view zenith) cos(relative azimuth)"""

    relative_azimuth = sunAz.subtract(viewAz).rename(['relAz'])
    pa1 = viewZen.cos().multiply(sunZen.cos())
    pa2 = viewZen.sin().multiply(sunZen.sin()).multiply(relative_azimuth.cos())
    phase_angle1 = pa1.add(pa2)
    phase_angle = phase_angle1.acos()
    p1 = ee.Image(PI.divide(2)).subtract(phase_angle)
    p2 = p1.multiply(phase_angle1)
    p3 = p2.add(phase_angle.sin())
    p4 = sunZen.cos().add(viewZen.cos())
    p5 = ee.Image(PI.divide(4))
    kvol = p3.divide(p4).subtract(p5).rename(['kvol'])
    viewZen0 = ee.Image(0)
    pa10 = viewZen0.cos().multiply(sunZen.cos())
    pa20 = viewZen0.sin().multiply(sunZen.sin()).multiply(relative_azimuth.cos())
    phase_angle10 = pa10.add(pa20)
    phase_angle0 = phase_angle10.acos()
    p10 = ee.Image(PI.divide(2)).subtract(phase_angle0)
    p20 = p10.multiply(phase_angle10)
    p30 = p20.add(phase_angle0.sin())
    p40 = sunZen.cos().add(viewZen0.cos())
    p50 = ee.Image(PI.divide(4))

    kvol0 = p30.divide(p40).subtract(p50).rename(['kvol0'])
    return [kvol, kvol0]


# helper function
def line_from_coords(coordinates, fromIndex, toIndex):
    return ee.Geometry.LineString(ee.List([
        coordinates.get(fromIndex),
        coordinates.get(toIndex)]))


def where(condition, trueValue, falseValue):
    trueMasked = trueValue.mask(condition)
    falseMasked = falseValue.mask(invertMask(condition))
    return trueMasked.unmask(falseMasked)


def invertMask(mask):
    return mask.multiply(-1).add(1)


def value(list, index):
    return ee.Number(list.get(index))


############## SENTINEL 2 TOA TERRAIN CORRECTION

scale = 300
toaOrSR = 'SR'

# get terrain layers
dem = ee.Image("USGS/SRTMGL1_003")
degree2radian = 0.01745


def topoCorrection(collection):
    collection = collection.map(lambda img:
                                illuminationCondition(img))

    collection = ee.ImageCollection(collection).map(lambda img:
                                                    illuminationCorrection(img))
    # collection = correction.merge(notcorrection).sort("system:time_start");
    return (collection)


# Function to calculate illumination condition(IC).Function by Patrick Burns(pb463 @ nau.edu) and Matt Macander
# (mmacander @ abrinc.com)

def illuminationCondition(img):
    # Extract image metadata about solar position
    SZ_rad = ee.Image.constant(ee.Number(img.get('MEAN_SOLAR_ZENITH_ANGLE'))).multiply(3.14159265359).divide(180).clip(
        img.geometry().buffer(10000))
    SA_rad = ee.Image.constant(ee.Number(img.get('MEAN_SOLAR_AZIMUTH_ANGLE')).multiply(3.14159265359).divide(180)).clip(
        img.geometry().buffer(10000))

    # Creat terrain layers
    slp = ee.Terrain.slope(dem).clip(img.geometry().buffer(10000))
    slp_rad = ee.Terrain.slope(dem).multiply(3.14159265359).divide(180).clip(
        img.geometry().buffer(10000))
    asp_rad = ee.Terrain.aspect(dem).multiply(3.14159265359).divide(180).clip(
        img.geometry().buffer(10000))

    # Calculate the Illumination Condition(IC)
    # slope part of the illumination condition
    cosZ = SZ_rad.cos()
    cosS = slp_rad.cos()
    slope_illumination = cosS.expression("cosZ * cosS",
                                         {'cosZ': cosZ,
                                          'cosS': cosS.select('slope')})
    # aspect part of the illumination condition var
    sinZ = SZ_rad.sin()
    sinS = slp_rad.sin()
    cosAziDiff = (SA_rad.subtract(asp_rad)).cos()
    aspect_illumination = sinZ.expression("sinZ * sinS * cosAziDiff",
                                          {'sinZ': sinZ,
                                           'sinS': sinS,
                                           'cosAziDiff': cosAziDiff})
    # full illumination condition(IC)
    ic = slope_illumination.add(aspect_illumination)
    # Add IC to original image
    img_plus_ic = ee.Image(
        img.addBands(ic.rename('IC')).addBands(cosZ.rename('cosZ')).addBands(cosS.rename('cosS')).addBands(
            slp.rename('slope')))
    return img_plus_ic


# Function to apply the Sun - Canopy - Sensor + C(SCSc) correction method
# to each image.Function by Patrick Burns(pb463 @ nau.edu) and Matt Macander (mmacander @ abrinc.com)

def illuminationCorrection(img):
    props = img.toDictionary()
    st = img.get('system:time_start')
    img_plus_ic = img
    # mask1 = img_plus_ic.select('nir').gt(-0.1)
    mask2 = img_plus_ic.select('slope').gte(5).And(img_plus_ic.select('IC').gte(0)
                                                   ).And(img_plus_ic.select('nir').gt(-0.1))
    img_plus_ic_mask2 = ee.Image(img_plus_ic.updateMask(mask2))
    # Specify Bands to topographically correct
    bandList = ['blue', 'green', 'red', 'nir', 'swir1', 'swir2']
    compositeBands = img.bandNames()
    nonCorrectBands = img.select(compositeBands.removeAll(bandList))

    # geom = ee.Geometry(img.get('system:footprint')).bounds().buffer(10000)

    def apply_SCSccorr(band):
        # method = 'SCSc'
        out = ee.Image(1).addBands(img_plus_ic_mask2.select('IC', band)
                                   ).reduceRegion(reducer=ee.Reducer.linearRegression(2, 1),
                                                  geometry=ee.Geometry(img.geometry()),
                                                  scale=300,
                                                  bestEffort=True,
                                                  maxPixels=1e10)

        fit = out.combine({"coefficients": ee.Array([[1], [1]])}, False)
        # Get the coefficients as a nested list, ast it to an array, and get just
        # the selected column

        out_a = (ee.Array(fit.get('coefficients')).get([0, 0]))
        out_b = (ee.Array(fit.get('coefficients')).get([1, 0]))
        out_c = out_a.divide(out_b)
        # Apply the SCSc correction
        SCSc_output = img_plus_ic_mask2.expression(
            "((image * (cosB * cosZ + cvalue)) / (ic + cvalue))", {
                'image': img_plus_ic_mask2.select(band),
                'ic': img_plus_ic_mask2.select('IC'),
                'cosB': img_plus_ic_mask2.select('cosS'),
                'cosZ': img_plus_ic_mask2.select('cosZ'),
                'cvalue': out_c
            })
        return SCSc_output

    imagebandprocess = [apply_SCSccorr(bnd) for bnd in bandList]
    # img_SCSccorr = ee.Image(bandList.map(
    #    lambda bnd:
    #    apply_SCSccorr(bnd))).addBands(img_plus_ic.select('IC'))
    img_SCSccorr = ee.Image(imagebandprocess).addBands(img_plus_ic.select('IC'))
    bandList_IC = ee.List([bandList, 'IC']).flatten()
    img_SCSccorr = img_SCSccorr.unmask(img_plus_ic.select(bandList_IC)).select(bandList)

    return img_SCSccorr.addBands(nonCorrectBands
                                 ).setMulti(props
                                            ).set('system:time_start', st
                                                  )
