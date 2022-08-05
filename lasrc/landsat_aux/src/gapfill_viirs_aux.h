#ifndef _GAPFILL_VIIRS_AUX_H_
#define _GAPFILL_VIIRS_AUX_H_

#include <stdio.h>
#include <stdlib.h>
#include <strings.h>
#include <ctype.h>
#include <libgen.h>
#include <math.h>
#include <stdbool.h>
#include <unistd.h>
#include "mfhdf.h"
#include "error_handler.h"

#define MAXLENGTH 128
#define MAXLENGTH2 5000

/* Define the input fill value */
#define VIIRS_FILL 0
#define IFILL -1

typedef struct{
   int32 sd_id;
   int32 sds_id;
   bool process;
   int32 data_type;
   int sds_dims[2];
   void *data;
   char sdsname[100];
} iparam;


/* Prototypes */
int get_args
(
    int argc,              /* I: number of cmd-line args */
    char *argv[],          /* I: string of cmd-line args */
    int *month,            /* O: month (1-12) of auxiliary file to be proc'd */
    int *day,              /* O: day (1-31) of auxiliary file to be proc'd */
    int *year,             /* O: year of auxiliary file to be processed */
    char **viirs_aux_file  /* O: address of input VIIRS auxiliary file */
);

void usage();

int parse_sds_info
(
    char *filename,          /* I: VIIRS file to be read */
    iparam viirs_params[]    /* O: array of structs for VIIRS params */
);

void interpolate
(
    int32 data_type,     /* I: data type of the data array */
    void *data,          /* I: data array */
    long lineoffset,     /* I: pixel location for the start of this line */
    int left,            /* I: location in the line of the left pixel */
    int right            /* I: location in the line of the right pixel */
);

#endif
