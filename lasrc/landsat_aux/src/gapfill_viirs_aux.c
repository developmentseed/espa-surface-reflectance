/******************************************************************************
FILE: gapfill_viirs_aux
  
PURPOSE: Contains functions for gapfilling the VIIRS auxiliary data.

PROJECT:  Land Satellites Data System Science Research and Development (LSRD)
at the USGS EROS

LICENSE TYPE:  NASA Open Source Agreement Version 1.3

NOTES:
******************************************************************************/
#include "gapfill_viirs_aux.h"

/* Program will look for these SDSs in the VIIRS inputs */
#define TOTAL_N_SDS 5
#define N_SDS 2
char list_of_sds[N_SDS][50] = {
    "Coarse Resolution Ozone",
    "Coarse Resolution Water Vapor"};
#define OZONE 0
#define WV 1


/******************************************************************************
MODULE:  gapfill_viirs_aux

PURPOSE:  Opens the user-specified VIIRS auxiliary product, reads the
identified SDSs, fills the gaps in the data, and writes the SDS back out to
the same file.

RETURN VALUE:
Type = int
Value          Description
-----          -----------
ERROR          Error occurred reading the inputs, gapfilling, or writing the
               data back out
SUCCESS        Successful completion

NOTES:
1. This routine will work on the VIIRS JPSS1 (VJ104ANC) and the NPP (VNP04ANC)
   products.
******************************************************************************/
int main (int argc, char **argv)
{    
    char FUNC_NAME[] = "main"; /* function name */
    char errmsg[STR_SIZE];     /* error message */
    char *viirs_aux_file = NULL;  /* input VIIRS auxiliary file */
    char sdsname[STR_SIZE];       /* ozone and water vapor SDS name */
    bool found;              /* was the SDS found */
    iparam viirs_params[TOTAL_N_SDS]; /* array of VIIRS SDS parameters */
    long pix;                /* current pixel location in the 1D array */
    int i, j;                /* looping variables */
    int nbits;               /* number of bits per pixel for this data array */
    int line;                /* current line in the CMG data array */
    int samp;                /* current sample in the line */
    int left, right;         /* pixel locations for interpolation */ 
    int n_pixels;            /* number of pixels in this 1D array */
    int retval;              /* return status */
    uint8 *ozone = NULL;     /* pointer to the ozone data */
    int32 dims[2] = {IFILL, IFILL}; /* dimensions of desired CMG/CMA SDSs */
    int32 sds_id[N_SDS+1];   /* SDS IDs for the output file */
    int32 start[2];          /* starting location in each dimension */
    int32 dtype;             /* Terra/Aqua data type */

    /* Read the command-line arguments */
    retval = get_args (argc, argv, &viirs_aux_file);
    if (retval != SUCCESS)
    {   /* get_args already printed the error message */
        exit (ERROR);
    }

    /* Initialize the SDS information for the input file */
    for (i = 0; i < TOTAL_N_SDS; i++)
    {
        strcpy (viirs_params[i].sdsname, "(missing SDS)");
        viirs_params[i].sd_id = IFILL;
        viirs_params[i].sds_id = IFILL;
        viirs_params[i].process = false;
        viirs_params[i].data_type = IFILL;
        viirs_params[i].data = NULL;
    }

    /* Read the input file */
    retval = parse_sds_info (viirs_aux_file, viirs_params);
    if (retval != SUCCESS)
    {
        sprintf (errmsg, "Error parsing file: %s", viirs_aux_file);
        error_handler (true, FUNC_NAME, errmsg);
        exit (ERROR);
    }

    /* Make sure each SDS was found */
    for (i = 0; i < N_SDS; i++)
    {
        found = false;
        for (j = 0; j < TOTAL_N_SDS; j++)
        {
            if (!strcmp (viirs_params[j].sdsname, list_of_sds[i]))
            {
                found = true;
                viirs_params[j].process = true;
                break;
            }
        }

        if (!found)
        {
            sprintf (errmsg, "Unable to find SDS in the VIIRS file: %s",
                list_of_sds[i]);
            error_handler (true, FUNC_NAME, errmsg);
            exit (ERROR);
        }
    }

    /* Allocate memory for the data arrays, separate memory for each of the
       SDSs we are going to read and output */
    nbits = 0;
    dims[0] = viirs_params[0].sds_dims[0];
    dims[1] = viirs_params[0].sds_dims[1];
    n_pixels = dims[1] * dims[0];
    for (i = 0; i < TOTAL_N_SDS; i++)
    {
        /* Skip if this SDS is not to be processed */
        if (!viirs_params[i].process)
            continue;

        dtype = viirs_params[i].data_type;
        strcpy (sdsname, viirs_params[i].sdsname);

        if (dtype == DFNT_UINT16)
            nbits = sizeof (uint16);
        else if (dtype == DFNT_UINT8)
            nbits = sizeof (uint8);
        else
        {
            sprintf (errmsg, "Unsupported data type for SDS %s.  Only uint16 "
                "and uint8 are supported.", sdsname);
            error_handler (true, FUNC_NAME, errmsg);
            exit (ERROR);
        }

        /* This is the location of the input data */
        viirs_params[i].data = calloc (n_pixels, nbits);
        if (viirs_params[i].data == NULL)
        {
            sprintf (errmsg, "Allocating memory (%d bits) for VIIRS SDS: "
                "%s", nbits, sdsname);
            error_handler (true, FUNC_NAME, errmsg);
            exit (ERROR);
        }
    }  /* end for i */

    /* Start of processing the inputs .... */
    /* Read each SDS */
    printf ("Reading each SDS ...\n");
    start[0] = 0;
    start[1] = 0;
    for (i = 0; i < TOTAL_N_SDS; i++)
    {
        /* Skip if this SDS is not to be processed */
        if (!viirs_params[i].process)
            continue;

        /* Get the SDS information */
        strcpy (sdsname, viirs_params[i].sdsname);
        printf ("    %d: %s\n", i, sdsname);

        /* Read the VIIRS data for this SDS */
        retval = SDreaddata (viirs_params[i].sds_id, start, NULL, dims,
            viirs_params[i].data);
        if (retval == -1)
        {
            sprintf (errmsg, "Unable to read SDS %s from the VIIRS file",
                sdsname);
            error_handler (true, FUNC_NAME, errmsg);
            exit (ERROR);
        }
    }

    /* Interpolate water vapor and ozone data, but only for the gaps which
       don't span the entire globe.  Those are more likely gaps in the polar
       regions.  Use the ozone data to identify the fill pixels, which are the
       same for both ozone and water vapor. */
    printf ("Interpolating VIIRS products for WV and OZ ...\n");
    ozone = (uint8 *) viirs_params[OZONE].data;
    if (dims[0] == 3600)
    {  /* then, yeah, we have a CMG */
        for (line = 0; line < dims[0]; line++)
        {
            /* Get the current pixel location in the 1D array for this line */
            pix = (long) line * dims[1];

            /* Loop through the pixels in this line */
            left = right = -1;
            for (samp = 0; samp < dims[1]; samp++)
            {
                /* If the pixel is not fill then continue */
                if (ozone[pix+samp] != VIIRS_FILL)
                    continue;

                /* Find the left and right pixels in the line to use for
                   interpolation.  Basically need the non-fill pixels
                   surrounding the current pixel. */
                left = right = samp;
                while (ozone[pix+right] == VIIRS_FILL)
                    right++;
                samp = right;
                left--;

                /* Interpolate the fill area, but skip large gaps which are
                   likely in the arctic regions. We will use the interpolation
                   for filling the "smaller" gaps that are more reasonable. */
                if (abs (right - left) <= 900)
                {
                    /* Interpolate all fill pixels between the left and right
                       non-fill pixels for the ozone and water vapor data */
                    interpolate (DFNT_UINT8, viirs_params[OZONE].data, pix,
                        left, right);
                    interpolate (DFNT_UINT16, viirs_params[WV].data, pix, left,
                        right);
                }
            }
        }
    }  /* if dims[0] */

    /* Write each SDS to the output file */
    start[0] = 0;
    start[1] = 0;
    printf ("Writing each SDS ...\n");
    for (i = 0; i < TOTAL_N_SDS; i++)
    {
        /* Skip if this SDS is not to be processed */
        if (!viirs_params[i].process)
            continue;

        strcpy (sdsname, viirs_params[i].sdsname);
        printf ("    %s\n", sdsname);

        retval = SDwritedata (viirs_params[i].sds_id, start, NULL, dims,
            viirs_params[i].data); 
        if (retval == -1)
        {
            sprintf (errmsg, "Unable to write the %s SDS to the VIIRS file.",
                sdsname);
            error_handler (true, FUNC_NAME, errmsg);
            exit (ERROR);
        }
    }

    /* Close and clean up */
    for (i = 0; i < N_SDS; i++)
    {
        free (viirs_params[i].data);
        SDendaccess (viirs_params[i].sds_id);
        SDend (viirs_params[i].sd_id);
        SDendaccess (sds_id[i]);
    }   
    SDendaccess (sds_id[i]);
    free (viirs_aux_file);

    /* Successful completion */
    exit (SUCCESS);
}


