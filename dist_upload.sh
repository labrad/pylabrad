# Use the twine package to upload built packages to pypi.
#
# twine is the recommended package for interacting with PyPI because it is
# careful about only using HTTPS to connect so that credentials are kept safe.
# To use this, you'll need to first `pip install twine` on your local machine.
# And of course you'll need to have already built packages and have an account
# on PyPI with permissions to update pylabrad packages.

twine upload dist/*
