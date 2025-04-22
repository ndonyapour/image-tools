"""Tests for dicom2nifti."""

import pytest
from polus.plugins.images.formats.dicom2nifti.dicom2nifti import (
    dicom2nifti,
)
from .conftest import FixtureReturnType


def test_dicom2nifti(generate_test_data : FixtureReturnType):
    """Test dicom2nifti."""
    inp_dir, out_dir, ground_truth_dir, img_path, ground_truth_path = generate_test_data
    filepattern = ".*"
    assert dicom2nifti(inp_dir, filepattern, out_dir) == None


@pytest.mark.skipif("not config.getoption('slow')")
def test_dicom2nifti(generate_large_test_data : FixtureReturnType):
    """Test dicom2nifti."""
    inp_dir, out_dir, ground_truth_dir, img_path, ground_truth_path = generate_large_test_data
    filepattern = ".*"
    assert dicom2nifti(inp_dir, filepattern, out_dir) == None