/******************************************************************************
MODULE:  interpolate

PURPOSE:  Interpolates all fill pixels between the left and right pixels.

RETURN VALUE:
Type = None

NOTES:
  1. Only supports uint8 and uint16.
******************************************************************************/
void interpolate
(
    int32 data_type,     /* I: data type of the data array */
    void *data,          /* I: data array */
    long lineoffset,     /* I: pixel location for the start of this line */
    int left,            /* I: location in the line of the left pixel */
    int right            /* I: location in the line of the right pixel */
)
{
    uint8 *ui8x = NULL;     /* uint8 pointer */
    uint16 *ui16x = NULL;   /* uint16 pointer */
    int i;                  /* looping variable */
    int diff;               /* distance between the left and right pixels */
    float slope;            /* slope for this pixel */

    /* Determine the distance between the left and right pixels */
    diff = right - left;

    /* Handle the interpolation between the pixels based on the data type */
    if (data_type == DFNT_UINT8)
    {
        ui8x = (uint8 *)data;
        if (ui8x[lineoffset+right] > ui8x[lineoffset+left])
        {
            slope = ((float) ui8x[lineoffset+right] -
                     (float) ui8x[lineoffset+left]) / (float) (diff);
            for (i = 0; i < diff; i++)
            {
                ui8x[lineoffset+i+left] = (uint8)
                    ((float) ui8x[lineoffset+left] + (slope * i));
            }
        }
        else
        {
            slope = ((float) ui8x[lineoffset+left] - 
                     (float) ui8x[lineoffset+right]) / (float) (diff);
            for (i = 0; i < diff; i++)
            {
                ui8x[lineoffset+i+left] = (uint8)
                    ((float) ui8x[lineoffset+left] - (slope * i));
            }
        }
    }
    else if (data_type == DFNT_UINT16)
    {
        ui16x = (uint16 *)data;
        if (ui16x[lineoffset+right] > ui16x[lineoffset+left])
        {
            slope = ((float) ui16x[lineoffset+right] - 
                     (float) ui16x[lineoffset+left]) / (float) (diff);
            for (i = 0; i < diff; i++)
            {
                ui16x[lineoffset+i+left] = (uint16)
                    ((float) ui16x[lineoffset+left] + (slope * i));
            }
        }
        else
        {
            slope = ((float) ui16x[lineoffset+left] -
                     (float) ui16x[lineoffset+right]) / (float)(diff);
            for (i = 0; i < diff; i++)
            {
                ui16x[lineoffset+i+left] = (uint16)
                    ((float) ui16x[lineoffset+left] - (slope * i));
            }
        }
    }

    return;
}


