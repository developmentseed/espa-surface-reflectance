#!/usr/bin/env python
from osgeo import gdal
from osgeo import ogr
from osgeo import osr
import sys
import logging

def list_gdal_drivers():
    """Generates a list of all the short names for the GDAL image drivers

    Returns:
        <list>: A list of driver short names
    """

    return [gdal.GetDriver(index).ShortName
            for index in range(gdal.GetDriverCount())]


def delete_gdal_drivers(exclusions=list()):
    """Deletes all GDAL image drivers except those in the exclusions list
    """

    for name in list_gdal_drivers():
        if name not in exclusions:
            gdal.GetDriverByName(name).Deregister()


def main():
    # Make sure ENVI is the only GDAL driver available so that the ENVI files
    # do not get tagged as something other than ENVI, which has happened with
    # a few of our image files (particularly the solar/sensor angle bands).
    logger.debug('{}'.format(list_gdal_drivers()))
    delete_gdal_drivers(['ENVI'])
    logger.debug('{}'.format(gdal.GetDriverCount()))


if __name__ == '__main__':
    # Setup the default logger format and level. Log to STDOUT.
    logging.basicConfig(format=('%(asctime)s.%(msecs)03d %(process)d'
                                ' %(levelname)-8s'
                                ' %(filename)s:%(lineno)d:'
                                '%(funcName)s -- %(message)s'),
                        datefmt='%Y-%m-%d %H:%M:%S',
                        level=logging.INFO)
    logger = logging.getLogger(__name__)

    sys.exit(main())
