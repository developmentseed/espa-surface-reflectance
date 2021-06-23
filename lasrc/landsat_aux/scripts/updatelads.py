#!/usr/bin/env python

from __future__ import (division, print_function, absolute_import, unicode_literals)
import sys
import os
import shutil
import fnmatch
import datetime
import subprocess
import re
import time
import subprocess
from optparse import OptionParser
import requests
import logging
from config_utils import retrieve_cfg
from api_interface import api_connect
from io import StringIO

# Global static variables
ERROR = 1
SUCCESS = 0
START_YEAR = 2013      # quarterly processing will reprocess back to the
                       # start year to make sure all data is up to date
                       # Landsat 8 was launched on Feb. 11, 2013

##NOTE: For non-ESPA environments, the TOKEN needs to be defined.  This is
##the application token that is required for accessing the LAADS data
##https://ladsweb.modaps.eosdis.nasa.gov/tools-and-services/data-download-scripts/
TOKEN = None
USERAGENT = 'espa.cr.usgs.gov/updatelads.py 1.4.1--' + sys.version.replace('\n','').replace('\r','')

# Specify the base location for the LAADS data as well as the
# correct subdirectories for each of the instrument-specific ozone
# products
# These are version 006 products
SERVER_URL = 'https://ladsweb.modaps.eosdis.nasa.gov'
TERRA_CMA = '/archive/allData/6/MOD09CMA/'
TERRA_CMG = '/archive/allData/6/MOD09CMG/'
AQUA_CMA = '/archive/allData/6/MYD09CMA/'
AQUA_CMG = '/archive/allData/6/MYD09CMG/'

def isLeapYear (year):
    """
    Determines if the specified year is a leap year.

    Args:
      year: year to determine if it is a leap year (integer)

    Returns:
      True: yes, this is a leap year
      False: no, this is not a leap year
    """
    if (year % 4) == 0:
        if (year % 100) == 0:
            if (year % 400) == 0:
                return True
            else:
                return False
        else:
            return True
    else:
        return False


def geturl(url, token=None, out=None):
    """
    Pulls the file specified by URL.  If there is a problem with the
    connection, then retry up to 5 times.

    Args:
      url: URL for the file to be downloaded
      token: application token for the desired website
      out: directory where the downloaded file will be written

    Returns: None
    """
    # get the logger
    logger = logging.getLogger(__name__)

    # get the headers for the application data download
    headers = {'user-agent' : USERAGENT}
    if not token is None:
        headers['Authorization'] = 'Bearer ' + token

    # Use CURL to download the file
    import subprocess
    try:
        # Setup CURL command using silent mode and change location if reported
        args = ['curl', '--fail', '-sS', '-L', '--retry', '5',
                '--retry-delay', '60', '--get', url]
        for (k,v) in list(headers.items()):
            args.extend(['-H', ': '.join([k, v])])
        if out is None:
            # python3's subprocess.check_output returns stdout as a
            # byte string
            result = subprocess.check_output(args)
            return result.decode('utf-8') if isinstance(result, bytes) else result
        else:
            # download of the actual LAADS data product
            retval = subprocess.call(args, stdout=out)

            # make sure the download was successful or retry up to 5 more times
            # and sleep in between
            if retval:
                retry_count = 1
                while ((retry_count <= 5) and (retval)):
                    time.sleep(60)
                    logger.info('Retry {} of download for {}'
                                .format(retry_count, url))
                    retval = subprocess.call(args, stdout=out)
                    retry_count += 1

                if retval:
                    logger.warn('Unsuccessful download of {} (retried 5 times)'
                                .format(url))

    except subprocess.CalledProcessError as e:
        msg = ('curl GET error for URL (). {}:{}'
               .format(url, e.message, e.output))
        logger.error(msg)

    return None


