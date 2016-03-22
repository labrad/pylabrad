#!/usr/bin/env python
"""

"""
from warnings import warn
try:
    from fastunits import *
    DimensionlessArray = Value
    DimensionlessFloat = Value
    DimensionlessComplex = Value
except ImportError:
    warn("Unable to import compiled unit library.  Unit computations will be slow")
    from labrad.units_compat import *
