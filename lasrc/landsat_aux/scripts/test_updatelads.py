import pytest
import subprocess
from freezegun import freeze_time
from . import updatelads
from unittest.mock import patch


def fnmatch_side_effect(filename, pattern):
    print(pattern)
    if pattern == "L8ANC2021169.hdf_fused":
        return False
    elif pattern == "L8ANC2021168.hdf_fused":
        return False
    else:
        return True


@freeze_time("2021-6-20")
@patch("subprocess.run")
@patch("fnmatch.fnmatch")
@patch.object(updatelads, "downloadLads")
@patch("os.listdir")
@patch("os.path.exists")
@patch("os.makedirs")
def test_getLadsData(makedirs, exists, listdir, downloadLads, fnmatch, run):
    # Previous days are processed after combine_l8_aux_data fails for a day.
    exists.side_effect = [True, False, True]
    listdir.return_value = ['afile']
    downloadLads.side_effect = [0, 0]
    fnmatch.side_effect = fnmatch_side_effect
    run.return_value = subprocess.CompletedProcess(args=["none"], returncode=1)
    updatelads.getLadsData("", 2021, True, "")
    assert run.call_count == 2
    run.reset_mock()

    # Previous days are processed if downloadLads fails for a day.
    # Side effect iterator needs to be reset through new assignment
    exists.side_effect = [True, False, True]
    downloadLads.side_effect = [0, 1]
    fnmatch.side_effect = fnmatch_side_effect
    run.return_value = subprocess.CompletedProcess(args=["none"], returncode=0)
    updatelads.getLadsData("", 2021, True, "")
    assert run.call_count == 1
    run.reset_mock()
