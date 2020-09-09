#! /usr/bin/env python
from numpy import *
from osgeo import gdal
from osgeo import ogr
from osgeo import osr
from osgeo import gdal_array
from osgeo import gdalconst
from gdalconst import *
import sys
import os
import datetime
import logging
from optparse import OptionParser
import gdal_remove_drivers as gdal_deregister

ERROR = 1
SUCCESS = 0
BQA_FILL = 1             # first bit is turned on for fill
OUTPUT_FILL = -32768


class MaskAngles():

    def __init__(self):
        pass

    ########################################################################
    # Description: Reads the per-pixel angle band and uses the band quality
    # array to mask the pixels of the per-pixel angle file that are fill.
    # The per-pixel angle band is closed, but the band quality array is not
    # modified.
    #
    # Inputs:
    #   ppa_file - name of ESPA raw binary per-pixel angle file to be masked;
    #              file is read then overwritten with the masked data
    #            - this should be an INT16 band
    #   bqa - array of band quality data to be used for masking
    #       - this should be a UINT16 band
    #
    # Returns:
    #     ERROR - error masking the per-pixel angle file
    #     SUCCESS - successful masking
    #
    # Notes:
    #######################################################################
    def maskFill(self, ppa_file, bqa):
        logger = logging.getLogger(__name__)

        # Open connection to the PPA (read/write) band
        ppa_ds = gdal.Open(ppa_file, GA_Update)
        if ppa_ds is None:
            logger.error('GDAL could not open PPA file: {}'.format(ppa_file))
            return ERROR

        # Create a connection to the PPA band
        ppa_band = ppa_ds.GetRasterBand(1)
        if ppa_band is None:
            logger.error('Could not connect to PPA file: {}'.format(ppa_file))
            return ERROR

        # Read the PPA band
        ppa = ppa_band.ReadAsArray(0, 0, ppa_ds.RasterXSize, ppa_ds.RasterYSize)

        # Mask the PPA band for the fill pixels in the BQA band
        ppa[bqa == 1] = OUTPUT_FILL

        # Write the new PPA values
        ppa_band.WriteArray(ppa, 0, 0)

        # Close the PPA dataset, file, and array
        bqa = None
        bqa_band = None
        bqa_ds = None

        # Masking complete
        return SUCCESS


    ########################################################################
    # Description: runMask reads the band quality file and then masks the
    # per-pixel files to mark the fill pixels.  The band quality file is
    # read and then passed to the masking routine for each per-pixel angle
    # band to minimize the need to open, read, re-open, re-read that band
    # multiple times.
    #
    # Inputs:
    #   xmlfile - name of the Landsat XML file to be processed
    #
    # Returns:
    #     ERROR - error running the masking applications
    #     SUCCESS - successful masking
    #
    # Notes:
    #   1. The script obtains the path of the XML file and changes
    #      directory to that path for running the masking code.  If the
    #      xml_file directory is not writable, then this script exits with
    #      an error.
    #######################################################################
    def runMask(self, xml_file=None):
        # If no parameters were passed then get the info from the command line
        if xml_file is None:
            # Get the command line argument for the XML file
            parser = OptionParser()
            parser.add_option("-f", "--xml",
                              type="string", dest="xml_file",
                              help="name of Landsat XML file",
                              metavar="FILE")
            (options, args) = parser.parse_args()

            # Validate the command-line options
            xml_file = options.xml_file  # name of the XML file
            if xml_file is None:
                parser.error("missing XML file command-line argument")
                return ERROR

        # Obtain logger from logging using the module's name
        logger = logging.getLogger(__name__)
        logger.info('Masking angle bands in Landsat XML file: {}'
                    .format(xml_file))

        # Make sure the XML file exists
        if not os.path.isfile(xml_file):
            logger.error('XML file does not exist or is not accessible: {}'
                         .format(xml_file))
            return ERROR

        # Save the current working directory for return to upon error or when
        # processing is complete
        mydir = os.getcwd()

        # Turn off some of the drivers for gdal since it tends to create issues
        # with some of our ESPA datasets. The ESPA products intermittently
        # will be read as JDEM or DOQ instead of UTM or ALBERS. We believe
        # that GDAL finds a character in the .img file that makes it believe
        # the image is something other than an ENVI product in the actual
        # projection we have specified.
