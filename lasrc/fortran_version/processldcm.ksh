#!/bin/ksh
#build the input file for processing ldcm data
rootdir=/gpfs/data1/salsagp/skakuns/Data/Malawi/Malawi_test1/
ver=v3.5.7
for case in `ls  $rootdir | awk -F / '{print $NF}' | grep LC08_L1TP_169069_20180512_20180517_01_T1`
do
mtlfile=`ls $rootdir$case/*.txt`
fileinp=ldcm$ver$case.inp
echo 0 >$fileinp
rm -f $rootdir$case/*.bin*
rm -f $rootdir$case/*.hdr
for file in `ls $rootdir$case/*_B?.TIF`
do
gdal_translate -of ENVI $file $file.bin
done
for file in `ls $rootdir$case/*_B1?.TIF`
do
gdal_translate -of ENVI $file $file.bin
done
for file in `ls $rootdir$case/*_BQA.TIF`
do
gdal_translate -of ENVI $file $file.bin
done
#exit
ls $rootdir$case/*_B?.TIF.bin >>$fileinp
ls $rootdir$case/*_B1?.TIF.bin >>$fileinp
ls $rootdir$case/*_BQA.TIF.bin >>$fileinp
file=`ls $rootdir$case/*_B5.TIF.tif`
offsettiff=0
echo $offsettiff
date=`echo $case | awk -F _ '{print $4}'`
echo $date
#exit
year2d=`echo $date | cut -c 3-4`
year=`echo $date | cut -c 1-4`
month=`echo $date | cut -c 5-6`
dom=`echo $date | cut -c 7-8`
echo $month/$dom/$year2d
doy=`./jdoy $month/$dom/$year2d | cut -c 1-3`
echo $doy
#exit

fileanc=`ls /gpfs/data1/salsagp/eric/VNP04ANCGF/$year/VNP04ANC.A$year$doy*.hdf`
echo $fileanc >>$fileinp
mtlfile=`ls $rootdir$case/*MTL.txt`
rnl=`grep REFLECTIVE_LINES $mtlfile | awk '{print $3}'`
rnc=`grep REFLECTIVE_SAMPLES $mtlfile | awk '{print $3}'`
pnl=`grep  PANCHROMATIC_LINES $mtlfile | awk '{print $3}'`
pnc=`grep PANCHROMATIC_SAMPLES $mtlfile | awk '{print $3}'`
echo $rnl $rnc $pnl $pnc >>$fileinp
ts=`grep SUN_ELEVATION $mtlfile | awk '{print 90.-$3}'`
fs=`grep SUN_AZIMUTH $mtlfile | awk '{print $3}'`
echo $ts $fs >>$fileinp
utmzone=`grep  "UTM_ZONE" $mtlfile | awk '{print $3}'`
x0=`grep  "CORNER_UL_PROJECTION_X_PRODUCT" $mtlfile | awk '{print $3}'`
y0=`grep  "CORNER_UL_PROJECTION_Y_PRODUCT" $mtlfile | awk '{print $3}'`
echo $utmzone 1 1 $y0 $x0 >>$fileinp
time=`grep SCENE_CENTER_TIME $mtlfile |  awk '{print $3}' | tr -d '"' | tr -d Z | tr -s : " "`
echo $doy $time >>$fileinp
echo sr$ver$case.hdf  >>$fileinp
echo $offsettiff >>$fileinp
#echo 2603 3870 2759 3771 >>$fileinp
./LDCMSR-$ver <$fileinp >log$case$ver
rm -f $rootdir$case/*.bin*
rm -f $rootdir$case/*.hdr
done

