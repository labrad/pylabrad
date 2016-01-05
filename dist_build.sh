# Build distribution packages for pylabrad.
#
# We first clear out the dist/ directory which may contain old packages from
# other builds, so that we don't accumulate lots of packages locally.

rm -r dist/
python setup.py sdist --format=zip,gztar \
                bdist_wheel
