#!/bin/bash

version=$(<VERSION)
docker build . -t polusai/dicom2nifti-plugin:${version}
