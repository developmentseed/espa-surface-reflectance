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
MODULE:  file_exists

PURPOSE:  Determines if the specified file exists.

RETURN VALUE:
Type = bool
Value          Description
-----          -----------
false          File does not exist
true           File exists

NOTES:
******************************************************************************/
bool file_exists
(
    char *filename   /* I: file to check for existence */
)
{
    if (access (filename, F_OK) == 0)
        return true;
    else
        return false;
}


/* DAYSTEP is 50/15 . Weight the monthly data by 50% at day 1, another 50%
 * in 15 days (from day 1 to day 15) and then down to just 50% at day 30
 */
#define DAYSTEP 3.3333333

/******************************************************************************
MODULE:  determine_weights

PURPOSE:  Based on the day of month, the weighting for filling the gaps using
the monthly averages is set up to use the target/current month, the previous
month, and the next month.

RETURN VALUE:
Type = None

NOTES:
 1. Weight the monthly data by 50% at day 1, another 50% in 15 days (from
    day 1 to day 15) and then down to just 50% at day 30.
******************************************************************************/
void determine_weights
(
    int aux_day,             /* I: day of the auxiliary file (1-31) */
    float *prev_weight,      /* O: weight for the previous month */
    float *target_weight,    /* O: weight for the current/target month */
    float *next_weight       /* O: weight for the next month */
)
{
    int i;    /* looping variable for the day within the month */

    /* Determine the weighting for this day (a very crude sawtooth function).
       Start with a 50/50 weight between the current month and the previous
       month. */
    *target_weight = 50.0;
    *prev_weight = 50.0;
    *next_weight = 0.0;

    /* Weighting for the first half of the month (day = 1-15) */
    for (i = 1; i <= 15; i++)
    {
        if (i >= aux_day)
            break;

        *target_weight += DAYSTEP;
        *prev_weight -= DAYSTEP;
    }

    /* Weighting for the second half of the month (day = 16-31) */
    if (aux_day >= 15)
    {
        for(i = 16; i <= 31; i++)
        {
            if (i == aux_day)
                break;

            *target_weight -= DAYSTEP;
            *next_weight += DAYSTEP;
        }
    }

    /* Adjust the weights to zero if they are below 3.0 */
    if (*prev_weight < 3.0)
        *prev_weight = 0.0;
    if (*next_weight < 3.0)
        *next_weight = 0.0;
}


