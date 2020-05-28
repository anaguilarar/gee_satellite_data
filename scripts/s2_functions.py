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
    #imageaftermaskshadow = imageaftermask0.updateMask(maskshadow)
    #imageafterclouds = imageaftermaskshadow.mask(maskclouds.eq(0))
    imageafterclouds = imageaftermask0.mask(maskclouds.eq(0))

    return imageafterclouds

