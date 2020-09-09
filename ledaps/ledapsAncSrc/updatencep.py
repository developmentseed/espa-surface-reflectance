#!/usr/bin/env python

############################################################################
# Updated on 12/27/2012 by Gail Schmidt, USGS EROS
#   Modified the wget retrievals to limit the number of retries to 5 in the
#   case of a download or connection problem.
# Updated on 10/28/2014 by Gail Schmidt, USGS EROS
#   Changed the ANC_PATH environment variable to LEDAPS_AUX_DIR to be more
#   consistent with the Landsat8 auxiliary directory name.
# Updated on 9/9/2015 by Gail Schmidt, USGS EROS
#   Modified the wget calls to retry up to 5 times if the download fails.
############################################################################
import sys
import os.path
import ftplib
import datetime
import subprocess
import os
import re
import time
import subprocess
from optparse import OptionParser
import logging

# Global static variables
ERROR = 1
SUCCESS = 0
START_YEAR = 1978

############################################################################
# Description: isLeapYear will determine if the specified year is a leap
# year.
#
# Inputs:
#   year - year to determine if it is a leap year (integer)
#
# Returns:
#     True - yes, this is a leap year
#     False - no, this is not a leap year
#
# Notes:
############################################################################
def isLeapYear (year):
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


############################################################################
# Description: getNcepData download the air temp, surface pressure, and
# precipitable water netCDF files for the desired year, then process the
# netCDF file into individual daily HDF files containing the air temp,
# surface pressure, and precipitable water.
#
# Inputs:
#   ancdir - name of the base LEDAPS ancillary directory which contains
#            the REANALYSIS directory
#   year - year of NCEP data to be downloaded and processed (integer)
#
# Returns:
#     ERROR - error occurred while processing
#     SUCCESS - processing completed successfully
#
# Notes:
############################################################################
def getNcepData (ancdir, year):
    # set up the names of the NCEP netCDF files to be downloaded for the
    # specified year
    pressureFile = "slp.%d.nc" % year
    waterFile = "pr_wtr.eatm.%d.nc" % year
    airFile = "air.sig995.%d.nc" % year
    pressureFileSource = '/tmp/ncep/' + pressureFile
    waterFileSource = '/tmp/ncep/' + waterFile
    airFileSource = '/tmp/ncep/' + airFile
    
    # cleanup previously downloaded annual netCDF files
    if os.path.isfile(airFileSource):
        os.remove(airFileSource)
    if os.path.isfile(pressureFileSource):
        os.remove(pressureFileSource)
    if os.path.isfile(waterFileSource):
        os.remove(waterFileSource)

    logger = logging.getLogger(__name__)

    # download the air temp, surface pressure, and precipitable water files
    # for the specified year to /tmp/ncep
    status = downloadNcep(pressureFile, '/tmp/ncep')
    if status == ERROR:
        logger.error('could not download pressureFile data: {0}'
                     .format(pressureFile))
        return ERROR
        
    status = downloadNcep(waterFile, '/tmp/ncep')
    if status == ERROR:
        logger.error('could not download waterFile data: {0}'
                     .format(waterFile))
        return ERROR

    status = downloadNcep(airFile, '/tmp/ncep')
    if status == ERROR:
        logger.error('could not download airFile data: {0}'.format(airFile))
        return ERROR
    
    # use the downloaded netCDF files to create the daily HDF files needed
    # for LEDAPS processing
    outputDest = ancdir + '/REANALYSIS/RE_' + str(year)
    status = executeNcep(pressureFileSource, outputDest, year, True)
    if status == ERROR:
        logger.error('could not process pressureFile: {0}'
                     .format(pressureFileSource))
        return ERROR

    status = executeNcep(waterFileSource, outputDest, year, False)
    if status == ERROR:
        logger.error('could not process waterFile: {0}'
                     .format(waterFileSource))
        return ERROR

    status = executeNcep(airFileSource, outputDest, year, False)
    if status == ERROR:
        logger.error('could not process airFile: {0}'.format(airFileSource))
        return ERROR

    # cleanup the downloaded annual netCDF files
    os.remove(airFileSource)
    os.remove(pressureFileSource)
    os.remove(waterFileSource)

    return SUCCESS


