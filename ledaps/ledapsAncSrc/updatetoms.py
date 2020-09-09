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
import os
import fnmatch
import datetime
import subprocess
import re
import time
import subprocess
import logging
from optparse import OptionParser

# Global static variables
ERROR = 1
SUCCESS = 0
START_YEAR = 1978      # quarterly processing will reprocess back to the
                       # start of the TOMS data to make sure all data is
                       # up to date

############################################################################
# Datasource object to identify the instrument type and URL
############################################################################
class Datasource:
    type = None
    url = None

    def __init__(self, type, url):
        self.type = type       # instrument type
        self.url = url         # URL


############################################################################
# DatasourceResolver class
############################################################################
class DatasourceResolver:
    # Specify the base location for the TOMS data as well as the
    # correct subdirectories for each of the instrument-specific ozone
    # products
    SERVER_URL = 'https://acd-ext.gsfc.nasa.gov/anonftp/toms'
    NIMBUS = '/nimbus7/data/ozone/Y'
    EARTHPROBE = '/eptoms/data/ozone/Y'
    METEOR3 = '/meteor3/data/ozone/Y'
    OMI = '/omi/data/ozone/Y'
    
    def __init__(self):
        pass

    #######################################################################
    # Description: Resolve which instrument will be used for the specified
    # year.  Identify the appropriate URL for downloading data for that
    # instrument, and put that data source object on the list.
    #
    # Inputs:
    #   year - year of desired ozone data
    #   DOY - download data up through the DOY
    #
    # Returns:
    #   None - error resolving the instrument and associated URL for
    #          the specified year
    #   urlList - List of URL(s) to pull the ozone data from for the
    #         specified year.  The primary data source is first, followed
    #         by the backup data source in the event the desired date does
    #         not exist on the primary URL.
    #
    # Notes:
    #######################################################################
    def resolve(self, year, DOY):
        logger = logging.getLogger(__name__)  # Get logger for the module.
        # use NIMBUS data for 1978-1990
        if year in range(1978, 1991):
            dsList = self.buildURL('NIMBUS', self.SERVER_URL, self.NIMBUS, year,
                                   DOY)
            if dsList is None:
                logger.warn('Could not resolve NIMBUS datasource for year, '
                            'DOY: {0}/{1}'.format(year, DOY))
                return None

        # use METEOR3 data for 1991-1993, with NIMBUS as the backup
        elif year in range(1991, 1994):
            dsList = self.buildURL('METEOR3', self.SERVER_URL, self.METEOR3,
                                   year, DOY)
            if dsList is None:
                logger.warn('Could not resolve METEOR3 datasource for year, '
                            'DOY: {0}/{1}'.format(year, DOY))
                return None

            dsList2 = self.buildURL('NIMBUS', self.SERVER_URL, self.NIMBUS,
                                   year, DOY)
            if dsList2 is None:
                logger.warn('Could not resolve NIMBUS datasource for year, '
                            'DOY: {0}/{1}'.format(year, DOY))
            else:
                dsList.extend(dsList2)


        # use METEOR3 data for 1994
        elif year == 1994:
            dsList = self.buildURL('METEOR3', self.SERVER_URL, self.METEOR3,
                                   year, DOY)
            if dsList is None:
                logger.warn('Could not resolve METEOR3 datasource for year, '
                            'DOY: {0}/{1}'.format(year, DOY))
                return None

        # use EARTHPROBE data for 1996-2003
        elif year in range(1996, 2004):
            dsList = self.buildURL('EARTHPROBE', self.SERVER_URL,
                                   self.EARTHPROBE, year, DOY)
            if dsList is None:
                logger.warn('Could not resolve EARTHPROBE datasource for year, '
                            'DOY: {0}/{1}'.format(year, DOY))
                return None

        # use OMI data for 2004-2005, with EARTHPROBE as the backup
        elif year in range(2004, 2006):
            dsList = self.buildURL('OMI', self.SERVER_URL, self.OMI, year, DOY)
            if dsList is None:
                logger.warn('Could not resolve EARTHPROBE datasource for year, '
                            'DOY: {0}/{1}'.format(year, DOY))
                return None

            dsList2 = self.buildURL('EARTHPROBE', self.SERVER_URL,
                self.EARTHPROBE, year, DOY)
            if dsList2 is None:
                logger.warn('Could not resolve EARTHPROBE datasource for year, '
                            'DOY: {0}/{1}'.format(year, DOY))
            else:
                dsList.extend(dsList2)

        # use OMI for any years beyond 2006
        elif year >= 2006:
            dsList = self.buildURL('OMI', self.SERVER_URL, self.OMI, year, DOY)
            if dsList is None:
                logger.warn('Could not resolve OMI datasource for year, DOY: '
                            '{0}/{1}'.format(year, DOY))
                return None

        # year requested does not have TOMS ozone data
        else:
            logger.warn('Could not resolve a datasource for year, DOY: {0}/{1}'
                        .format(year, DOY))
            return None

        return dsList


    #######################################################################
    # Description: buildURL builds the URL for the specific instrument
    # which will be used for the specified year.
    #
    # Inputs:
    #   type - instrument that will be used (NIMBUS, EARTHPROBE, METEOR3,
    #          OMI)
    #   serverUrl - portion of the URL for the server location
    #   basePath - base portion of the URL that is instrument-specific
    #   year - year of desired ozone data
    #   DOY - download data up through the DOY
    #
    # Returns:
    #   None - error resolving the instrument and associated URL for
    #          the specified year
    #   urlList - Final list of URL locations to download
    #
    # Notes:
    #######################################################################
    def buildURL (self, type, serverUrl, basePath, year, DOY):
        urlList = []     # create empty data source list

        # loop through each day in the year and download the TOMS data
        for doy in range(1, DOY + 1):
            # get the month/day for the current DOY
            currday = datetime.datetime(year, 1, 1) + datetime.timedelta(doy-1)
            datestr = currday.strftime("%Y%m%d")

            # build the filename regular expression for the specified
            # instrument type, year, and DOY
            if type == 'NIMBUS':
                name = 'L3_ozone_n7t_%s.txt' % datestr
            elif type == 'EARTHPROBE':
                name = 'L3_ozone_epc_%s.txt' % datestr
            elif type == 'METEOR3':
                name = 'L3_ozone_m3t_%s.txt' % datestr
            elif type == 'OMI':
                name = 'L3_ozone_omi_%s.txt' % datestr
            else:
                logger.warn('Could not categorize datasource for: {0}'
                            .format(type))
                return None

            # build the URL with the information provided
            url = serverUrl + basePath + str(year) + '/' + name
            urlList.append(url)

        # return the URL list
        return urlList 
