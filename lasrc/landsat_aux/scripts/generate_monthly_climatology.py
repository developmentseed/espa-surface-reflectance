#!/usr/bin/env python

import sys      # system commands
import os       # misc commands
import shutil   # file copy/move/delete operations
import time     # for date/time conversions
import argparse # for command line aruguments
import logging  # for message logging
import glob     # list and manipulate filenames
import numpy
import fnmatch
import datetime
import calendar
from download_lads import downloadLads
from config_utils import retrieve_cfg
from api_interface import api_connect

from optparse import OptionParser
from osgeo import gdal
from osgeo import ogr
from osgeo import osr
from osgeo import gdal_array
from osgeo import gdalconst

##NOTE: For non-ESPA environments, the TOKEN needs to be defined.  This is
##the application token that is required for accessing the LAADS data
##https://ladsweb.modaps.eosdis.nasa.gov/tools-and-services/data-download-scripts/
TOKEN = None

# leap day start/end of month
ldaySOM = [ 1, 32, 61,  92, 122, 153, 183, 214, 245, 275, 306, 336]
ldayEOM = [31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366]

# regular day start/end of month
rdaySOM = [ 1, 32, 60,  91, 121, 152, 182, 213, 244, 274, 305, 335]
rdayEOM = [31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365]

# ignore divide by zero temporarily
numpy.seterr(divide='ignore')
numpy.seterr(invalid='ignore')

# error object used for handling fatal errors
ERROR = 1
SUCCESS = 0

# set the per-file cache in MB
gdal.SetConfigOption('GDAL_CACHEMAX', '256')

# do not establish a list of all the files in the directory of the file passed
# to GDALOpen()
gdal.SetConfigOption('GDAL_DISABLE_READDIR_ON_OPEN', 'TRUE')


def writeResultsEnvi(auxData, outputFilename, imageType=gdal.GDT_Byte,
    bandDesc="Monthly Avgs"):
    """
    Description: write the output data to the output ENVI file

    Args:
      auxData: array of data to write
      outputFilename: filename for writing the auxData (ENVI)
      imageType: data type of the output band
      bandDesc: description for the band names in the ENVI header file

    Returns: N/A
    """
    # if the monthly average file already exists, remove it
    if os.path.isfile(outputFilename):
        os.remove(outputFilename)

    # create the ENVI driver for output data
    driver = gdal.GetDriverByName('ENVI')

    # create the output dataset
    aux_dataset = driver.Create(outputFilename, xsize=auxData.shape[1],
                  ysize=auxData.shape[0], bands=1, eType=imageType)

    # get the output band
    aux_band = aux_dataset.GetRasterBand(1)
    aux_band.SetNoDataValue(0)
    aux_band.SetDescription(bandDesc)
    aux_band.WriteArray(auxData)

    aux_band = None
    aux_dataset = None


def addFiletoAvg(auxfile, init_totals, aux_total, aux_sum):
    """
    Description: addFiletoAvg will add the current auxiliary file/SDS to the
    specific SDS monthly average.

    Args:
      auxfile: name of the auxiliary file or SDS to open and add to the
               auxiliary totals
      init_totals: boolean to specify if the auxiliary totals need initialized
      aux_total: running total for the auxiliary data (uint64)

    Returns:
        False: error occurred while processing
        True: processing completed successfully
    """

    # initialize the logger and error objects
    logger = logging.getLogger(__name__)

    # open the current auxiliary file
    aux_dataset = gdal.Open(auxfile)
    if aux_dataset is None:
        logger.error('Failed to open auxiliary file: {}'.format(auxfile))
        return False

    # get the band from the file
    aux_band = aux_dataset.GetRasterBand(1)
    if aux_band is None:
        logger.error('Failed to open the band from {}'.format(auxfile))
        return False

    # read the auxiliary data
    aux_image = aux_band.ReadAsArray()

    # close the input bands and dataset
    aux_band = None
    aux_dataset = None

    # if this is the first file in the averages, then we need to initialize
    # the totals
    if init_totals == True:
        init_totals = False

        # array to hold the auxiliary totals for this dataset
        aux_total = numpy.zeros_like(aux_image, dtype=numpy.uint64)

        # array to hold the auxiliary good pixel count for this dataset
        aux_sum = numpy.zeros_like(aux_image, dtype=numpy.uint8)

    # add the current band to the total. fill values are already zero so no
    # special handling is needed.
    aux_total = aux_total + aux_image

    # add one to the good pixel count for any pixel that is not fill
    aux_sum = numpy.where(aux_image > 0, aux_sum+1, aux_sum)

    # free the image data
    aux_image = None

    return True, init_totals, aux_total, aux_sum