############################################################################
# Description: executeNcep will run the 'ncep' executable to produce the
# HDF files for the specified year and they will be written to the outputdir.
# If the specified year is the current year, then the days processed will
# only be up through today.  If the outputdir directory does not exist, then
# it is made before downloading.
#
# Inputs:
#   fullinputpath - full path and filename of the NCEP REANALYSIS file for
#                   the specified year
#   outputdir - output directory name for the generated daily NCEP HDF files
#   year - year of NCEP data to be processed (integer)
#   clean - should the HDF file be cleaned if it exists?
#
# Returns: nothing
#     ERROR - error occurred while reading one of the NCEP input files
#     SUCCESS - processing completed successfully
#
# Notes:
#   If ncep is not successful processing a particular DOY, then a warning
#   message is printed and processing continues.
############################################################################
def executeNcep (fullinputpath, outputdir, year, clean):
    logger = logging.getLogger(__name__)

    # if the specified year is the current year, only process up through
    # today otherwise process through all the days in the year
    now = datetime.datetime.now()
    if year == now.year:
        day_of_year = now.timetuple().tm_yday
    else:
        if isLeapYear (year) == True:
            day_of_year = 366   
        else:
            day_of_year = 365

    # make sure the output directory exists or create it recursively
    if not os.path.exists(outputdir):
        logger.warn('{0} does not exist... creating'.format(outputdir))
        os.makedirs(outputdir, 0o777)

    # loop through each day in the year and process the NCEP REANALYSIS HDF
    # file for each day
    for doy in range(1, day_of_year + 1):
        if doy < 10:
            dayofyear = '00' + str(doy)
        elif 9 < doy < 100:
            dayofyear = '0' + str(doy)
        else:
            dayofyear = str(doy)

        # generate the full path for the output file to be processed. if the
        # output file already exists, then remove it.  if processing fails,
        # then remove the output file.
        fulloutputpath = "%s/REANALYSIS_%d%s.hdf" % (outputdir, year, dayofyear)
        if clean == True and os.path.isfile(fulloutputpath):
            os.remove(fulloutputpath)
        cmdstr = 'ncep_repackage %s %s %s' % (fullinputpath,fulloutputpath,doy)
        logger.info('\nExecuting {0}'.format(cmdstr))
        (status, output) = subprocess.getstatusoutput (cmdstr)
        logger.info(output)
        exit_code = status >> 8
        if exit_code == 157:  # return value of -99 (2s complement of 157)
            logger.error('Input file for year {0}, DOY {1} is not'
                         ' readable.  Stop processing since this same file is'
                         ' used for all days in the current year.'
                         .format(year, doy))
            return ERROR
        elif exit_code != 0:
            logger.warn('error running ncep for year {0}, DOY {1}.  '
                        'Processing will continue ...'.format(year, doy))
            if os.path.isfile(fulloutputpath):
                os.remove(fulloutputpath)

    # successful processing
    return SUCCESS


############################################################################
# Description: cleanNcepTargetDir will regressively clean the NCEP REANALYSIS
# HDF files from the NCEP directory for the specified year.
#
# Inputs:
#   ancdir - name of the base LEDAPS ancillary directory which contains
#            the REANALYSIS directory
#   year - year of NCEP REANALYSIS HDF data to be removed (integer)
#
# Returns: nothing
#
# Notes:
#   If the specified directory does not exist, then it won't get cleaned.
############################################################################
def cleanNcepTargetDir (ancdir, year):
    mydir = "%s/REANALYSIS/RE_%d" % (ancdir, year)
    logger = logging.getLogger(__name__)  # Obtain logger for this module.
    logger.info('Cleaning NCEP target directory: {0}'.format(mydir))
    regex = re.compile('REANALYSIS_' + str(year) + '\d*.hdf')
    if os.path.exists(mydir):
        # look at each file in the specified directory
        for myfile in os.listdir(mydir):
            # if the file matches our regular expression for NCEP REANALYSIS
            # HDF files then remove it
            if regex.search(myfile):
                name = os.path.join(mydir, myfile)
                try:
                    os.remove(name)
                    # logger.info('Removed {0}'.format(name))
                except:
                    logger.error('Could not remove {0}'.format(name))