############################################################################
# End DatasourceResolver class
############################################################################

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
# Description: cleanTomsTargetDir will regressively clean the TOMS HDF files
# from the TOMS directory for the specified year.
#
# Inputs:
#   ancdir - name of the base LEDAPS ancillary directory which contains
#            the TOMS directory
#   year - year of TOMS ozone HDF data to be removed (integer)
#
# Returns: nothing
#
# Notes:
#   If the specified directory does not exist, then it won't get cleaned.
############################################################################
def cleanTomsTargetDir (ancdir, year):
    mydir = "%s/EP_TOMS/ozone_%d" % (ancdir, year)
    logger.info('Cleaning TOMS target directory: {0}'.format(mydir))
    regex = re.compile('TOMS_' + str(year) + '\d*.hdf')
    if os.path.exists(mydir):
        # look at each file in the specified directory
        for myfile in os.listdir(mydir):
            # if the file matches our regular expression for TOMS ozone
            # HDF files then remove it
            if regex.search(myfile):
                name = os.path.join(mydir, myfile)
                try:
                    os.remove(name)
                    # logger.info('Removed {0}'.format(name))
                except:
                    logger.error('Could not remove {0}'.format(name))


############################################################################
# Description: getOzoneSource determines the source/instrument used to obtain
# this TOMS ozone data file.
#
# Inputs:
#   filename - name of the ozone file
#
# Returns:
#     None - error occurred while processing
#     ozoneSource - source of the ozone file (METEOR3, EARTHPROBE, NIMBUS7, OMI)
#
# Notes:
############################################################################
def getOzoneSource (filename):
    # Extract the instrument type from the filename.  Files look like
    # L3_ozone_XXX_YYYYMMDD.txt where XXX = either epc (EARTHPROBE),
    # omi (OMI), n7t (NIMBUS7), or m3t (METEOR3).
    parts = filename.split('_')
    inst = parts[2]     # type of instrument

    # Now we determine the datasource for the file we're dealing with
    if inst == "m3t":
        ozoneSource = 'METEOR3'
    elif inst == "epc":
        ozoneSource = 'EARTHPROBE'
    elif inst == "n7t":
        ozoneSource = 'NIMBUS7'
    elif inst == "omi":
        ozoneSource = 'OMI'
    else:
        logger.warn('Error classifying the downloaded data for: {0} ...'
                    ' unknown source type ({1})'.format(filename, inst))
        return None

    # successful processing
    return ozoneSource


