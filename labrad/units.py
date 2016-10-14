#!/usr/bin/env python
"""

"""
from warnings import warn
try:
    from fastunits import *
    DimensionlessArray = ValueArray
    DimensionlessFloat = Value
    DimensionlessComplex = Complex
    for k, v in constants.items():
        globals()[k] = v
        
except ImportError:
    warn("Unable to import compiled unit library.  Unit computations will be slow")
    from labrad.units_compat import *