def buildURLs(year, doy):
    """
    Builds the URLs for the Terra and Aqua CMG and CMA products for the
    current year and DOY, and put that URL on the list.

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

    # append TERRA CMA data (MOD09CMA)
    url = ('{}{}{}/{:03d}/'.format(SERVER_URL, TERRA_CMA, year, doy))
    urlList.append(url)

    # append TERRA CMG data (MOD09CMG)
    url = ('{}{}{}/{:03d}/'.format(SERVER_URL, TERRA_CMG, year, doy))
    urlList.append(url)

    # append AQUA CMA data (MYD09CMA)
    url = ('{}{}{}/{:03d}/'.format(SERVER_URL, AQUA_CMA, year, doy))
    urlList.append(url)

    # append AQUA CMG data (MYD09CMG)
    url = ('{}{}{}/{:03d}/'.format(SERVER_URL, AQUA_CMG, year, doy))
    urlList.append(url)

    return urlList


def downloadLads (year, doy, destination, token=None):
    """
    Retrieves the files for the specified year and DOY from the LAADS https
    interface and download to the desired destination.  If the destination
    directory does not exist, then it is made before downloading.  Existing
    files in the download directory are removed/cleaned.  This will download
    the Aqua/Terra CMG and CMA files for the current year, DOY.

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

    # make sure the download directory exists (and is cleaned up) or create
    # it recursively
    if not os.path.exists(destination):
        msg = '{} does not exist... creating'.format(destination)
        logger.info(msg)
        os.makedirs(destination, 0o777)
    else:
        # directory already exists and possibly has files in it.  any old
        # files need to be cleaned up
        msg = 'Cleaning download directory: {}'.format(destination)
        logger.info(msg)
        for myfile in os.listdir(destination):
            name = os.path.join(destination, myfile)
            if not os.path.isdir(name):
                os.remove(name)

    # obtain the list of URL(s) for our particular date.  this includes the
    # locations for the Aqua and Terra CMG/CMA files.
    urlList = buildURLs(year, doy)
    if urlList is None:
        msg = ('LAADS URLs could not be resolved for year {} and DOY {}'
               .format(year, doy))
        logger.error(msg)
        return ERROR

    # download all the files from the list of URLs.
    msg = 'Downloading data for {}/{} to {}'.format(year, doy, destination)
    logger.info(msg)
    for url in urlList:
        msg = 'Retrieving {} to {}'.format(url, destination)
        cmd = ('wget -e robots=off -m -np -R .html,.tmp --no-directories '
               '--header \"Authorization: Bearer {}\" -P {} \"{}\"'
               .format(token, destination, url))
        retval = subprocess.call(cmd, shell=True, cwd=destination)
    
        # make sure the wget was successful or retry up to 5 more times and
        # sleep in between
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

        # make sure the index.html file was removed if it was downloaded
        index_file = '{}/index.html'.format(destination)
        del index_file
    
    return SUCCESS


