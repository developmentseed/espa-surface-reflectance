#include <getopt.h>
#include "gapfill_viirs_aux.h"

/******************************************************************************
MODULE:  get_args

PURPOSE:  Gets the command-line arguments and validates that the required
arguments were specified.

RETURN VALUE:
Type = int
Value           Description
-----           -----------
ERROR           Error getting the command-line arguments or a command-line
                argument and associated value were not specified
SUCCESS         No errors encountered

PROJECT:  Land Satellites Data System Science Research and Development (LSRD)
at the USGS EROS

NOTES:
  1. Memory is allocated for the input files.  This should be character a
     pointer set to NULL on input.  The caller is responsible for freeing the
     allocated memory upon successful return.
******************************************************************************/
int get_args
(
    int argc,               /* I: number of cmd-line args */
    char *argv[],           /* I: string of cmd-line args */
    char **viirs_aux_file   /* O: address of input VIIRS auxiliary file */
)
{
    int c;                           /* current argument index */
    int option_index;                /* index for the command-line option */
    char errmsg[STR_SIZE];           /* error message */
    char FUNC_NAME[] = "get_args";   /* function name */
    static struct option long_options[] =
    {
        {"viirs_aux", required_argument, 0, 'v'},
        {"help", no_argument, 0, 'h'},
        {0, 0, 0, 0}
    };

    /* Loop through all the cmd-line options */
    opterr = 0;   /* turn off getopt_long error msgs as we'll print our own */
    while (1)
    {
        /* optstring in call to getopt_long is empty since we will only
           support the long options */
        c = getopt_long (argc, argv, "", long_options, &option_index);
        if (c == -1)
        {   /* Out of cmd-line options */
            break;
        }

        switch (c)
        {
            case 0:
                /* If this option set a flag, do nothing else now. */
                if (long_options[option_index].flag != 0)
                    break;
     
            case 'h':  /* help */
                usage ();
                return (ERROR);
                break;

            case 'v':  /* VIIRS auxiliary input file */
                *viirs_aux_file = strdup (optarg);
                break;
     
            case '?':
            default:
                sprintf (errmsg, "Unknown option %s", argv[optind-1]);
                error_handler (true, FUNC_NAME, errmsg);
                usage ();
                return (ERROR);
                break;
        }
    }

    /* Make sure the input file was specified */
    if (*viirs_aux_file == NULL)
    {
        sprintf (errmsg, "Input VIIRS VNP04ANC/VJ104ANC file is a required "
            "argument.");
        error_handler (true, FUNC_NAME, errmsg);
        usage ();
        return (ERROR);
    }

    /* Make sure the file is VNP04ANC/VJ104ANC */
    if (!strstr (*viirs_aux_file, "04ANC.A20"))
    {
        sprintf (errmsg, "Filename is '%s', which is not a recognized "
            "VIIRS VNP04ANC/VJ104ANC filename", *viirs_aux_file);
        error_handler (true, FUNC_NAME, errmsg);
        usage ();
        return (ERROR);
    }

    return (SUCCESS);
}

