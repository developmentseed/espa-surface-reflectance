import requests
import logging
import sys
import os
import shutil
import fnmatch
import subprocess
import time
from io import StringIO
logging.getLogger('requests').setLevel(logging.WARNING)

# Global static variables
ERROR = 1
SUCCESS = 0
NPP_START_YEAR = 2017
JPSS1_START_YEAR = 2021 # quarterly processing will reprocess back to the
                        # start year to make sure all data is up to date
                        # Landsat 8 was launched on Feb. 11, 2013
                        # Landsat 9 was launched on Sept. 27, 2021

# Specify the base location for the LAADS VIIRS data as well as the correct
# subdirectories for each of the instrument-specific ozone and water vapor
# products
SERVER_URL = 'https://ladsweb.modaps.eosdis.nasa.gov'
VIIRS_JPSS1 = '/archive/allData/3194/VJ104ANC/'
VIIRS_NPP = '/archive/allData/5000/VNP04ANC/'


def buildURLs(year, doy):
    """
    Builds the URLs for the VIIRS JPSS1 and NPP products for the current year
    and DOY, and put that URL on the list.

    Args:
      year: year of desired LAADS data
      doy: day of year of desired LAADS data

    Returns:
      None: error resolving the instrument and associated URL for the
            specified year and DOY
      urlList: list of URLs to pull the LAADS data from for the specified
               year and DOY.
    """
    urlList = []     # create empty URL list

    # append JPSS1 as the first/priority file (VJ104ANC) as long as it's
    # within the JPSS1 range
    if year >= JPSS1_START_YEAR:
        url = ('{}{}{}/{:03d}/'.format(SERVER_URL, VIIRS_JPSS1, year, doy))
        urlList.append(url)

    # append NPP as the secondary file (VNP04ANC)
    url = ('{}{}{}/{:03d}/'.format(SERVER_URL, VIIRS_NPP, year, doy))
    urlList.append(url)

    return urlList


def downloadLads (year, doy, destination, token=None):
    """
    Retrieves the files for the specified year and DOY from the LAADS https
    interface and download to the desired destination.  If the destination
    directory does not exist, then it is made before downloading.  Existing
    files in the download directory are removed/cleaned.  This will download
    the JPSS1 file as the priority and the NPP as the backup, for the current
    year, DOY.

    Args:
      year: year of data to download (integer)
      doy: day of year of data to download (integer)
      destination: name of the directory on the local system to download the
          LAADS files
      token: application token for the desired website

    Returns:
      ERROR: error occurred while processing
      SUCCESS: processing completed successfully
    """
    # get the logger
    logger = logging.getLogger(__name__)

    # obtain the list of URL(s) for our particular date
    urlList = buildURLs(year, doy)
    if urlList is None:
        msg = ('LAADS URLs could not be resolved for year {} and DOY {}'
               .format(year, doy))
        logger.error(msg)
        return ERROR

    # download the files from the list of URLs. The list should be the priority
    # JPSS1 file first (if it falls within the correct date range), followed by
    # the backup NPP file.
    msg = 'Downloading data for {}/{} to {}'.format(year, doy, destination)
    logger.info(msg)
    for url in urlList:
        msg = 'Retrieving {} to {}'.format(url, destination)
        logger.info(msg)
        cmd = ('wget -e robots=off -m -np -R .html,.tmp -nH --no-directories '
               '--header \"Authorization: Bearer {}\" -P {} \"{}\"'
               .format(token, destination, url))
        retval = subprocess.call(cmd, shell=True, cwd=destination)
    
        # make sure the wget was successful or retry up to 5 more times and
        # sleep in between. if successful then break out of the for loop.
        if retval:
            retry_count = 1
            while ((retry_count <= 5) and (retval)):
                time.sleep(60)
                logger.info('Retry {0} of wget for {1}'
                            .format(retry_count, url))
                retval = subprocess.call(cmd, shell=True, cwd=destination)
                retry_count += 1
    
            if retval:
                logger.info('unsuccessful download of {0} (retried 5 times)'
                            .format(url))
            else:
                break
        else:
            break

    # make sure the index.html file was removed if it was downloaded
    index_file = '{}/index.html'.format(destination)
    del index_file
    
    return SUCCESS