############################################################################
# Description: resolveFile will look at the list of available files and
# grab the highest priority file to be used for processing in the order of
# OMI, EARTHPROBE, METEOR3, and NIMBUS7.
#
# Inputs:
#   fileList - list of available ozone files for the current day and year
#
# Returns:
#     None - none of the files matched our known instruments
#     filename - priority file to be processed
#
# Notes:
############################################################################
def resolveFile (fileList):
    omiregex = re.compile('.*_omi_\d*.txt')
    earthproberegex = re.compile('.*_epc_\d*.txt')
    meteor3regex = re.compile('.*_m3t_\d*.txt')
    nimbusregex = re.compile('.*_n7t_\d*.txt')

    # loop through the files, looping for OMI, EARTHPROBE, METEOR3, and NIMBUS7
    # files in that order.  return the first one found as the file to be
    # processed.
    for myfile in fileList:
        if omiregex.search(myfile):
            return myfile

    for myfile in fileList:
        if earthproberegex.search(myfile):
            return myfile

    for myfile in fileList:
        if meteor3regex.search(myfile):
            return myfile

    for myfile in fileList:
        if nimbusregex.search(myfile):
            return myfile

    # if none of the files match our known instruments then return None
    return None


############################################################################
# Description: downloadToms will retrieve the files for the specified year
# from the TOMS http site and download to the desired destination.  If the
# destination directory does not exist, then it is made before downloading.
# Existing files in the download directory are removed/cleaned.
#
# Inputs:
#   year - year of data to download (integer)
#   DOY - download data up through the DOY (integer)
#   destination - name of the directory on the local system to download the
#                 TOMS files
#
# Returns:
#     ERROR - error occurred while processing
#     SUCCESS - processing completed successfully
#
# Notes:
############################################################################
def downloadToms (year, DOY, destination):
    logger = logging.getLogger(__name__)  # Get logger for the module.
    # make sure the download directory exists (and is cleaned up) or create
    # it recursively
    if not os.path.exists(destination):
        logger.info('{0} does not exist... creating'.format(destination))
        os.makedirs(destination, 0o777)
    else:
        # directory already exists and possibly has files in it.  any old
        # files need to be cleaned up
        logger.info('Cleaning download directory: {0}'.format(destination))
        for myfile in os.listdir(destination):
            name = os.path.join(destination, myfile)
            if not os.path.isdir(name):
                os.remove(name)

    # obtain the list of URL(s) for our particular date, up through the DOY
    urlList = DatasourceResolver().resolve(year, DOY)
    if urlList == None:
        logger.warn('TOMS URL could not be resolved for year {0} up through '
                    'DOY {1}. Processing will continue ...'.format(year, DOY))
        return ERROR

    # download the data for the current year from the list of URLs.
    # if there is a problem with the connection, then retry up to 5 times.
    # Note: if you don't like the wget output, --quiet can be used to minimize
    # the output info.  wget will return a nonzero value if there was a problem.
    logger.info('Downloading data for year {0} to: {1}'
                .format(year, destination))

    for url in urlList:
        logger.info('Retrieving {0} to {1}'.format(url, destination))
        cmd = 'wget --tries=5 %s' % url 
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
                logger.warn('unsuccessful download of {0} (retried 5 times)'
                            .format(url))

    return SUCCESS