/******************************************************************************
MODULE:  read_monthly_avgs

PURPOSE:  Determines the previous, target, and next monthly averages, and
based on the weights, reads those monthly averages to be used for gapfilling.

RETURN VALUE:
Type = int
Value          Description
-----          -----------
ERROR          Error occurred reading the monthly averages or the monthly
               averages are not available
SUCCESS        Successful completion

NOTES:
******************************************************************************/
int read_monthly_avgs
(
    int aux_month,        /* I: month of the auxiliary file (1-12) */
    int aux_year,         /* I: year of the auxiliary file */
    int n_pixels,         /* I: number of pixels in the monthly avg 1D array */
    float prev_weight,    /* I: weight for the previous month */
    float target_weight,  /* I: weight for the current/target month */
    float next_weight,    /* I: weight for the next month */
    uint8* monthly_avg_oz_data[3],  /* O: array of the ozone data for
                                previous month, target month, next month. If
                                the weight is 0, then the data will be NULL. */
    uint16* monthly_avg_wv_data[3]  /* O: array of the water vapor data
                                for previous month, target month, next month. If
                                the weight is 0, then the data will be NULL. */
)
{
    char FUNC_NAME[] = "read_monthly_avgs"; /* function name */
    char errmsg[STR_SIZE];   /* error message */
    char envvar[STR_SIZE];   /* LASRC_AUX_DIR environment variable contents */
    char aux_dir[STR_SIZE];  /* location of monthly averages aux files */
    char oz_monthly_file[3][STR_SIZE]; /* input ozone monthly files (previous
                                month, current month, next month) */
    char wv_monthly_file[3][STR_SIZE]; /* input water vapor monthly files
                                (previous month, current month, next month)*/
    int prev_month;          /* previous month for filling gaps */
    int next_month;          /* next month for filling gaps */
    FILE *mavg_fp = NULL;    /* file pointer for monthly averages */

    /* Determine which months will be used for gapfilling */
    prev_month = aux_month - 1;
    if (prev_month <= 0)
        prev_month = 12;

    next_month = aux_month + 1;
    if (next_month > 12)
        next_month = 1;

    /* Get the LASRC auxiliary environment variable */
    if (!getenv ("LASRC_AUX_DIR"))
    {
        sprintf (errmsg, "LASRC_AUX_DIR environment variable is not defined.");
        error_handler (true, FUNC_NAME, errmsg);
        return (ERROR);
    }
    snprintf (envvar, STR_SIZE, "%s", getenv("LASRC_AUX_DIR"));
    sprintf (aux_dir, "%s/monthly_avgs", envvar);

    /* Determine the name of the monthly average files to be opened - previous
       month, current/target month, next month. For the previous month, start
       with the current year.  If that isn't available, then we will have to
       pull the previous year.  For the target and next month, we will have to
       pull the previous year because the monthly averages for those months
       aren't available in the current year. */
    sprintf (oz_monthly_file[0], "%s/%d/monthly_avg_oz_%4d_%02d.img", aux_dir,
        aux_year, aux_year, prev_month);
    sprintf (wv_monthly_file[0], "%s/%d/monthly_avg_wv_%4d_%02d.img", aux_dir,
        aux_year, aux_year, prev_month);
    sprintf (oz_monthly_file[1], "%s/%d/monthly_avg_oz_%4d_%02d.img", aux_dir,
        aux_year-1, aux_year-1, aux_month);
    sprintf (wv_monthly_file[1], "%s/%d/monthly_avg_wv_%4d_%02d.img", aux_dir,
        aux_year-1, aux_year-1, aux_month);
    sprintf (oz_monthly_file[2], "%s/%d/monthly_avg_oz_%4d_%02d.img", aux_dir,
        aux_year-1, aux_year-1, next_month);
    sprintf (wv_monthly_file[2], "%s/%d/monthly_avg_wv_%4d_%02d.img", aux_dir,
        aux_year-1, aux_year-1, next_month);

    /* Initialize the monthly average ozone and water vapor pointers to NULL
       for the previous, target, and next month datasets */
    monthly_avg_oz_data[0] = NULL;
    monthly_avg_oz_data[1] = NULL;
    monthly_avg_oz_data[2] = NULL;
    monthly_avg_wv_data[0] = NULL;
    monthly_avg_wv_data[1] = NULL;
    monthly_avg_wv_data[2] = NULL;

    /* Check for the existence and open the previous month's averages, but
       only if they will be used */
    if (prev_weight > 0.0)
    {
        /* If the file doesn't exist for the current year, then check last
           year */
        /* ozone */
        if (!file_exists (oz_monthly_file[0]))
        {
            sprintf (oz_monthly_file[0], "%s/%d/monthly_avg_oz_%4d_%02d.img",
                aux_dir, aux_year-1, aux_year-1, prev_month);
            if (!file_exists (oz_monthly_file[0]))
            {
                sprintf (errmsg, "Monthly ozone averages for the previous "
                    "month (%d) do not exist for the current year (%d) or the "
                    "previous year (%d). %s", prev_month, aux_year, aux_year-1,
                    oz_monthly_file[0]);
                error_handler (true, FUNC_NAME, errmsg);
                return (ERROR);
            }
        }

        /* Allocate data for the previous monthly avg array */
        monthly_avg_oz_data[0] = calloc (n_pixels, sizeof(uint8));
        if (monthly_avg_oz_data[0] == NULL)
        {
            sprintf (errmsg, "Error allocating memory for the previous monthly "
                "ozone average");
            error_handler (true, FUNC_NAME, errmsg);
            return (ERROR);
        }

        /* Read the data for return */
        printf ("Previous monthly averages OZ file: %s\n", oz_monthly_file[0]); 
        mavg_fp = fopen (oz_monthly_file[0], "r");
        if (!mavg_fp)
        {
            sprintf (errmsg, "Not able to open the monthly ozone average: %s",
                oz_monthly_file[0]);
            error_handler (true, FUNC_NAME, errmsg);
            return (ERROR);
        }

        if (fread (&monthly_avg_oz_data[0][0], sizeof(uint8), n_pixels,
            mavg_fp) != n_pixels)
        {
            sprintf (errmsg, "Error reading the monthly ozone average: %s",
                oz_monthly_file[0]);
            error_handler (true, FUNC_NAME, errmsg);
            return (ERROR);
        }

        fclose (mavg_fp);

        /* water vapor */
        if (!file_exists (wv_monthly_file[0]))
        {
            sprintf (wv_monthly_file[0], "%s/%d/monthly_avg_wv_%4d_%02d.img",
                aux_dir, aux_year-1, aux_year-1, prev_month);
            if (!file_exists (wv_monthly_file[0]))
            {
                sprintf (errmsg, "Monthly water vapor averages for the "
                    "previous month (%d) do not exist for the current year "
                    "(%d) or the previous year (%d). %s", prev_month, aux_year,
                    aux_year-1, wv_monthly_file[0]);
                error_handler (true, FUNC_NAME, errmsg);
                return (ERROR);
            }
        }

        /* Allocate data for the previous monthly avg array */
        monthly_avg_wv_data[0] = calloc (n_pixels, sizeof(uint16));
        if (monthly_avg_wv_data[0] == NULL)
        {
            sprintf (errmsg, "Error allocating memory for the previous monthly "
                "water vapor average");
            error_handler (true, FUNC_NAME, errmsg);
            return (ERROR);
        }

        /* Read the data for return */
        printf ("Previous monthly averages WV file: %s\n", wv_monthly_file[0]); 
        mavg_fp = fopen (wv_monthly_file[0], "r");
        if (!mavg_fp)
        {
            sprintf (errmsg, "Not able to open the monthly WV average: %s",
                wv_monthly_file[0]);
            error_handler (true, FUNC_NAME, errmsg);
            return (ERROR);
        }

        if (fread (&monthly_avg_wv_data[0][0], sizeof(uint16), n_pixels,
            mavg_fp) != n_pixels)
        {
            sprintf (errmsg, "Error reading the monthly WV average: %s",
                wv_monthly_file[0]);
            error_handler (true, FUNC_NAME, errmsg);
            return (ERROR);
        }

        fclose (mavg_fp);
    }

    /* Check for the existence and open the target month's averages */
    /* ozone */
    if (!file_exists (oz_monthly_file[1]))
    {
        sprintf (errmsg, "Monthly ozone averages for the target month (%d) "
            "do not exist for the previous year (%d). %s", aux_month,
            aux_year-1, oz_monthly_file[1]);
        error_handler (true, FUNC_NAME, errmsg);
        return (ERROR);
    }

    /* Allocate data for the target monthly avg array */
    monthly_avg_oz_data[1] = calloc (n_pixels, sizeof(uint8));
    if (monthly_avg_oz_data[1] == NULL)
    {
        sprintf (errmsg, "Error allocating memory for the target monthly "
            "ozone average");
        error_handler (true, FUNC_NAME, errmsg);
        return (ERROR);
    }

    /* Read the data for return */
    printf ("Target monthly averages OZ file: %s\n", oz_monthly_file[1]); 
    mavg_fp = fopen (oz_monthly_file[1], "r");
    if (!mavg_fp)
    {
        sprintf (errmsg, "Not able to open the monthly ozone average: %s",
            oz_monthly_file[1]);
        error_handler (true, FUNC_NAME, errmsg);
        return (ERROR);
    }
 
    if (fread (&monthly_avg_oz_data[1][0], sizeof(uint8), n_pixels,
        mavg_fp) != n_pixels)
    {
        sprintf (errmsg, "Error reading the monthly ozone average: %s",
            oz_monthly_file[1]);
        error_handler (true, FUNC_NAME, errmsg);
        return (ERROR);
    }
 
    fclose (mavg_fp);

    /* water vapor */
    if (!file_exists (wv_monthly_file[1]))
    {
        sprintf (errmsg, "Monthly water vapor averages for the target month "
            "(%d) do not exist for the previous year (%d). %s", aux_month,
            aux_year-1, wv_monthly_file[1]);
        error_handler (true, FUNC_NAME, errmsg);
        return (ERROR);
    }

    /* Allocate data for the target monthly avg array */
    monthly_avg_wv_data[1] = calloc (n_pixels, sizeof(uint16));
    if (monthly_avg_wv_data[1] == NULL)
    {
        sprintf (errmsg, "Error allocating memory for the target monthly "
            "water vapor average");
        error_handler (true, FUNC_NAME, errmsg);
        return (ERROR);
    }

    /* Read the data for return */
    printf ("Target monthly averages WV file: %s\n", wv_monthly_file[1]); 
    mavg_fp = fopen (wv_monthly_file[1], "r");
    if (!mavg_fp)
    {
        sprintf (errmsg, "Not able to open the monthly WV average: %s",
            wv_monthly_file[1]);
        error_handler (true, FUNC_NAME, errmsg);
        return (ERROR);
    }

    if (fread (&monthly_avg_wv_data[1][0], sizeof(uint16), n_pixels,
        mavg_fp) != n_pixels)
    {
        sprintf (errmsg, "Error reading the monthly WV average: %s",
            wv_monthly_file[1]);
        error_handler (true, FUNC_NAME, errmsg);
        return (ERROR);
    }

    fclose (mavg_fp);

    /* Check for the existence and open the next month's averages, but only
       if they will be used */
    if (next_weight > 0.0)
    {
        /* ozone */
        if (!file_exists (oz_monthly_file[2]))
        {
            sprintf (errmsg, "Monthly ozone averages for the next month (%d) "
                "do not exist for the previous year (%d). %s", next_month,
                aux_year-1, oz_monthly_file[2]);
            error_handler (true, FUNC_NAME, errmsg);
            return (ERROR);
        }

        /* Allocate data for the next monthly avg array */
        monthly_avg_oz_data[2] = calloc (n_pixels, sizeof(uint8));
        if (monthly_avg_oz_data[2] == NULL)
        {
            sprintf (errmsg, "Error allocating memory for the next monthly "
                "ozone average");
            error_handler (true, FUNC_NAME, errmsg);
            return (ERROR);
        }

        /* Read the data for return */
        printf ("Next monthly averages OZ file: %s\n", oz_monthly_file[2]); 
        mavg_fp = fopen (oz_monthly_file[2], "r");
        if (!mavg_fp)
        {
            sprintf (errmsg, "Not able to open the monthly ozone average: %s",
                oz_monthly_file[2]);
            error_handler (true, FUNC_NAME, errmsg);
            return (ERROR);
        }

        if (fread (&monthly_avg_oz_data[2][0], sizeof(uint8), n_pixels,
            mavg_fp) != n_pixels)
        {
            sprintf (errmsg, "Error reading the monthly ozone average: %s",
                oz_monthly_file[2]);
            error_handler (true, FUNC_NAME, errmsg);
            return (ERROR);
        }

        fclose (mavg_fp);

        /* water vapor */
        if (!file_exists (wv_monthly_file[2]))
        {
            sprintf (errmsg, "Monthly water vapor averages for the next month "
                "(%d) do not exist for the previous year (%d). %s", next_month,
                aux_year-1, wv_monthly_file[2]);
            error_handler (true, FUNC_NAME, errmsg);
            return (ERROR);
        }

        /* Allocate data for the next monthly avg array */
        monthly_avg_wv_data[2] = calloc (n_pixels, sizeof(uint16));
        if (monthly_avg_wv_data[2] == NULL)
        {
            sprintf (errmsg, "Error allocating memory for the next monthly "
                "water vapor average");
            error_handler (true, FUNC_NAME, errmsg);
            return (ERROR);
        }

        /* Read the data for return */
        printf ("Next monthly averages WV file: %s\n", wv_monthly_file[2]);
        mavg_fp = fopen (wv_monthly_file[2], "r");
        if (!mavg_fp)
        {
            sprintf (errmsg, "Not able to open the monthly WV average: %s",
                wv_monthly_file[2]);
            error_handler (true, FUNC_NAME, errmsg);
            return (ERROR);
        }

        if (fread (&monthly_avg_wv_data[2][0], sizeof(uint16), n_pixels,
            mavg_fp) != n_pixels)
        {
            sprintf (errmsg, "Error reading the monthly WV average: %s",
                wv_monthly_file[2]);
            error_handler (true, FUNC_NAME, errmsg);
            return (ERROR);
        }

        fclose (mavg_fp);
    }

    return (SUCCESS);
}