def getLadsData (auxdir, year, today, token):
    """
    Description: getLadsData downloads the daily MODIS Aqua/Terra CMG and CMA
    data files for the desired year, then combines those files into one daily
    product containing the various ozone, water vapor, temperature, etc. SDSs.
    
    Args:
      auxdir: name of the base L8_SR auxiliary directory which contains the
              LAADS directory
      year: year of LAADS data to be downloaded and processed (integer)
      today: specifies if we are just bringing the LAADS data up to date vs.
             reprocessing the data
      token: application token for the desired website

    Returns:
        ERROR: error occurred while processing
        SUCCESS: processing completed successfully
    """
    # get the logger
    logger = logging.getLogger(__name__)

    # determine the directory for the output auxiliary data files to be
    # processed.  create the directory if it doesn't exist.
    outputDir = '{}/LADS/{}'.format(auxdir, year)
    if not os.path.exists(outputDir):
        msg = '{} does not exist... creating'.format(outputDir)
        logger.info(msg)
        os.makedirs(outputDir, 0o777)

    # if the specified year is the current year, only process up through
    # today (actually 2 days earlier due to the LAADS data lag) otherwise
    # process through all the days in the year
    now = datetime.datetime.now()
    if year == now.year:
        # start processing LAADS data with a 2-day time lag. if the 2-day lag
        # puts us into last year, then we are done with the current year.
        day_of_year = now.timetuple().tm_yday - 2
        if day_of_year <= 0:
            return SUCCESS
    else:
        if isLeapYear (year) == True:
            day_of_year = 366   
        else:
            day_of_year = 365

    # set the download directory in /tmp/lads
    dloaddir = '/tmp/lads/{}'.format(year)

    # loop through each day in the year and process the LAADS data.  process
    # in the reverse order so that if we are handling data for "today", then
    # we can stop as soon as we find the current DOY has been processed.
    for doy in range(day_of_year, 0, -1):
        # get the year + DOY string
        datestr = '{}{:03d}'.format(year, doy)

        # if the data for the current year and doy exists already, then we are
        # going to skip that file if processing for the --today.  For
        # --quarterly, we will completely reprocess.
        skip_date = False
        for myfile in os.listdir(outputDir):
            if fnmatch.fnmatch (myfile, 'L8ANC' + datestr + '.hdf_fused') \
                and today:
                msg = 'L8ANC{}.hdf_fused already exists. Skip.'.format(datestr)
                logger.info(msg)
                skip_date = True
                break

        if skip_date:
            continue

        # download the daily LAADS files for the specified year and DOY
        found_mod09cma = True
        found_mod09cmg = True
        found_myd09cma = True
        found_myd09cmg = True
        status = downloadLads (year, doy, dloaddir, token)
        if status == ERROR:
            # warning message already printed
            return ERROR

        # get the Terra CMA file for the current DOY (should only be one)
        fileList = []    # create empty list to store files matching date
        for myfile in os.listdir(dloaddir):
            if fnmatch.fnmatch (myfile, 'MOD09CMA.A' + datestr + '*.hdf'):
                fileList.append (myfile)

        # make sure files were found or print a warning
        nfiles = len(fileList)
        if nfiles == 0:
            found_mod09cma = False
        else:
            # if only one file was found which matched our date, then that's
            # the file we'll process.  if more than one was found, then we
            # have a problem as only one file is expected.
            if nfiles == 1:
                terra_cma = dloaddir + '/' + fileList[0]
            else:
                msg = ('Multiple LAADS MOD09CMA files found for doy {} year {}'
                       .format(doy, year))
                logger.error(msg)
                return ERROR

        # get the Terra CMG file for the current DOY (should only be one)
        fileList = []    # create empty list to store files matching date
        for myfile in os.listdir(dloaddir):
            if fnmatch.fnmatch (myfile, 'MOD09CMG.A' + datestr + '*.hdf'):
                fileList.append(myfile)

        # make sure files were found or print a warning
        nfiles = len(fileList)
        if nfiles == 0:
            found_mod09cmg = False
        else:
            # if only one file was found which matched our date, then that's
            # the file we'll process.  if more than one was found, then we
            # have a problem as only one file is expected.
            if nfiles == 1:
                terra_cmg = dloaddir + '/' + fileList[0]
            else:
                msg = ('Multiple LAADS MOD09CMG files found for doy {} year {}'
                       .format(doy, year))
                logger.error(msg)
                return ERROR

        # get the Aqua CMA file for the current DOY (should only be one)
        fileList = []    # create empty list to store files matching date
        for myfile in os.listdir(dloaddir):
            if fnmatch.fnmatch (myfile, 'MYD09CMA.A' + datestr + '*.hdf'):
                fileList.append(myfile)

        # make sure files were found or print a warning
        nfiles = len(fileList)
        if nfiles == 0:
            found_myd09cma = False
        else:
            # if only one file was found which matched our date, then that's
            # the file we'll process.  if more than one was found, then we
            # have a problem as only one file is expected.
            if nfiles == 1:
                aqua_cma = dloaddir + '/' + fileList[0]
            else:
                msg = ('Multiple LAADS MOD09CMA files found for doy {} year {}'
                       .format(doy, year))
                logger.error(msg)
                return ERROR

        # get the Aqua CMG file for the current DOY (should only be one)
        fileList = []    # create empty list to store files matching date
        for myfile in os.listdir(dloaddir):
            if fnmatch.fnmatch (myfile, 'MYD09CMG.A' + datestr + '*.hdf'):
                fileList.append(myfile)

        # make sure files were found or print a warning
        nfiles = len(fileList)
        if nfiles == 0:
            found_myd09cmg = False
        else:
            # if only one file was found which matched our date, then that's
            # the file we'll process.  if more than one was found, then we
            # have a problem as only one file is expected.
            if nfiles == 1:
                aqua_cmg = dloaddir + '/' + fileList[0]
            else:
                msg = ('Multiple LAADS MYD09CMA files found for doy {} year {}'
                       .format(doy, year))
                logger.error(msg)
                return ERROR

        # make sure at least one of the Aqua or Terra CMG files is present
        if not found_myd09cmg and not found_mod09cmg:
            msg = ('No Aqua or Terra LAADS CMG data available for doy {} year '
                   '{}. Skipping this date.'
                   .format(doy, year))
            logger.warning(msg)
            continue

        # make sure at least one of the Aqua or Terra CMA files is present
        if not found_myd09cma and not found_mod09cma:
            msg = ('No Aqua or Terra LAADS CMA data available for doy {} year '
                   '{}. Skipping this date.'
                   .format(doy, year))
            logger.warning(msg)
            continue

        # generate the command-line arguments and executable for combining
        # the CMG and CMA products
        terra_cmg_cmdline = ''
        if found_mod09cmg:
            terra_cmg_cmdline = '--terra_cmg {}'.format(terra_cmg)

        terra_cma_cmdline = ''
        if found_mod09cma:
            terra_cma_cmdline = '--terra_cma {}'.format(terra_cma)

        aqua_cmg_cmdline = ''
        if found_myd09cmg:
            aqua_cmg_cmdline = '--aqua_cmg {}'.format(aqua_cmg)

        aqua_cma_cmdline = ''
        if found_myd09cma:
            aqua_cma_cmdline = '--aqua_cma {}'.format(aqua_cma)

        cmdstr = ('combine_l8_aux_data {} {} {} {} --output_dir {} --verbose'
                  .format(terra_cmg_cmdline, terra_cma_cmdline,
                          aqua_cmg_cmdline, aqua_cma_cmdline, outputDir))
        msg = 'Executing {}'.format(cmdstr)
        logger.info(msg)

        (status, output) = subprocess.getstatusoutput (cmdstr)
        logger.info(output)
        exit_code = status >> 8
        if exit_code != 0:
            msg = ('Error running combine_l8_aux_data for year {}, DOY {}'
                   .format(year, doy))
            logger.error(msg)
            return ERROR
    # end for doy

    # remove the files downloaded to the temporary directory
    msg = 'Removing downloaded files from {}'.format(dloaddir)
    logger.info(msg)
    if os.path.exists(dloaddir):
        for myfile in os.listdir(dloaddir):
            name = os.path.join(dloaddir, myfile)
            os.remove(name)

    return SUCCESS