############################################################################
# Description: getTomsData downloads the daily ozone data files for the
# desired year, then processes the text files into individual daily HDF
# files containing the ozone.
#
# Inputs:
#   ancdir - name of the base LEDAPS ancillary directory which contains
#            the TOMS directory
#   year - year of TOMS data to be downloaded and processed (integer)
#
# Returns:
#     ERROR - error occurred while processing
#     SUCCESS - processing completed successfully
#
# Notes:
############################################################################
def getTomsData (ancdir, year):
    logger = logging.getLogger(__name__)  # Obtain logger for this module.

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

    # download the daily ozone files for the specified year to /tmp/ep_toms
    dloaddir = "/tmp/ep_toms/%d" % year
    status = downloadToms (year, day_of_year, dloaddir)
    if status == ERROR:
        # warning message already printed
        return ERROR

    # determine the directory for the output ancillary data files to be
    # processed.  create the directory if it doesn't exist.
    outputDir = "%s/EP_TOMS/ozone_%d" % (ancdir, year)
    if not os.path.exists(outputDir):
        logger.info('{0} does not exist... creating'.format(outputDir))
        os.makedirs(outputDir, 0o777)

    # loop through each day in the year and process the TOMS data
    for doy in range(1, day_of_year + 1):
        # get the month/day for the current DOY
        currday = datetime.datetime (year, 1, 1) + datetime.timedelta (doy-1)
        datestr = currday.strftime("%Y%m%d")

        # find all the files for the current day
        fileList = []    # create empty list to store files matching date
        for myfile in os.listdir(dloaddir):
            if fnmatch.fnmatch (myfile, '*' + datestr + ".txt"):
                fileList.append(myfile)

        # make sure files were found or print a warning
        nfiles = len(fileList)
        if nfiles == 0:
            logger.warn('no TOMS data available for doy {0} year'
                        ' {1} ({2}). processing will continue ...'
                        .format(doy, year, datestr))
            continue
        else:
            # if only one file was found which matched our date, then that's
            # the file we'll process.  if more than one was found, then the
            # file needs to be resolved based on instrument type.
            if nfiles == 1:
                tomsfile = fileList[0]
            else:
                tomsfile = resolveFile (fileList)
                if tomsfile == None:
                    logger.warn('error resolving the list of TOMS'
                                ' files to process. processing will continue ...')
                    continue

            # get the ozone source
            ozoneSource = getOzoneSource (tomsfile)
            if ozoneSource == None:
                logger.warn('error determining the ozone source for'
                            ' {0}. Processing will continue ...'
                            .format(tomsfile))
                continue

            # generate the full path for the input and output file to be
            # processed. if the output file already exists, then remove it.
            fullOutputPath = "%s/TOMS_%d%03d.hdf" % (outputDir, year, doy)
            fullInputPath = os.path.join(dloaddir, tomsfile)
            if os.path.isfile(fullOutputPath):
                os.remove(fullOutputPath)
            cmdstr = 'convert_ozone %s %s %s' % (fullInputPath, fullOutputPath,
                ozoneSource)
            logger.info('Executing {0}'.format(cmdstr))
            (status, output) = subprocess.getstatusoutput (cmdstr)
            logger.info(output)
            exit_code = status >> 8
            if exit_code != 0:
                logger.warn('error running convert_ozone for year'
                            ' {0}, DOY {1}.  processing will continue ...'
                            .format(year, doy))
    # end for doy

    # remove the files downloaded to the temporary directory
    logger.info('Removing downloaded files')
    for myfile in os.listdir(dloaddir):
        name = os.path.join(dloaddir, myfile)
        os.remove(name)

    return SUCCESS


############################################################################
# Description: Main routine which grabs the command-line arguments, determines
# which years/days of data need to be processed, then processes the user-
# specified dates of TOMS data.
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
#    earliest year so that any updated TOMS files are picked up and
#    processed.
# 4. Existing TOMS HDF files are removed before processing data for that
#    year and DOY, but only if the downloaded ancillary data exists for that
#    date.
############################################################################
def main ():
    # get the command line arguments
    parser = OptionParser()
    parser.add_option ("-s", "--start_year", type="int", dest="syear",
        default=0, help="year for which to start pulling TOMS data")
    parser.add_option ("-e", "--end_year", type="int", dest="eyear",
        default=0, help="last year for which to pull TOMS data")
    parser.add_option ("--today", dest="today", default=False,
        action="store_true",
        help="process TOMS data for the most recent year")
    msg = "reprocess all TOMS data from today back to %d" % START_YEAR
    parser.add_option ("--quarterly", dest="quarterly", default=False,
        action="store_true", help=msg)

    (options, args) = parser.parse_args()
    syear = int(options.syear)      # starting year
    eyear = int(options.eyear)      # ending year
    today = options.today           # process most recent year of data
    quarterly = options.quarterly   # process today back to START_YEAR

    logger = logging.getLogger(__name__)  # Get logger for the module.

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
        logger.info('Processing TOMS data for the most recent year')
        now = datetime.datetime.now()
        day_of_year = now.timetuple().tm_yday
        eyear = now.year
        if day_of_year <= 31:
            syear = now.year - 1
        else:
            syear = now.year

    elif quarterly:
        logger.info('Processing TOMS data back to {0}'.format(START_YEAR))
        now = datetime.datetime.now()
        day_of_year = now.timetuple().tm_yday
        eyear = now.year
        syear = START_YEAR

    logger.info('Processing TOMS data for {0} - {1}'.format(syear, eyear))
    for yr in range(syear, eyear+1):
        logger.info('Processing year: {0}'.format(yr))
        status = getTomsData(ancdir, yr)
        if status == ERROR:
            logger.warn('Problems occurred while processing TOMS data for'
                        ' year {0}.  Processing will continue.'
                        .format(yr))

    logger.info('TOMS processing complete.')
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