/******************************************************************************
MODULE:  get_fill_value

PURPOSE:  Determines the weighted average to be used for filling the gaps.

RETURN VALUE:
Type = float
Value          Description
-----          -----------
float          Weighted average

NOTES:
******************************************************************************/
float get_fill_value
(
    float prev_weight,    /* I: weight for the previous month */
    float target_weight,  /* I: weight for the current/target month */
    float next_weight,    /* I: weight for the next month */
    float prev_avg,       /* I: previous month average for this pixel */
    float target_avg,     /* I: current/target month average for this pixel */
    float next_avg        /* I: next month average for this pixel */
)
{
    float wgt_avg;   /* weighted average for this pixel */

    wgt_avg = target_avg * (target_weight * 0.01);
    if (prev_weight > 0.0)
        wgt_avg += prev_avg * (prev_weight * 0.01);
    if (next_weight > 0.0)
        wgt_avg += next_avg * (next_weight * 0.01);

    return (wgt_avg);
}


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
    char sdsname[STR_SIZE];  /* ozone and water vapor SDS name */
    bool found;              /* was the SDS found */
    iparam viirs_params[TOTAL_N_SDS]; /* array of VIIRS SDS parameters */
    long pix;                /* current pixel location in the 1D array */
    int i, j;                /* looping variables */
    int nbits;               /* number of bits per pixel for this data array */
    int n_pixels;            /* number of pixels in this 1D array */
    int retval;              /* return status */
    int aux_month;           /* month of the auxiliary file (1-12) */
    int aux_day;             /* day of the auxiliary file (1-31) */
    int aux_year;            /* year of the auxiliary file */
    int32 dims[2] = {IFILL, IFILL}; /* dimensions of desired SDSs */
    int32 sds_id[N_SDS+1];   /* SDS IDs for the output file */
    int32 start[2];          /* starting location in each dimension */
    int32 dtype;             /* VIIRS data type */
    float target_weight;     /* weight for the current/target month */
    float prev_weight;       /* weight for the previous month */
    float next_weight;       /* weight for the next month */
    float prev_oz;           /* previous ozone value for the monthly avg */
    float target_oz;         /* target ozone value for the monthly avg */
    float next_oz;           /* next ozone value for the monthly avg */
    float prev_wv;           /* previous water vapor value for monthly avg */
    float target_wv;         /* target water vapor value for the monthly avg */
    float next_wv;           /* next water vapor value for the monthly avg */
    uint8 *ozone = NULL;     /* pointer to the ozone data */
    uint8 *monthly_avg_oz_data[3];  /* array of the ozone data for previous
                                       month, target month, next month */
    uint16 *wv = NULL;       /* pointer to the water vapor data */
    uint16 *monthly_avg_wv_data[3]; /* array of the water vapor data for prev
                                       month, target month, next month */

    /* Read the command-line arguments */
    retval = get_args (argc, argv, &aux_month, &aux_day, &aux_year,
        &viirs_aux_file);
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

    /* Determine the gapfill weighting for this day */
    determine_weights (aux_day, &prev_weight, &target_weight, &next_weight);
    printf ("Gapfill weights: Target: %.02f  Previous: %.02f  Next: %.02f\n",
        target_weight, prev_weight, next_weight);

    /* Read the data for each of the previous, target, and next monthly avgs
       for ozone and water vapor. Allocates memory for the arrays. Returns a
       NULL pointer in the array if the previous or next weight is zero. */
    retval = read_monthly_avgs (aux_month, aux_year, n_pixels, prev_weight,
        target_weight, next_weight, monthly_avg_oz_data, monthly_avg_wv_data);
    if (retval == ERROR)
    {
        sprintf (errmsg, "Unable to read the monthly averages needed for "
            "gapfilling the VIIRS file.");
        error_handler (true, FUNC_NAME, errmsg);
        exit (ERROR);
    }

    /* Fill in the gaps using a weighted value from the monthly averages.  Use
       the ozone data to identify the fill/gap pixels, which are the same for
       both ozone and water vapor. */
    printf ("Gapfilling VIIRS products for WV and OZ ...\n");
    ozone = (uint8 *) viirs_params[OZONE].data;
    wv = (uint16 *) viirs_params[WV].data;
    if (dims[0] == 3600)
    {  /* then, yeah, we have a CMG */
        for (pix = 0; pix < dims[0] * dims[1]; pix++)
        {
            /* If the pixel is not fill then continue */
            if (ozone[pix] != VIIRS_FILL)
                continue;

            /* Fill this pixel */
            target_oz = (float) monthly_avg_oz_data[1][pix];
            target_wv = (float) monthly_avg_wv_data[1][pix];

            prev_oz = 0.0;
            prev_wv = 0.0;
            if (prev_weight > 0.0)
            {
                prev_oz = (float) monthly_avg_oz_data[0][pix];
                prev_wv = (float) monthly_avg_wv_data[0][pix];
            }

            next_oz = 0.0;
            next_wv = 0.0;
            if (next_weight > 0.0)
            {
                next_oz = (float) monthly_avg_oz_data[2][pix];
                next_wv = (float) monthly_avg_wv_data[2][pix];
            }

            ozone[pix] = (uint8) get_fill_value (prev_weight, target_weight,
                next_weight, prev_oz, target_oz, next_oz);
            wv[pix] = (uint16) get_fill_value (prev_weight, target_weight,
                next_weight, prev_wv, target_wv, next_wv);
        }  /* for pix */
    }  /* if dims[0] */
    else
    {
        sprintf (errmsg, "Unexpected dimensions (%d lines x %d samps). Should "
            "be 3600 x 7200.", dims[0], dims[1]);
        error_handler (true, FUNC_NAME, errmsg);
        exit (ERROR);
    }

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

    /* Free the ozone and water vapor monthly average data */
    free (monthly_avg_oz_data[0]);
    free (monthly_avg_oz_data[1]);
    free (monthly_avg_oz_data[2]);
    free (monthly_avg_wv_data[0]);
    free (monthly_avg_wv_data[1]);
    free (monthly_avg_wv_data[2]);

    /* Successful completion */
    exit (SUCCESS);
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
            "the VIIRS auxiliary data, fills the gaps using monthly "
            "climatology averages, and writes the new data back out to the "
            "HDF file.\n\n");
    printf ("usage: gapfill_viirs_aux --viirs_aux=input_viirs_aux_filename "
            "--month=month_of_aux_file --day=day_of_month_of_aux_file "
            "--year=year_of_aux_file\n");

    printf ("\nwhere the following parameters are required:\n");
    printf ("    -viirs_aux: name of the input VIIRS auxiliary file (VNP04ANC "
            "or VJ104ANC) to be processed. The ozone and water vapor SDSs "
            "will be modified with the gapfilled data.\n"
            "    -month: month (1-12) of the auxiliary file\n"
            "    -day: day of month (1-31) of the auxiliary file\n"
            "    -year: year of the auxiliary file\n\n");

    printf ("\ngapfill_viirs_aux --help will print the usage statement\n");
}
