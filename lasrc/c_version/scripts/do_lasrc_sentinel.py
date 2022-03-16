#! /usr/bin/env python
import sys
import os
import re
import subprocess
import datetime
from optparse import OptionParser
import logging
import glob     # list and manipulate filenames

ERROR = 1
SUCCESS = 0


#############################################################################
# Created on August 23, 2019 by Gail Schmidt, USGS/EROS
# Created Python script to run the Sentinel surface reflectance code based
# on the inputs specified by the user.  This script will determine the input
# auxiliary file needed for processing, based on the date of the Sentinel
# input file.
#
# Usage: do_lasrc_sentinel.py --help prints the help message
############################################################################
class SurfaceReflectance():

    def __init__(self):
        pass


    ########################################################################
    # Description: runSr will use the parameters passed for the input and
    # output files.  If input/output files are None (i.e. not specified) then
    # the command-line parameters will be parsed for this information.  The
    # surface reflectance application is then executed to generate the desired
    # outputs on the specified input file.  If a log file was specified, then
    # the output from this application will be logged to that file.
    #
    # Inputs:
    #   xml_infile - name of the input XML file
    #   process_sr - specifies whether the surface reflectance processing
    #       should be completed.  True or False.  Default is True, otherwise
    #       the processing will halt after the TOA reflectance products are
    #       complete.
    #
    # Returns:
    #     ERROR - error running the surface reflectance application
    #     SUCCESS - successful processing
    #
    # Notes:
    #   1. The script obtains the path of the XML file and changes
    #      directory to that path for running the surface reflectance
    #      application.  If the XML file directory is not writable, then this
    #      script exits with an error.
    #   2. If the XML file is not specified and the information is
    #      going to be grabbed from the command line, then it's assumed all
    #      the parameters will be pulled from the command line.
    #######################################################################
    def runSr (self, xml_infile=None):
        # if no parameters were passed then get the info from the
        # command line
        if xml_infile == None:
            # Get version number
            cmdstr = ('lasrc --version')
            (exit_code, self.version) = subprocess.getstatusoutput(cmdstr)

            # get the command line argument for the XML file
            parser = OptionParser(version = self.version)
            parser.add_option ("-i", "--xml", type="string",
                dest="xml",
                help="name of XML file", metavar="FILE")
            (options, args) = parser.parse_args()
    
            # XML input file
            xml_infile = options.xml
            if xml_infile == None:
                parser.error ('missing input XML file command-line argument');
                return ERROR

        # get the logger
        logger = logging.getLogger(__name__)
        msg = ('Surface reflectance processing of Sentinel-2 file: {}'
               .format(xml_infile))
        logger.info (msg)
        
        # make sure the XML file exists
        if not os.path.isfile(xml_infile):
            msg = ('XML file does not exist or is not accessible: {}'
                   .format(xml_infile))
            logger.error (msg)
            return ERROR

        # use the base XML filename and not the full path.
        base_xmlfile = os.path.basename (xml_infile)
        msg = 'Processing XML file: {}'.format(base_xmlfile)
        logger.info (msg)
        
        # get the path of the XML file and change directory to that location
        # for running this script.  save the current working directory for
        # return to upon error or when processing is complete.  Note: use
        # abspath to handle the case when the filepath is just the filename
        # and doesn't really include a file path (i.e. the current working
        # directory).
        mydir = os.getcwd()
        xmldir = os.path.dirname (os.path.abspath (xml_infile))
        if not os.access(xmldir, os.W_OK):
            msg = ('Path of XML file is not writable: {}. Script needs '
                   'write access to the XML directory.'.format(xmldir))
            logger.error (msg)
            return ERROR
        msg = ('Changing directories for surface reflectance processing: {}'
               .format(xmldir))
        logger.info (msg)
        os.chdir (xmldir)

        # determine the auxiliary directory for the data
        auxdir = os.environ.get('LASRC_AUX_DIR')
        if auxdir is None:
            logger.error('LASRC_AUX_DIR environment variable not set. Exiting.')
            return ERROR

        # pull the date from the XML filename to determine which auxiliary
        # file should be used for input.
        # Example: S2A_MSI_L1C_T10TFR_20180816_20180903.xml uses the
        # VJ104ANC.A2018228.001.*.hdf HDF file or VNP04ANC.A2018228.001.*.hdf.
        s2_prefixes_collection = ['S2A', 'S2B']
        if base_xmlfile[0:3] in s2_prefixes_collection:
            # Collection naming convention. Pull the year, month, day from the
            # XML filename. It should be the 4th group, separated by
            # underscores. Then convert month, day to DOY.
            aux_date = base_xmlfile.split('_')[4]
            aux_year = aux_date[0:4]
            aux_month = aux_date[4:6]
            aux_day = aux_date[6:8]
            myday = datetime.date(int(aux_year), int(aux_month), int(aux_day))
            aux_doy = myday.strftime("%j")
            full_aux_dir = ('{}/LADS/{}'.format(auxdir, aux_year))

            # The auxiliary file could be VJ104ANC or VNP04ANC, however there
            # should only be one, with VJ104ANC being the priority. And LaSRC
            # only wants the base filename and not the entire path.
            aux_files = glob.glob('{}/*04ANC.A{}{}.*.hdf'
                                  .format(full_aux_dir, aux_year, aux_doy))
            if len(aux_files) == 0:
                logger.error('No auxiliary files were found to match '
                             '*04ANC.A{}{}.*.hdf'.format(aux_year, aux_doy))
                return ERROR
            aux_file = os.path.basename(aux_files[0])
        else:
            msg = ('Base XML filename is not recognized as a valid Sentinel-2 '
                   'scene name'.format(base_xmlfile))
            logger.error (msg)
            os.chdir (mydir)
            return ERROR

        # run surface reflectance algorithm, checking the return status.  exit
        # if any errors occur.
        cmdstr = ('lasrc --xml={} --aux={} --verbose'
                  .format(xml_infile, aux_file))
        msg = 'Executing lasrc command: {}'.format(cmdstr)
        logger.debug (msg)
        (exit_code, output) = subprocess.getstatusoutput (cmdstr)
        logger.info (output)
        if exit_code != 0:
            msg = 'Error running lasrc.  Processing will terminate.'
            logger.error (msg)
            os.chdir (mydir)
            return ERROR
        
        # successful completion.  return to the original directory.
        os.chdir (mydir)
        msg = 'Completion of surface reflectance.'
        logger.info (msg)
        return SUCCESS

######end of SurfaceReflectance class######

if __name__ == "__main__":
    # setup the default logger format and level. log to STDOUT.
    logging.basicConfig(format=('%(asctime)s.%(msecs)03d %(process)d'
                                ' %(levelname)-8s'
                                ' %(filename)s:%(lineno)d:'
                                '%(funcName)s -- %(message)s'),
                        datefmt='%Y-%m-%d %H:%M:%S',
                        level=logging.INFO)
    sys.exit (SurfaceReflectance().runSr())