############################################################################
# Description: downloadNcep will retrieve the specified sourcefilename
# from the NCEP REANALYSIS ftp site and download to the desired destination.
# If the destination directory does not exist, then it is made before
# downloading.
#
# Inputs:
#   sourcefilename - name of the NCEP file to pull from the ftp site
#   destination - name of the directory on the local system to download the
#                 NCEP file
#
# Returns:
#     ERROR - error occurred while processing
#     SUCCESS - processing completed successfully
#
# Notes:
#   We could use the Python ftplib or urllib modules, however the wget
#   function is pretty short and sweet, so we'll stick with wget.
############################################################################
def downloadNcep (sourcefilename, destination):
    logger = logging.getLogger(__name__)  # Get logger for the module.
    logger.info('Retrieving {0} to {1}'.format(sourcefilename, destination))
    url = 'ftp://ftp.cdc.noaa.gov/Datasets/ncep.reanalysis/surface/%s' %  \
        sourcefilename

    # make sure the path exists or create it recursively
    if not os.path.exists(destination):
        logger.info('{0} does not exist... creating'.format(destination))
        os.makedirs(destination, 0o777)

    # make sure the file to be downloaded doesn't exist, remove it if it does
    localfile = '%s/%s' % (destination, sourcefilename)
    if os.path.isfile(localfile):
        os.remove(localfile)

    # get the file from the ftp site and download it to the destination.
    # if there is a problem with the connection, then retry up to 5 times
    # and wait 60 seconds between retries.  Retry connection refused errors.
    # Note: if you don't like the wget output, --quiet can be used to
    # minimize the output info.
    cmd = 'wget --tries=5 %s' % url
    retval = subprocess.call(cmd, shell=True, cwd=destination)

    # make sure the wget was successful or retry up to 5 more times and sleep
    # in between
    if retval:
        retry_count = 1
        while ((retry_count <= 5) and (retval)):
            time.sleep(60)
            logger.info('Retry {0} of wget for {1}'.format(retry_count, url))
            retval = subprocess.call(cmd, shell=True, cwd=destination)
            retry_count += 1

        if retval:
            logger.info('unsuccessful download of {0} (retried 5 times)'
                        .format(url))

    logger.info('successful download of {0} to {1}'.format(url, destination))
    return SUCCESS


############################################################################
# Description: Main routine which grabs the command-line arguments, determines
# which years/days of data need to be processed, then processes the user-
# specified dates of NCEP REANALYSIS data.
#
# Developer(s):
#     David Hill, USGS EROS - Original development
#     Gail Schmidt, USGS EROS
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
#    previous year if the DOY is within the first month of the year)
# 3. --quarterly will process the data for today all the way back to the
#    earliest year so that any updated NCEP files are picked up and processed.
# 4. Existing NCEP HDF files are removed before processing data for that year
#    and DOY, but only if the downloaded ancillary data exists for that date.
############################################################################
def main ():
    # get the command line arguments
    parser = OptionParser()
    parser.add_option ("-s", "--start_year", type="int", dest="syear",
        default=0, help="year for which to start pulling NCEP data")
    parser.add_option ("-e", "--end_year", type="int", dest="eyear",
        default=0, help="last year for which to pull NCEP data")
    parser.add_option ("--today", dest="today", default=False,
        action="store_true", help="process NCEP data for the most recent year")
    msg = "reprocess all NCEP data from today back to %d" % START_YEAR
    parser.add_option ("--quarterly", dest="quarterly", default=False,
        action="store_true", help=msg)

    (options, args) = parser.parse_args()
    syear = options.syear           # starting year
    eyear = options.eyear           # ending year
    today = options.today           # process most recent year of data
    quarterly = options.quarterly   # process today back to START_YEAR

    logger = logging.getLogger(__name__)  # Get the logger for this module.
    # check the arguments
    if (today == False) and (quarterly == False) and \
       (syear == 0 or eyear == 0):
        logger.error('Invalid command line argument combination.  Type --help'
                     ' for more information')
        return ERROR

    # determine the ancillary directory to store the data
    ancdir = os.environ.get('LEDAPS_AUX_DIR')
    if ancdir == None:
        logger.error('LEDAPS_AUX_DIR environment variable not set... exiting')
        return ERROR

    # if processing today then process the current year.  if the current
    # DOY is within the first month, then process the previous year as well
    # to make sure we have all the recently available data processed.
    if today:
        logger.info('Processing NCEP data for the most recent year')
        now = datetime.datetime.now()
        day_of_year = now.timetuple().tm_yday
        eyear = now.year
        if day_of_year <= 31:
            syear = now.year - 1
        else:
            syear = now.year

    elif quarterly:
        logger.info('Processing NCEP data back to {0}'.format(START_YEAR))
        now = datetime.datetime.now()
        day_of_year = now.timetuple().tm_yday
        eyear = now.year
        syear = START_YEAR

    logger.info('Processing NCEP data for {0} - {1}'.format(syear, eyear))
    for yr in range(syear, eyear+1):
        logger.info('Processing year: {0}'.format(yr))
        status = getNcepData(ancdir, yr)
        if status == ERROR:
            logger.warn('Problems occurred while processing NCEP'
                        ' data for year {0}.  Processing will continue.'
                        .format(yr))

    logger.info('NCEP processing complete.')
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