#        jdem = gdal.GetDriverByName('JDEM')
#        doq1 = gdal.GetDriverByName('DOQ1')
#        doq2 = gdal.GetDriverByName('DOQ2')
#        jdem.Deregister()
#        doq1.Deregister()
#        doq2.Deregister()
        gdal_deregister.delete_gdal_drivers(['ENVI'])

        # Strip the path from the XML file and change into the directory
        # containing the XML file
        xml_dir = os.path.dirname(xml_file)
        base_xml_file = xml_file
        if not xml_dir == '':
            logger.warn('Changing directories to the location of the input '
                        'XML file: {}'.format(xml_dir))
            os.chdir(xml_dir)

            # Also need to obtain the base filename of the XML file, without
            # the path name
            base_xml_file = os.path.basename(xml_file)

        try:
            # Determine the name of the band 4 solar azimuth file and check if
            # it exists
            solar_az_file = base_xml_file.replace(
                            '.xml', '_b4_solar_azimuth.img')
            if not os.path.isfile(solar_az_file):
                logger.error('Band 4 solar azimuth file does not exist in the '
                             'XML directory. {}'.format(xml_dir))
                return ERROR
    
            # Determine the name of the band 4 solar zenith file and check if
            # it exists
            solar_zen_file = base_xml_file.replace(
                             '.xml', '_b4_solar_zenith.img')
            if not os.path.isfile(solar_zen_file):
                logger.error('Band 4 solar zenith file does not exist in the '
                             'XML directory. {}'.format(xml_dir))
                return ERROR
    
            # Determine the name of the band 4 sensor azimuth file and check if
            # it exists
            sensor_az_file = base_xml_file.replace(
                             '.xml', '_b4_sensor_azimuth.img')
            if not os.path.isfile(sensor_az_file):
                logger.error('Band 4 sensor azimuth file does not exist in the '
                             'XML directory. {}'.format(xml_dir))
                return ERROR
    
            # Determine the name of the band 4 sensor zenith file and check if
            # it exists
            sensor_zen_file = base_xml_file.replace(
                              '.xml', '_b4_sensor_zenith.img')
            if not os.path.isfile(sensor_zen_file):
                logger.error('Band 4 sensor zenith file does not exist in the '
                             'XML directory. {}'.format(xml_dir))
                return ERROR
    
            # Determine the name of the Level-1 band quality file and check if
            # it exists
            bqa_file = base_xml_file.replace('.xml', '_bqa.img')
            if not os.path.isfile(bqa_file):
                logger.error('Level-1 band quality file does not exist in the '
                             'XML directory. {}'.format(xml_dir))
                return ERROR
    
            # Open connection to the BQA (read-only) band, since it's used for
            # all the masks.  No need to open/reopen and read/re-read multiple
            # times.
            bqa_ds = gdal.Open(bqa_file)
            if bqa_ds is None:
                logger.error('GDAL could not open BQA file: {}'
                             .format(bqa_file))
                return ERROR

            # Create a connection to the BQA band
            bqa_band = bqa_ds.GetRasterBand(1)
            if bqa_band is None:
                logger.error('Could not connect to BQA file: {}'
                             .format(bqa_file))
                return ERROR

            # Read the BQA band
            bqa = bqa_band.ReadAsArray(0, 0, bqa_ds.RasterXSize,
                                       bqa_ds.RasterYSize)

            # Mask all four bands using the BQA band
            if self.maskFill(solar_az_file, bqa) != SUCCESS:
                logger.error('Error masking solar azimuth file')
                return ERROR

            if self.maskFill(solar_zen_file, bqa) != SUCCESS:
                logger.error('Error masking solar zenith file')
                return ERROR

            if self.maskFill(sensor_az_file, bqa) != SUCCESS:
                logger.error('Error masking sensor azimuth file')
                return ERROR

            if self.maskFill(sensor_zen_file, bqa) != SUCCESS:
                logger.error('Error masking sensor zenith file')
                return ERROR

            # Close the BQA dataset, file, and array
            bqa = None
            bqa_band = None
            bqa_ds = None

        finally:
            # Return to the original directory
            os.chdir(mydir)

        # Successful completion
        logger.info('Completion of per-pixel angle masking.')
        return SUCCESS

# ##### end of MaskAngles class #####

if __name__ == "__main__":
    # Setup the default logger format and level. Log to STDOUT.
    logging.basicConfig(format=('%(asctime)s.%(msecs)03d %(process)d'
                                ' %(levelname)-8s'
                                ' %(filename)s:%(lineno)d:'
                                '%(funcName)s -- %(message)s'),
                        datefmt='%Y-%m-%d %H:%M:%S',
                        level=logging.INFO)
    sys.exit(MaskAngles().runMask())
