#!/bin/bash


home=$(pwd) 
# Install file-renaming-tool
#
uv pip install "flytekit>=1.16.3"


cd $home/formats/file-renaming-tool
uv pip install -e .


# Install ome-converter-tool  
cd $home/formats/ome-converter-tool
uv pip install -e .

cd $home/regression/basic-flatfield-estimation-tool
uv pip install -e .



cd $home/transforms/images/apply-flatfield-tool
uv pip install -e .


cd $home/segmentation/kaggle-nuclei-segmentation-tool
uv pip install -e .

uv pip install skit-learnl
# cd  transforms/images/polus-ftl-label-plugin
# uv pip install -e