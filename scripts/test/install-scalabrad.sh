#!/bin/sh

# exit on any error
set -e

ARCHIVE=scalabrad-${SCALABRAD_VERSION}.tar.gz

# check to see if scalabrad folder is empty
if [ ! -d "$HOME/scalabrad-${SCALABRAD_VERSION}/bin" ]; then
  wget https://bintray.com/artifact/download/labrad/generic/$ARCHIVE -O $HOME/$ARCHIVE;
  cd $HOME && tar -xvf $ARCHIVE;
else
  echo "Using cached scalabrad-${VERSION}.";
fi