/******************************************************************************
MODULE:  parse_sds_info

PURPOSE:  Reads the daily, global VIIRS CMG file.

RETURN VALUE:
Type = int
Value          Description
-----          -----------
ERROR          Error occurred reading the input
SUCCESS        Successful completion

NOTES:
  1. If memory for the VIIRS_params structure has not been allocated, this
     function will allocate memory for an array of N_SDS iparam structures.
     Otherwise the passed in array will be utilized.
******************************************************************************/
int parse_sds_info
(
    char *filename,          /* I: VIIRS file to be read */
    iparam viirs_params[]    /* O: array of structs for VIIRS params */
)
{
    char FUNC_NAME[] = "parse_sds_info"; /* function name */
    char errmsg[STR_SIZE];  /* error message */
    int retval;             /* return status */
    int i, j;               /* looping variables */
    int sd_id;              /* file ID for the HDF file */
    int sds_id;             /* ID for the current SDS */
    int nsds;               /* number of SDSs in the file */
    int nattr;              /* number of attributes for this file */
    int rank;               /* rank of the dimensions in this SDS */
    int localdims[2];       /* stored version of the dimensions */
    int sds_dims[2];        /* SDS dimension sizes */
    int data_type;          /* value representing the data type of this SDS */
    char sds_name[STR_SIZE]; /* name of the SDS at the specified index */

    /* Open the input file for reading and writing */
    sd_id = SDstart (filename, DFACC_WRITE);
    if (sd_id == -1)
    {
        sprintf (errmsg, "Error reading file: %s", filename);
        error_handler (true, FUNC_NAME, errmsg);
        return (ERROR);
    }
    
    retval = SDfileinfo (sd_id, &nsds, &nattr);
    if (retval == -1)
    {
        sprintf (errmsg, "SDfileinfo error reading file: %s", filename);
        error_handler (true, FUNC_NAME, errmsg);
        SDend (sd_id);
        return (ERROR);
    }

    if (nsds < 1)
    {
        sprintf (errmsg, "File %s contains no SDSs", filename);
        error_handler (true, FUNC_NAME, errmsg);
        SDend (sd_id);
        return (ERROR);
    }

    /* Now check out the SDSs and their associated information */
    localdims[0] = IFILL;
    localdims[1] = IFILL;
    for (i = 0; i < nsds; i++)
    {
        /* Open the SDS */
        sds_id = SDselect (sd_id, i);
        if (sds_id == -1)
        {
            sprintf (errmsg, "SDselect error for SDS %d", i);
            error_handler (true, FUNC_NAME, errmsg);
            SDend (sd_id);
            return (ERROR);
        }
      
        /* CMG files should all have SDSs of the same rank (2) and dimensions
           (3600 by 7200).  If some file has an SDS with a different dimension,
           report it as a warning. */
        retval = SDgetinfo (sds_id, sds_name, &rank, sds_dims, &data_type,
            &nattr);   
        if (retval == -1)
        {
            sprintf (errmsg, "SDgetinfo error for SDS %d", i);
            error_handler (true, FUNC_NAME, errmsg);
            SDend (sd_id);
            return (ERROR);
        }

        if (rank != 2)
        {
            sprintf (errmsg, "SDS %d has unanticipated rank of %d, "
                "skipping ...", i, rank);
            error_handler (false, FUNC_NAME, errmsg);
            continue;
        }

        if (localdims[0] == IFILL && localdims[1] == IFILL)
        {
            localdims[0] = sds_dims[0];
            localdims[1] = sds_dims[1];
        }
        else
        {
            if (localdims[0] != sds_dims[0])
            {
                 sprintf (errmsg, "SDS has unanticipated x-dimension size of "
                     "%d, skipping ...", sds_dims[0]);
                 error_handler (false, FUNC_NAME, errmsg);
                 continue;
            }

            if (localdims[1] != sds_dims[1])
            {
                 sprintf (errmsg, "SDS has unanticipated y-dimension size of "
                     "%d, skipping ...", sds_dims[1]);
                 error_handler (false, FUNC_NAME, errmsg);
                 continue;
            }
        }
    
        /* Check against names of SDSs we need */
        for (j = 0; j < N_SDS; j++)
        {
            if (!strcmp (sds_name, list_of_sds[j]))
            {  /* keep this SDS info */
                viirs_params[j].sd_id = sd_id;
                viirs_params[j].sds_id = sds_id;
                viirs_params[j].data_type = data_type;
                viirs_params[j].data = (void *)NULL;    
                strcpy (viirs_params[j].sdsname, sds_name);
                viirs_params[j].sds_dims[0] = sds_dims[0];
                viirs_params[j].sds_dims[1] = sds_dims[1];
            }
        }  /* for j */
    }  /* for i */

    /* Successful completion */
    return (SUCCESS);
}


/******************************************************************************
MODULE:  usage

PURPOSE:  Prints the usage information for this application.

RETURN VALUE:
Type = None

NOTES:
******************************************************************************/
void usage ()
{
    printf ("gapfill_viirs_aux reads the ozone and water vapor SDSs from "
            "the VIIRS auxiliary data, fills the gaps, and writes the new "
            "data back out to the HDF file.\n\n");
    printf ("usage: gapfill_viirs_aux "
            "--viirs_aux=input_viirs_aux_filename\n");

    printf ("\nwhere the following parameters are required:\n");
    printf ("    -viirs_aux: name of the input VIIRS auxiliary file (VNP04ANC "
            "or VJ104ANC) to be processed. The ozone and water vapor SDSs "
            "will be modified with the gapfilled data.\n");

    printf ("\ngapfill_viirs_aux --help will print the usage statement\n");
}
