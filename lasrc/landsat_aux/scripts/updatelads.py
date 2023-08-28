#!/usr/bin/env python

from __future__ import (division, print_function, absolute_import, unicode_literals)
import sys
import os
import shutil
import fnmatch
import datetime
import calendar
import subprocess
import re
import time
import subprocess

from optparse import OptionParser
import requests
import logging
from config_utils import retrieve_cfg
from api_interface import api_connect
from download_lads import *
from io import StringIO

# Global static variables
ERROR = 1
SUCCESS = 0

##NOTE: For non-ESPA environments, the TOKEN needs to be defined.  This is
##the application token that is required for accessing the LAADS data
##https://ladsweb.modaps.eosdis.nasa.gov/tools-and-services/data-download-scripts/
TOKEN = None
USERAGENT = 'espa.cr.usgs.gov/updatelads.py 1.4.1--' + sys.version.replace('\n','').replace('\r','')

# leap day start/end of month
ldaySOM = [ 1, 32, 61,  92, 122, 153, 183, 214, 245, 275, 306, 336]
ldayEOM = [31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366]

# regular day start/end of month
rdaySOM = [ 1, 32, 60,  91, 121, 152, 182, 213, 244, 274, 305, 335]
rdayEOM = [31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365]


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
        args = ['curl', '--fail', '--no-progress-meter', '-L', '--retry', '5',
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


def getLadsData (auxdir, year, today, token):
    """
    Description: getLadsData downloads the daily VIIRS atmosphere data files
    for the desired year.

    Args:
      auxdir: name of the base LASRC_SR auxiliary directory which contains the
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
        if calendar.isleap(year):
            day_of_year = 366   
        else:
            day_of_year = 365

    # set the download directory in /tmp/lads
    dloaddir = '/tmp/lads/{}'.format(year)

    # make sure the download directory exists or create it and all necessary
    # parent directories
    if not os.path.exists(dloaddir):
        msg = '{} does not exist... creating'.format(dloaddir)
        logger.info(msg)
        os.makedirs(dloaddir, 0o777)
    else:
        # directory already exists and possibly has files in it.  any old
        # files need to be cleaned up
        msg = 'Cleaning download directory: {}'.format(dloaddir)
        logger.info(msg)
        for myfile in os.listdir(dloaddir):
            name = os.path.join(dloaddir, myfile)
            if not os.path.isdir(name):
                os.remove(name)

    # loop through each day in the year and process the LAADS data.  process
    # in the reverse order so that if we are handling data for "today", then
    # we can stop as soon as we find the current DOY has been processed.
    for doy in range(day_of_year, 0, -1):
        # get the year + DOY string
        datestr = '{}{:03d}'.format(year, doy)

        # if the JPSS1 or JPSS2 data for the current year and doy exists
        # already, then we are going to skip that file if processing for
        # --today.  For --quarterly, we will completely reprocess.  If the
        # backup NPP product exists without the JPSS[1|2], then we will still
        # reprocess in hopes that the JPSS[1|2] product becomes available.
        skip_date = False
        for myfile in os.listdir(outputDir):
            if fnmatch.fnmatch (myfile, 'VJ?04ANC.A{}*.h5'.format(datestr)) \
                    and today:
                msg = ('JPSS product for VJX04ANC.A{} already exists. Skip.'
                       .format(datestr))
                logger.info(msg)
                skip_date = True
                break

        if skip_date:
            continue

        # download the daily LAADS files for the specified year and DOY. The
        # JPSS2 file is the priority, but if that isn't found then check for
        # JPSS1 followed by NPP to be downloaded.
        found_vjx04anc = False
        found_vnp04anc = False
        status = downloadLads (year, doy, dloaddir, token)
        if status == ERROR:
            # warning message already printed
            return ERROR

        # get the JPSS[1|2] file for the current DOY (should only be one)
        fileList = []    # create empty list to store files matching date
        for myfile in os.listdir(dloaddir):
            if fnmatch.fnmatch (myfile, 'VJ?04ANC.A{}*.h5'.format(datestr)):
                fileList.append (myfile)

        # make sure files were found or search for the NPP file
        nfiles = len(fileList)
        if nfiles == 0:
            # get the NPP file for the current DOY (should only be one)
            for myfile in os.listdir(dloaddir):
                if fnmatch.fnmatch (myfile, 'VNP04ANC.A{}*.h5'
                                    .format(datestr)):
                    fileList.append (myfile)

            # make sure files were found
            nfiles = len(fileList)
            if nfiles != 0:
                # if only one file was found which matched our date, then that
                # is the file we'll process.  if more than one was found, then
                # we have a problem as only one file is expected.
                if nfiles == 1:
                    found_vnp04anc = True
                    viirs_anc = dloaddir + '/' + fileList[0]
                else:
                    msg = ('Multiple LAADS VNP04ANC files found for doy {} '
                           'year {}'.format(doy, year))
                    logger.error(msg)
                    return ERROR

        else:
            # if only one file was found which matched our date, then that's
            # the file we'll process.  if more than one was found, then we
            # have a problem as only one file is expected.
            if nfiles == 1:
                found_vjx04anc = True
                viirs_anc = dloaddir + '/' + fileList[0]
            else:
                msg = ('Multiple LAADS VJX04ANC files found for doy {} year {}'
                       .format(doy, year))
                logger.error(msg)
                return ERROR

        # make sure at least one of the JPSS[1|2] or NPP files is present
        if not found_vjx04anc and not found_vnp04anc:
            msg = ('Neither the JPSS[1|2] nor NPP data is available for doy {} '
                   'year {}. Skipping this date.'.format(doy, year))
            logger.warning(msg)
            continue

        # determine the month and day (both 1-based) for this year/doy date
        # indx will be 0-based for the array
        if calendar.isleap(year):
            for indx in range(0, len(ldayEOM)):
                if doy <= ldayEOM[indx]:
                    break;
            month = indx+1
            day = doy - ldaySOM[indx] + 1
        else:
            for indx in range(0, len(rdayEOM)):
                if doy <= rdayEOM[indx]:
                    break;
            month = indx+1
            day = doy - rdaySOM[indx] + 1

        # generate the command-line arguments and executable for gap-filling
        # the VIIRS product (works the same for either VJX04ANC or VNP04ANC)
        cmdstr = ('gapfill_viirs_aux --viirs_aux {} --month {} --day {} '
                  '--year {}'.format(viirs_anc, month, day, year))
        msg = 'Executing {}'.format(cmdstr)
        logger.info(msg)
        (status, output) = subprocess.getstatusoutput (cmdstr)
        logger.info(output)
        exit_code = status >> 8
        if exit_code != 0:
            msg = ('Error running gap_fill for year {}, DOY {}: {}'
                   .format(year, doy, cmdstr))
            logger.error(msg)
            return ERROR

        # move the gap-filled file to the output directory
        msg = ('Moving downloaded file {} to {}'
               .format(viirs_anc, outputDir))
        logger.debug(msg)
        outanc = ('{}/{}'.format(outputDir, os.path.basename(viirs_anc)))
        if os.path.isfile(outanc):
            logger.debug('REMOVING ' + outanc)
            os.remove(outanc)
        shutil.move(viirs_anc, outputDir)

    # end for doy

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
#    this option is used for nightly updates.  If the gapfilled VJ104 data
#    products already exist for a particular year/doy, they will not be
#    reprocessed.
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
    msg = ('process or reprocess all LAADS data for this year or back to {}'
           .format(NPP_START_YEAR))
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
    auxdir = os.environ.get('LASRC_AUX_DIR')
    if auxdir is None:
        msg = 'LASRC_AUX_DIR environment variable not set... exiting'
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
    now = datetime.datetime.now()
    if today:
        msg = 'Processing LAADS data up to the most recent year and DOY.'
        logger.info(msg)        
        day_of_year = now.timetuple().tm_yday
        eyear = now.year
        if day_of_year <= 31:
            syear = eyear - 1
        else:
            syear = eyear

    elif quarterly:
        msg = 'Processing LAADS data back to {}'.format(NPP_START_YEAR)
        logger.info(msg)
        eyear = now.year
        syear = NPP_START_YEAR

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
    # determine the logging level. Default is INFO.
    espa_log_level = os.environ.get('ESPA_LOG_LEVEL')
    if espa_log_level == 'DEBUG':
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    # setup the default logger format and level. log to STDOUT.
    logging.basicConfig(format=('%(asctime)s.%(msecs)03d %(process)d'
                                ' %(levelname)-8s'
                                ' %(filename)s:%(lineno)d:'
                                '%(funcName)s -- %(message)s'),
                        datefmt='%Y-%m-%d %H:%M:%S',
                        level=log_level)
    sys.exit (main())
