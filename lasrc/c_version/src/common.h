#ifndef _COMMON_H_
#define _COMMON_H_

#include <stdlib.h>
#include "hdf.h"
#include "mfhdf.h"
typedef char byte;

#ifndef MIN
#define MIN(a,b) (((a)<(b))?(a):(b))
#endif
#ifndef MAX
#define MAX(a,b) (((a)>(b))?(a):(b))
#endif

/* Surface reflectance version */
#define SR_VERSION "2.1.0 (Collection 1)"

/* Define the default aerosol value */
#define DEFAULT_AERO 0.05
#define DEFAULT_EPS 1.5

/* Define the size of the aerosol window that will be used when running the
   aerosol inversion.  The aerosols will be inverted for the center of the
   NxN window (with special handling for fill, clouds, water) and then used
   to fill the rest of the window.  Aerosols are fairly homogenious over a
   reasonable area.  Landsat windows represent the UL corner.
   The following are example NxN window setups:
   9x9: AERO_WINDOW 9 and HALF_AERO_WINDOW 4
   7x7: AERO_WINDOW 7 and HALF_AERO_WINDOW 3
   5x5: AERO_WINDOW 5 and HALF_AERO_WINDOW 2
   3x3: AERO_WINDOW 3 and HALF_AERO_WINDOW 1
   1x1: AERO_WINDOW 1 and HALF_AERO_WINDOW 0
*/
#define L8_AERO_WINDOW 3
#define L8_HALF_AERO_WINDOW 1
#define S2_AERO_WINDOW 6

/* How many lines of data should be processed at one time */
#define PROC_NLINES 10

/* For angle conversions -
   degrees to radians = PI/180
   radians to degrees = 180/PI */
#define PI 3.14159265
#define PIx2 (PI * 2.0)
#define DEG2RAD 0.017453293
#define RAD2DEG 57.29577951

/* For divisions - to minimize processing time */
#define ONE_DIV_1013 0.000987166
#define ONE_DIV_8500 0.000117647

/* Number of bands corrected to surface reflectance
   * Landsat 8 (bands 1-7).  The atmospheric correction variables store
   information for 8 bands, so we will go with that for the array size.
   * Sentinel-2 (bands 1-13, skipping band 9 and 10).  The atmospheric
   correction variables store information for 11 bands, so we will go with
   that for the array size. */
#define NSR_L8_BANDS 8
#define NSR_S2_BANDS 11

/* Get the larger number of bands between the two instruments */
#define NSR_BANDS MAX(NSR_L8_BANDS, NSR_S2_BANDS)

/* L8 Level-1 products have 8 reflectance bands (bands 1-7, and 9),
   2 thermal bands (band 10 and 11), 1 pan band (band 8), and 1 QA band
   (band 12)
   Sentinel-2 Level-1 products have 13 reflectance bands, but we will not
   process bands 9 and 10 */
#define NBAND_L8_REFL_MAX 8
#define NBAND_L8_THM_MAX 2
#define NBAND_L8_PAN_MAX 1
#define NBAND_L8_QA_MAX 1
#define NBAND_L8_TTL_MAX (NBAND_L8_REFL_MAX + NBAND_L8_THM_MAX + NBAND_L8_PAN_MAX + NBAND_L8_QA_MAX)

#define NBAND_S2_REFL_MAX 11
#define NBAND_S2_TTL_MAX NBAND_S2_REFL_MAX

/* Get the larger number of bands between the two instruments */
#define NBAND_REFL_MAX MAX(NBAND_L8_REFL_MAX, NBAND_S2_REFL_MAX)

/* L8 surface reflectance products have 8 reflectance bands, 2 thermal bands, 
   0 pan bands, and 1 QA band.
   Sentinel-2 surface reflectance products have 13 reflectance bands, and
   1 QA band. Bands 9 (water vapor) and 10 (cirrus) will not be processed. */
#define NBAND_L8_REFL_OUT 8
#define NBAND_L8_THM_OUT 2
#define NBAND_L8_PAN_OUT 0
#define NBAND_L8_QA_OUT 1
#define NBAND_L8_TTL_OUT (NBAND_L8_REFL_OUT + NBAND_L8_THM_OUT + NBAND_L8_PAN_OUT + NBAND_L8_QA_OUT)

#define NBAND_S2_REFL_OUT 11
#define NBAND_S2_QA_OUT 1
#define NBAND_S2_TTL_OUT (NBAND_S2_REFL_OUT + NBAND_S2_QA_OUT)

/* CMG and DEM files are lat/long images where each pixel represents 0.05 deg x
   0.05 deg */
/* DEM information */
#define DEM_NBLAT 3600
#define DEM_NBLON 7200

/* Ratio file information */
#define RATIO_NBLAT 3600
#define RATIO_NBLON 7200

/* Ozone and water vapor information */
#define CMG_NBLAT 3600
#define CMG_NBLON 7200

/* Lookup table index value */
#define NPRES_VALS 7
#define NAOT_VALS 22
#define NSOLAR_VALS 8000
#define NSUNANGLE_VALS 22
#define NVIEW_ZEN_VALS 20
#define NSOLAR_ZEN_VALS 22

