from datetime import timedelta
from zipfile import ZipFile

def unzip_files(filepath, outputpath):
    with ZipFile(filepath, 'r') as zipObj:
        # Get list of files names in zip
        filesunzipped = zipObj.namelist()
        zipObj.extractall(outputpath)

    return filesunzipped



