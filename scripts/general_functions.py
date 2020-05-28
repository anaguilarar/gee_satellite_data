from scripts import gee_satellite_data
from zipfile import ZipFile
import numpy as np
import pandas as pd
import os
import shutil

def get_imageproperties(filename, outputfolder, scale):
    datestr = filename[filename.index('_20') + 1:filename.index('_20') + 9]
    prefixgee = filename[len(outputfolder) + 1:filename.index('_20')]
    regionid = filename[filename.index(datestr) + 9:filename.index(str(scale) + 'm') - 1]
    return [prefixgee, datestr, regionid]

def unzip_files(filepath, outputpath):
    with ZipFile(filepath, 'r') as zipObj:
        # Get list of files names in zip
        filesunzipped = zipObj.namelist()
        zipObj.extractall(outputpath)

    return filesunzipped


def unzip_geeimages(zipfilename, outputfolder, imgbands, scale):
    filenamesunzipped = unzip_files(zipfilename + '.zip', outputfolder)
    imgargs = get_imageproperties(zipfilename, outputfolder, scale)

    if type(imgbands) != list:
        imgbands = [imgbands]

    newfolder = '{}_{}_{}_{}m'.format(imgargs[0], imgargs[1], imgargs[2],
                                      str(scale))

    if os.path.exists(os.path.join(outputfolder, newfolder)) == False:
        os.mkdir(os.path.join(outputfolder, newfolder))

    for bandsindex in range(len(imgbands)):

        filesperband = np.array([x for x in filenamesunzipped if imgbands[bandsindex] in x])
        suffixraster = [x[x.index(imgbands[bandsindex] + '.') + len(imgbands[bandsindex]):] for x in filesperband]

        newnames_perband = []
        for i in range(len(suffixraster)):
            newnames_perband.append(os.path.join(outputfolder, newfolder,
                                                 '{}_{}_{}_{}_{}m{}'
                                                 .format(imgargs[0], imgbands[bandsindex], imgargs[1], imgargs[2],
                                                         str(scale), suffixraster[i])))

        for j, i in zip(filesperband, newnames_perband):
            shutil.move(os.path.join(outputfolder, j),
                        os.path.join(outputfolder, newfolder))

            os.rename(os.path.join(outputfolder, newfolder, j), i)

    os.remove(zipfilename + '.zip')


def to_stringdates(pddates, sep= ""):
    strdates = []
    for i in pd.DatetimeIndex(pddates):
        year = str(i.year)
        month = i.month
        day = i.day
        if month < 10:
            month = "0" + str(month)
        else:
            month = str(month)
        if day < 10:
            day = "0" + str(day)
        else:
            day = str(day)
        strdates.append(year + sep + month + sep + day)

    return (strdates)