############################################################################
# Description: Main routine which grabs the command-line arguments, determines
# which years/days of data need to be processed, then processes the user-
# specified dates of LAADS data.
#
# Developer(s):
#     Gail Schmidt, USGS EROS - Original development
#
# Returns:
#     ERROR - error occurred while processing
#     SUCCESS - processing completed successfully
#
# Notes:
# 1. This script can be called with the --today option or with a combination
#    of --start_year / --end_year.  --today trumps --quarterly and
#    --start_year / --end_year.
# 2. --today will process the data for the most recent year (including the
#    previous year if the DOY is within the first month of the year).  Thus
#    this option is used for nightly updates.  If the hdf fused data products
#    already exist for a particular year/doy, they will not be reprocessed.
# 3. --quarterly will process the data for today all the way back to the
#    earliest year so that any updated LAADS files are picked up and
#    processed.  Thus this option is used for quarterly updates.
# 4. Existing LAADS HDF files are removed before processing data for that
#    year and DOY, but only if the downloaded auxiliary data exists for that
#    date.
############################################################################
def main ():
    logger = logging.getLogger(__name__)  # Get logger for the module.

    # get the command line arguments
    parser = OptionParser()
    parser.add_option ('-s', '--start_year', type='int', dest='syear',
        default=0, help='year for which to start pulling LAADS data')
    parser.add_option ('-e', '--end_year', type='int', dest='eyear',
        default=0, help='last year for which to pull LAADS data')
    parser.add_option ('--today', dest='today', default=False,
        action='store_true',
        help='process LAADS data up through the most recent year and DOY')
    msg = ('process or reprocess all LAADS data from today back to {}'
           .format(START_YEAR))
    parser.add_option ('--quarterly', dest='quarterly', default=False,
        action='store_true', help=msg)

    (options, args) = parser.parse_args()
    syear = options.syear           # starting year
    eyear = options.eyear           # ending year
    today = options.today           # process most recent year of data
    quarterly = options.quarterly   # process today back to START_YEAR

    # check the arguments
    if (today == False) and (quarterly == False) and \
       (syear == 0 or eyear == 0):
        msg = ('Invalid command line argument combination.  Type --help '
              'for more information.')
        logger.error(msg)
        return ERROR

    # determine the auxiliary directory to store the data
    auxdir = os.environ.get('L8_AUX_DIR')
    if auxdir is None:
        msg = 'L8_AUX_DIR environment variable not set... exiting'
        logger.error(msg)
        return ERROR

    # Get the application token for the LAADS https interface. for ESPA
    # systems, pull the token from the config file.
    if TOKEN is None:
        # ESPA Processing Environment
        # Read ~/.usgs/espa/processing.conf to get the URL for the ESPA API.
        # Connect to the ESPA API and get the application token for downloading
        # the LAADS data from the internal database.
        PROC_CFG_FILENAME = 'processing.conf'
        proc_cfg = retrieve_cfg(PROC_CFG_FILENAME)
        rpcurl = proc_cfg.get('processing', 'espa_api')
        server = api_connect(rpcurl)
        if server:
            token = server.get_configuration('aux.downloads.laads.token')
    else:
        # Non-ESPA processing.  TOKEN needs to be defined at the top of this
        # script.
        token = TOKEN

    if token is None:
        logger.error('Application token is None. This needs to be a valid '
            'token provided for accessing the LAADS data. '
            'https://ladsweb.modaps.eosdis.nasa.gov/tools-and-services/data-download-scripts/')
        return ERROR

    # if processing today then process the current year.  if the current
    # DOY is within the first month, then process the previous year as well
    # to make sure we have all the recently available data processed.
    if today:
        msg = 'Processing LAADS data up to the most recent year and DOY.'
        logger.info(msg)
        now = datetime.datetime.now()
        day_of_year = now.timetuple().tm_yday
        eyear = now.year
        if day_of_year <= 31:
            syear = eyear - 1
        else:
            syear = eyear

    elif quarterly:
        msg = 'Processing LAADS data back to {}'.format(START_YEAR)
        logger.info(msg)
        eyear = now.year
        syear = START_YEAR

    msg = 'Processing LAADS data for {} - {}'.format(syear, eyear)
    logger.info(msg)
    for yr in range(eyear, syear-1, -1):
        msg = 'Processing year: {}'.format(yr)
        logger.info(msg)
        status = getLadsData(auxdir, yr, today, token)
        if status == ERROR:
            msg = ('Problems occurred while processing LAADS data for year {}'
                   .format(yr))
            logger.error(msg)
            return ERROR

    msg = 'LAADS processing complete.'
    logger.info(msg)
    return SUCCESS

if __name__ == "__main__":
    # setup the default logger format and level. log to STDOUT.
    logging.basicConfig(format=('%(asctime)s.%(msecs)03d %(process)d'
                                ' %(levelname)-8s'
                                ' %(filename)s:%(lineno)d:'
                                '%(funcName)s -- %(message)s'),
                        datefmt='%Y-%m-%d %H:%M:%S',
                        level=logging.INFO)
    sys.exit (main())