def downloadFiles(dloaddir, year, start_doy, end_doy, token):
    """
    Description: Download the VIIRS products for the specified year and DOY
    range. Download them to the specified download directory.

    Args:
      dloaddir: directory to download the VIIRS products
      year: year of the VIIRS product
      start_doy - end_doy: inclusive day of year date range for the year
      token: application token for the desired website

    Returns:
        ERROR: error occurred while processing
        SUCCESS: processing completed successfully
    """

    # initialize the logger and error objects
    logger = logging.getLogger(__name__)

    # make sure the download directory exists (and is cleaned up) or create
    # it recursively
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
            if os.path.isfile(name):
                os.remove(name)

    # loop through each day in the year and download the LAADS data
    for doy in range(start_doy, end_doy+1):
        # get the year + DOY string
        datestr = '{}{:03d}'.format(year, doy)

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

    return SUCCESS


#########
# generate the monthly averages
#########
def main ():
    # initialize the logger and error objects
    logger = logging.getLogger(__name__)

    # get the command line arguments
    parser = OptionParser()
    parser.add_option ('-y', '--aux_year', type='int', dest='aux_year',
        default=0, help='year for which to generate monthly averages of the '
                        'LAADS VIIRS data (default is the current year)')
    parser.add_option ('-m', '--aux_month', type='int', dest='aux_month',
        default=0, help='month (1-12) for which to generate monthly averages '
                        'of the LAADS VIIRS data (default is the previous '
                        'month)')

    (options, args) = parser.parse_args()
    aux_year = options.aux_year     # year
    aux_month = options.aux_month   # month

    # check the arguments and default to the current year and previous
    # month for processing if the year and/or month were not specified
    now = datetime.datetime.now()
    if aux_year == 0:
        aux_year = now.year

    if aux_month == 0:
        if now.month > 1:
            aux_month = now.month - 1
        else:
            aux_month = 12

    msg = ('Processing LAADS VIIRS monthly averages for year {} and month {}.'
           .format(aux_year, aux_month))
    logger.info(msg)

    # determine the auxiliary directory to store the data
    auxdir = os.environ.get('LASRC_AUX_DIR')
    if auxdir is None:
        msg = 'LASRC_AUX_DIR environment variable not set... exiting'
        logger.error(msg)
        return ERROR

    # make sure the auxiliary directory exists
    if not os.path.exists(auxdir):
        msg = 'LASRC_AUX_DIR {} does not exist... exiting'.format(auxdir)
        logger.error(msg)
        return ERROR

    # make sure the monthly averages directory exists or make it
    auxdir_out = ('{}/monthly_avgs'.format(auxdir))
    if not os.path.exists(auxdir_out):
        msg = ('Auxiliary directory for monthly averages {} does not exist. '
               'Creating...'.format(auxdir_out))
        logger.info(msg)
        os.mkdir(auxdir_out)

    # make sure the monthly averages year directory exists or make it
    auxdir_out = ('{}/monthly_avgs/{}'.format(auxdir, aux_year))
    if not os.path.exists(auxdir_out):
        msg = ('Auxiliary directory for monthly averages year {} does not '
               'exist. Creating...'.format(auxdir_out))
        logger.info(msg)
        os.mkdir(auxdir_out)

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

    # determine the DOY values included in the aux_year and aux_month, handling
    # leap years
    if calendar.isleap(aux_year):
        min_doy = ldaySOM[aux_month-1]
        max_doy = ldayEOM[aux_month-1]
    else:
        min_doy = rdaySOM[aux_month-1]
        max_doy = rdayEOM[aux_month-1]
    logger.info('DOY range to process: {} - {}'.format(min_doy, max_doy))

    # set the download directory in /tmp/lads_monthly
    dloaddir = '/tmp/lads_monthly/{}'.format(aux_year)

    # make sure the LAADS data exists for the specified year
    status = downloadFiles(dloaddir, aux_year, min_doy, max_doy, token)
    if status == ERROR:
        msg = ('Problems occurred while downloading LAADS data for year {}, '
               'date range {}-{}'.format(aux_year, min_doy, max_doy))
        logger.error(msg)
        return ERROR

    auxdir_in = dloaddir
    if not os.path.exists(auxdir_in):
        msg = ('Auxiliary directory {} does not exist... exiting'
               .format(auxdir_in))
        logger.error(msg)
        return ERROR

    msg = ('Auxiliary temp directory: {}'.format(auxdir_in))
    logger.info(msg)
    msg = ('Monthly averages output directory: {}'.format(auxdir_out))
    logger.info(msg)

    # loop through the year/month files in the auxiliary directory
    init_oz_totals = True
    init_wv_totals = True
    oz_total = None
    oz_count = None
    wv_total = None
    wv_count = None
    count = 0
    for doy in range(min_doy, max_doy+1):
        logger.info('Processing DOY {}'.format(doy))
        glob_pattern = ('{}/*4ANC.A{:04d}{:03d}.*.h5'
                        .format(auxdir_in, aux_year, doy))
        doy_file = glob.glob(glob_pattern)

        # if there are no files in this directory for the year/doy then
        # continue to the next doy. if there are more than one file, then
        # we have an issue that needs to be resolved (error).
        if len(doy_file) == 0:
            continue
        elif len(doy_file) > 1:
            msg = ('There is more than one file for {}. Something is wrong '
                   'in the auxiliary directory {}.'
                   .format(glob_pattern, auxdir_in))
            logger.error(msg)
            return ERROR
        logger.debug('{} DOY files were found'.format(len(doy_file)))
        logger.debug('Found {} DOY files: {}'
                     .format(len(doy_file), doy_file[0]))

        # generate the SDS names for the ozone and water vapor bands
        oz_sds = ('HDF5:\"{}\"://HDFEOS/GRIDS/VIIRS_CMG/Data_Fields/'
                  'Coarse_Resolution_Ozone'.format(doy_file[0]))
        wv_sds = ('HDF5:\"{}\"://HDFEOS/GRIDS/VIIRS_CMG/Data_Fields/'
                  'Coarse_Resolution_Water_Vapor'.format(doy_file[0]))

        # process the current file and add the SDS data to the overall total
        # for ozone and water vapor
        # if this is the first file in the month then we need to setup and
        # initialize the ozone and water vapor totals
        count = count + 1
        [status, init_oz_totals, oz_total, oz_count] =  \
            addFiletoAvg(oz_sds, init_oz_totals, oz_total, oz_count)
        if not status:
            msg = ('An error occurred adding {} to the overall total.'
                   .format(oz_sds))
            logger.error(msg)
            return ERROR

        [status, init_wv_totals, wv_total, wv_count] =  \
            addFiletoAvg(wv_sds, init_wv_totals, wv_total, wv_count)
        if not status:
            msg = ('An error occurred adding {} to the overall total.'
                   .format(wv_sds))
            logger.error(msg)
            return ERROR
        logger.debug('Count: {}'.format(count))

    # make sure there are auxiliary files for this month
    if count == 0:
        msg = ('No auxiliary files were found for {}. Something is wrong '
               'in the auxiliary directory {}.'.format(glob_pattern, auxdir_in))
        logger.error(msg)
        return ERROR

    # make sure the ozone and water vapor arrays are valid
    if oz_total is None:
        msg = ('Ozone total for {} is None. Something is wrong '
               'in the auxiliary directory {}.'.format(glob_pattern, auxdir_in))
        logger.error(msg)
        return ERROR

    if wv_total is None:
        msg = ('Water vapor total for {} is None. Something is wrong '
               'in the auxiliary directory {}.'.format(glob_pattern, auxdir_in))
        logger.error(msg)
        return ERROR

    # determine the averages and handle divide by zero
    oz_total = numpy.where(oz_count > 0, oz_total / oz_count, 0)
    wv_total = numpy.where(wv_count > 0, wv_total / wv_count, 0)

    # write data to the output ENVI File
    basename = 'monthly_avg_oz_{:4}_{:02}'.format(aux_year, aux_month)
    outname = '{}/{}.img'.format(auxdir_out, basename)
    writeResultsEnvi(oz_total, outname, gdal.GDT_Byte, basename)
    basename = 'monthly_avg_wv_{:4}_{:02}'.format(aux_year, aux_month)
    outname = '{}/{}.img'.format(auxdir_out, basename)
    writeResultsEnvi(wv_total, outname, gdal.GDT_UInt16, basename)

    # clean up the temporary download directory
    for myfile in os.listdir(dloaddir):
        name = os.path.join(dloaddir, myfile)
        if os.path.isfile(name):
            os.remove(name)

    # successful completion
    msg = ('Successful completion')
    logger.info(msg)
    return SUCCESS


if __name__ == "__main__":
    # Determine the logging level. Default is INFO.
    espa_log_level = os.environ.get('ESPA_LOG_LEVEL')
    if espa_log_level == 'DEBUG':
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    # Setup the default logger format and level. Log to STDOUT.
    logging.basicConfig(format=('%(asctime)s.%(msecs)03d %(process)d'
                                ' %(levelname)-8s'
                                ' %(filename)s:%(lineno)d:'
                                '%(funcName)s -- %(message)s'),
                        datefmt='%Y-%m-%d %H:%M:%S',
                        level=log_level)
    sys.exit(main())
