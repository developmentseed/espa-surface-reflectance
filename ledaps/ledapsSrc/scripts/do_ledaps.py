#! /usr/bin/env python
import sys
import os
import re
import subprocess
import datetime
import logging
from optparse import OptionParser

ERROR = 1
SUCCESS = 0


############################################################################
# Description: isLeapYear will determine if the specified year is a leap
# year.
#
# Inputs:
#   year - year to determine if it is a leap year (integer)
#
# Returns:
#     1 - yes, this is a leap year
#     0 - no, this is not a leap year
#
# Notes:
############################################################################
def isLeapYear(year):
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


#############################################################################
# Created on November 13, 2012 by Gail Schmidt, USGS/EROS
# Created Python script so that lnd* application status values can be checked
# for successful completion and failures can be flagged.
#
# Usage: do_ledaps.py --help prints the help message
############################################################################
class Ledaps():

    def __init__(self):
        pass

    ########################################################################
    # Description: findAncillary will parse the ANC_PATH directory and verify
    # that the required NCEP REANALYSIS and EP/TOMS ancillary products are
    # available for the specified year and DOY.  If the DOY is not specified,
    # then the entire year will be processed.
    #
    # Inputs:
    #   year - which year to look for ancillary data (integer)
    #   doy - which DOY to look for ancillary data (integer)
    #         (default - parse all days in the specified year)
    #
    # Returns:
    #     None - error occurred while processing the specified year/doy
    #     list of True/False - current value is True if the ancillary data is
    #         available for the current year/doy, False if the ancillary data
    #         does not exist;  if the DOY was specified, then the list will
    #         only have one value
    #
    # Notes:
    #     ANC_PATH points to the base LEDAPS ancillary directory which
    #         contains the REANALYSIS and EP/TOMS subdirectories.
    #######################################################################
    def findAncillary(self, year, doy=-99):
        logger = logging.getLogger(__name__)
        # Determine the ancillary directory to store the data
        ancdir = os.environ.get('ANC_PATH')
        if ancdir is None:
            logger.error('ANC_PATH environment variable not set... exiting')
            return None

        # Initialize the doyList to empty and the number of days to 1
        doyList = []
        ndays = 1

        # If doy wasn't specified, then determine the number of days in the
        # specified year. If the specified year is the current year, only
        # process up through today otherwise process through all the days
        # in the year.
        if doy == -99:
            now = datetime.datetime.now()
            if year == now.year:
                ndays = now.timetuple().tm_yday
            else:
                if isLeapYear(year) is True:
                    ndays = 366
                else:
                    ndays = 365

        # Loop through the number of days and determine if the required
        # ancillary data exists
        for currdoy in range(1, ndays+1):
            # If the DOY was specified then use that value otherwise use
            # the current DOY based on the number of days to be processed
            if doy != -99:
                currdoy = doy

            # Pad the DOY with 0s if needed
            if currdoy < 10:
                dayofyear = '00' + str(currdoy)
            elif 9 < currdoy < 100:
                dayofyear = '0' + str(currdoy)
            else:
                dayofyear = str(currdoy)

            # NCEP REANALYSIS file
            ncepFile = ('{}/REANALYSIS/RE_{}/REANALYSIS_{}{}.hdf'
                        .format(ancdir, year, year, dayofyear))

            # EP/TOMS file
            tomsFile = ('{}/EP_TOMS/ozone_{}/TOMS_{}{}.hdf'
                        .format(ancdir, year, year, dayofyear))
            if os.path.isfile(ncepFile) and os.path.isfile(tomsFile):
                doyList.append(True)
            else:
                doyList.append(False)

        # Return the True/False list
        return doyList

    ########################################################################
    # Description: runLedaps will use the parameter passed for the xmlfile.
    # If xmlfile is None (i.e. not specified) then the command-line parameters
    # will be parsed for this information.  The LEDAPS applications are then
    # executed on the specified XML file.  If a log file was specified, then
    # the output from each LEDAPS application will be logged to that file.
    #
    # Inputs:
    #   xmlfile - name of the Landsat XML file to be processed
    #   process_sr - specifies whether the surface reflectance processing,
    #       should be completed.  True or False.  Default is True, otherwise
    #       the processing will halt after the TOA reflectance products are
    #       complete.
    #
    # Returns:
    #     ERROR - error running the LEDAPS applications
    #     SUCCESS - successful processing
    #
    # Notes:
    #   1. The script obtains the path of the XML file and changes
    #      directory to that path for running the LEDAPS code.  If the
    #      xmlfile directory is not writable, then this script exits with
    #      an error.
    #######################################################################
    def runLedaps(self, xmlfile=None, process_sr="True"):
        # If no parameters were passed then get the info from the command line
        if xmlfile is None:

            # Get version number
            cmdstr = ('lndsr --version')
            (status, self.version) = subprocess.getstatusoutput(cmdstr)

            # Get the command line argument for the XML file
            parser = OptionParser(version = self.version)
            parser.add_option("-f", "--xml",
                              type="string", dest="xmlfile",
                              help="name of Landsat XML file",
                              metavar="FILE")
            parser.add_option("-s", "--process_sr", type="string",
                              dest="process_sr",
                              help=("process the surface reflectance products;"
                                    " True or False (default is True) "
                                    " If False, then processing will halt"
                                    " after the TOA reflectance products are"
                                    " complete. (Note: scenes with solar"
                                    " zenith angles above 76 degrees should"
                                    " use process_sr=False)"))
            (options, args) = parser.parse_args()

            # Validate the command-line options
            xmlfile = options.xmlfile  # name of the XML file
            if xmlfile is None:
                parser.error("missing xmlfile command-line argument")
                return ERROR
            process_sr = options.process_sr  # process SR or not
            if process_sr is None:
                process_sr = "True"  # If not provided, default to True

        # Obtain logger from logging using the module's name
        logger = logging.getLogger(__name__)
        logger.info('LEDAPS processing of Landsat XML file: {}'
                    .format(xmlfile))

        # Make sure the XML file exists
        if not os.path.isfile(xmlfile):
            logger.error('XML file does not exist or is not accessible: {}'
                         .format(xmlfile))
            return ERROR

        # Parse the XML filename, strip off the .xml. Use the base XML filename
        # and not the full path.
        base_xmlfile = os.path.basename(xmlfile)
        xml = re.sub('\.xml$', '', base_xmlfile)
        logger.info('Processing XML basefile: {}'.format(xml))

        # Get the path of the XML file and change directory to that location
        # for running this script.  Save the current working directory for
        # return to upon error or when processing is complete.  Note: use
        # abspath to handle the case when the filepath is just the filename
        # and doesn't really include a file path (i.e. the current working
        # directory).
        mydir = os.getcwd()
        xmldir = os.path.dirname(os.path.abspath(xmlfile))
        if not os.access(xmldir, os.W_OK):
            logger.error('Path of XML file is not writable: {}. '
                         'LEDAPS needs write access to the XML directory.'
                         .format(xmldir))
            return ERROR
        logger.info('Changing directories for LEDAPS processing: {}'
                    .format(xmldir))
        os.chdir(xmldir)

        # Processing down in the XML file directory itself, but always return
        # to the original directory after processing or error
        try:
            prefixes_collection = ['LT04', 'LT05', 'LE07']
            if base_xmlfile[0:4] in prefixes_collection:
                # Collection naming convention
                logger.debug('Processing collection data')
            else:
                msg = ('Base XML filename is not recognized as a valid Landsat '
                       '4-7 scene name: {}'.format(base_xmlfile))
                logger.error (msg)
                return ERROR

            # Set up the command-line option for lndsr for processing
            # collections. The per-pixel angle bands need to be generated for
            # band 4 (representative band) and the thermal band(s)
            cmdstr = ('create_landsat_angle_bands --xml {}'
                      .format(base_xmlfile))
            (status, output) = subprocess.getstatusoutput(cmdstr)
            logger.info(output)
            exit_code = status >> 8
            if exit_code != 0:
                logger.error('Error running create_landsat_angle_bands. '
                             'Processing will terminate.')
                return ERROR

            # Mask the angle bands to match the band quality band
            cmdstr = ('mask_per_pixel_angles.py --xml {}'
                      .format(base_xmlfile))
            (status, output) = subprocess.getstatusoutput(cmdstr)
            logger.info(output)
            exit_code = status >> 8
            if exit_code != 0:
                logger.error('Error masking angle bands with the band '
                             'quality band. Processing will terminate.')
                return ERROR

            # Set up the command-line option for lndpm if processing surface
            # reflectance
            if process_sr == "True":
                process_sr_opt_str = "--process_sr=true"
            else:
                process_sr_opt_str = "--process_sr=false"

            # Run LEDAPS modules, checking the return status of each module.
            # Exit if any errors occur.
            cmdstr = ('lndpm --xml {} {}'
                      .format(base_xmlfile, process_sr_opt_str))
            (status, output) = subprocess.getstatusoutput(cmdstr)
            logger.info(output)
            exit_code = status >> 8
            if exit_code != 0:
                logger.error('Error running lndpm.  Processing will terminate.')
                return ERROR

            cmdstr = 'lndcal --pfile lndcal.{}.txt'.format(xml)
            (status, output) = subprocess.getstatusoutput(cmdstr)
            logger.info(output)
            exit_code = status >> 8
            if exit_code != 0:
                logger.error('Error running lndcal. Processing will terminate.')
                return ERROR

            if process_sr == 'True':
                cmdstr = 'lndsr --pfile lndsr.{}.txt'.format(xml)
                (status, output) = subprocess.getstatusoutput(cmdstr)
                logger.info(output)
                exit_code = status >> 8
                if exit_code != 0:
                    logger.error('Error running lndsr. Processing will '
                                 'terminate.')
                    return ERROR

        finally:
            # Return to the original directory
            os.chdir(mydir)

        # Successful completion
        logger.info('Completion of LEDAPS.')
        return SUCCESS

# ##### end of Ledaps class #####

if __name__ == "__main__":
    # Setup the default logger format and level. Log to STDOUT.
    logging.basicConfig(format=('%(asctime)s.%(msecs)03d %(process)d'
                                ' %(levelname)-8s'
                                ' %(filename)s:%(lineno)d:'
                                '%(funcName)s -- %(message)s'),
                        datefmt='%Y-%m-%d %H:%M:%S',
                        level=logging.INFO)
    sys.exit(Ledaps().runLedaps())
