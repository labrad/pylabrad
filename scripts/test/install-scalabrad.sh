#!/bin/sh

# exit on any error
set -e

ARCHIVE="scalabrad-${SCALABRAD_VERSION}.tar.gz"

URL_BASE="https://github.com/labrad/scalabrad/releases/download/v${SCALABRAD_VERSION}"

# check to see if scalabrad folder is empty
if [ ! -d "$HOME/scalabrad-${SCALABRAD_VERSION}/bin" ]; then
  wget "${URL_BASE}/${ARCHIVE}" -O "${HOME}/${ARCHIVE}";
  cd $HOME && tar -xvf $ARCHIVE;
else
  echo "Using cached scalabrad-${VERSION}.";
fi
