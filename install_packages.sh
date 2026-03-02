#!/bin/bash


# Install file-renaming-tool
#
uv pip install "flytekit>=1.16.3"


cd formats/file-renaming-tool
uv pip install -e .

cd ../
# Install ome-converter-tool  
cd ome-converter-tool
uv pip install -e .

cd ../../
cd regression/basic-flatfield-estimation-tool
uv pip install -e .


cd transforms/images/apply-flatfield-tool
uv pip install -e 

cd  segmentation/kaggle-nuclei-segmentation-tool
# uv pip install -e 

# cd  transforms/images/polus-ftl-label-plugin
# uv pip install -e