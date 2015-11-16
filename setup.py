"""LabRAD interface for python

LabRAD is a system for quickly and easily building distributed
instrument control and data analysis applications.  pylabrad
provides a python interface to LabRAD.
"""

classifications = """\
Development Status :: 4 - Beta
Environment :: Console
Environment :: Web Environment
Intended Audience :: Science/Research
License :: OSI Approved :: GNU General Public License (GPL)
Operating System :: OS Independent
Programming Language :: Python
Topic :: Scientific/Engineering"""

from distutils.core import setup, Extension

doclines = __doc__.split('\n')

setup(
    name = 'pylabrad',
    version = '0.93.1',
    author = 'Matthew Neeley',
    author_email = 'maffoo@users.sourceforge.net',
    license = 'http://www.gnu.org/licenses/gpl-2.0.html',
    platforms = ['ANY'],
    
    url = 'http://sourceforge.net/projects/pylabrad/',
    download_url = '',
    
    description = doclines[0],
    long_description = '\n'.join(doclines[2:]),
    classifiers = classifications.split('\n'),
    
    install_requires = [
        'twisted>=2.5',
        'pyOpenSSL'
    ],
    provides = ['labrad'],
    packages = [
        'labrad',
        'labrad.node',
        'labrad.servers',
        'labrad.test',
        'labrad.util',
        ],
    ext_modules = [Extension('labrad.unit_array', sources = ['labrad/unit_array.c'])],

    package_data = {
        'labrad': ['LICENSE.txt'],
        'labrad.node': ['*.ini'],
        },
    scripts = [],
    )