/* Coefficients for determining atmospheric values */
#define NCOEF 4
#define NREFL_L8_BANDS 7
#define NREFL_S2_BANDS 11 

/* Get the larger number of bands between the two instruments */
#define NREFL_BANDS MAX(NREFL_L8_BANDS, NREFL_S2_BANDS)

/* Define the full list of bands for Sentinel-2, even though we aren't
   processing all these bands. Some look-up tables and input arrays are
   defined for the full list of bands. */
typedef enum {S2_BAND1=0, S2_BAND2, S2_BAND3, S2_BAND4, S2_BAND5, S2_BAND6,
    S2_BAND7, S2_BAND8, S2_BAND8A, S2_BAND9, S2_BAND10, S2_BAND11, S2_BAND12,
    S2_TTL} My_s2_band_t;
extern char S2_FULL_BANDNAME[S2_TTL][3];  /* defined in lut_subr.c */

/* Define the input products to be processed */
typedef enum {DN_L8_BAND1=0, DN_L8_BAND2, DN_L8_BAND3, DN_L8_BAND4,
    DN_L8_BAND5, DN_L8_BAND6, DN_L8_BAND7, DN_L8_BAND8, DN_L8_BAND9,
    DN_L8_BAND10, DN_L8_BAND11, DN_L8_QA, DN_L8_TTL} Mydn_l8_band_t;
typedef enum {DN_S2_BAND1=0, DN_S2_BAND2, DN_S2_BAND3, DN_S2_BAND4,
    DN_S2_BAND5, DN_S2_BAND6, DN_S2_BAND7, DN_S2_BAND8, DN_S2_BAND8A,
    DN_S2_BAND11, DN_S2_BAND12, DN_S2_QA, DN_S2_TTL} Mydn_s2_band_t;

/* Define the output products to be processed */
typedef enum {SR_L8_BAND1=0, SR_L8_BAND2, SR_L8_BAND3, SR_L8_BAND4, SR_L8_BAND5,
    SR_L8_BAND6, SR_L8_BAND7, SR_L8_BAND9, SR_L8_BAND10, SR_L8_BAND11,
    SR_L8_AEROSOL, SR_L8_TTL} Mysr_l8_band_t;
typedef enum {SR_S2_BAND1=0, SR_S2_BAND2, SR_S2_BAND3, SR_S2_BAND4, SR_S2_BAND5,
    SR_S2_BAND6, SR_S2_BAND7, SR_S2_BAND8, SR_S2_BAND8A, SR_S2_BAND11,
    SR_S2_BAND12, SR_S2_AEROSOL, SR_S2_TTL} Mysr_s2_band_t;
extern char S2_BANDNAME[NREFL_S2_BANDS][3];  /* defined in output.c */

/* For the minimal arrays that use this value, we will just use the largest
   of the L8 and S2 number of output bands */
#define NBAND_TTL_OUT SR_S2_TTL

/* Definte the RADSAT band */
#define SR_RADSAT 0

/* High confidence Level-1 QA values */
#define L1QA_HIGH_CONF 3

/* Bit values of ipflag (interpolation flag) QA, which includes aerosol
   levels */
typedef enum {
  IPFLAG_FILL=0,            /* fill value */
  IPFLAG_CLEAR=1,           /* aerosol retrieval was valid (land pixel) */
  IPFLAG_WATER=2,           /* water pixel */
  IPFLAG_FAILED=2,          /* flags failed aerosol retrieval pixels for S2 */
  IPFLAG_CLOUD=3,           /* pixel was flagged as cloud in the Level-1 QA */
  IPFLAG_FAILED_TMP=3,      /* temp flag for expanding possible failed pixels
                               for S2 */
  IPFLAG_SHADOW=4,          /* pixel was flagged as cloud shadow in the
                               Level-1 QA */
  IPFLAG_INTERP_WINDOW=5,   /* aerosol was interpolated using the center (L8) or
                               UL (S2) of the NxN windows */
  AERO1_QA=6,    /* these two AERO bits mark the amount of aerosols and = 64 */
  AERO2_QA=7     /* reflect the level of atmospheric correction made    = 128 */
} Ipflag_t;

/* Satellite type definitions, mainly to allow future satellites to be
   supported if needed */
typedef enum {
  SAT_NULL = -1,
  SAT_LANDSAT_8 = 0, 
  SAT_SENTINEL_2,
  SAT_MAX
} Sat_t;

/* Instrument type definition */
typedef enum {
  INST_NULL = -1,
  INST_OLI_TIRS = 0, 
  INST_OLI, 
  INST_MSI,
  INST_MAX
} Inst_t;

/* World Reference System (WRS) type definition */
typedef enum {
  WRS_NULL = -1,
  WRS_1 = 0, 
  WRS_2,
  WRS_MAX
} Wrs_t;

typedef struct {
  int nlines;
  int nsamps;
  double pixsize[2];
} Img_coord_info_t;

#endif
