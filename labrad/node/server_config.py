import io
import os
import sys

from configparser import ConfigParser

from labrad.util import findEnvironmentVars


class ServerConfig(object):
    def __init__(self, name, description, version, instance_name, cmdline, path,
                 filename, timeout, shutdown_mode, shutdown_timeout):
        self.name = self.base_name = name
        self.description = description
        self.version = version
        self.version_tuple = version_tuple(version)
        self.instance_name = instance_name
        self.environ_vars = findEnvironmentVars(instance_name)
        self.is_local = len(self.environ_vars) > 0
        self.cmdline = cmdline
        self.path = path
        self.filename = filename
        self.timeout = 20 if timeout is None else timeout
        self.shutdown_mode = shutdown_mode
        self.shutdown_timeout = 5 if shutdown_timeout is None else shutdown_timeout


def from_string(conf, filename=None, path=None, platform=sys.platform):
    """Parse a ServerConfig object from a node config string."""
    if isinstance(conf, bytes):
        conf = conf.decode('utf-8')
    scp = ConfigParser()
    scp.readfp(io.StringIO(conf))

    # general information
    name = scp.get('info', 'name', raw=True)
    description = scp.get('info', 'description', raw=True)
    if scp.has_option('info', 'version'):
        version = scp.get('info', 'version', raw=True)
    else:
        version = '0.0'
    if scp.has_option('info', 'instancename'):
        instance_name = scp.get('info', 'instancename', raw=True)
    else:
        instance_name = name

    # startup
    platform_cmdline_option = 'cmdline_{}'.format(platform)
    if scp.has_option('startup', platform_cmdline_option):
        # use platform-specific command line
        cmdline = scp.get('startup', platform_cmdline_option, raw=True)
    else:
        # use generic command line
        cmdline = scp.get('startup', 'cmdline', raw=True)
    if scp.has_option('startup', 'timeout'):
        timeout = float(scp.getint('startup', 'timeout'))
    else:
        timeout = None

    # shutdown
    if scp.has_option('shutdown', 'message'):
        shutdown_mode = 'message', int(scp.get('shutdown', 'message', raw=True))
    elif scp.has_option('shutdown', 'setting'):
        shutdown_mode = 'setting', scp.get('shutdown', 'setting', raw=True)
    else:
        shutdown_mode = None
    try:
        shutdown_timeout = float(scp.getint('shutdown', 'timeout'))
    except:
        shutdown_timeout = None

    return ServerConfig(name, description, version, instance_name, cmdline,
                        path, filename, timeout, shutdown_mode,
                        shutdown_timeout)


def find_config_block(path, filename):
    """Find a Node configuration block embedded in a file."""
    # markers to delimit node info block
    BEGIN = b"### BEGIN NODE INFO"
    END = b"### END NODE INFO"
    with open(os.path.join(path, filename), 'rb') as file:
        foundBeginning = False
        lines = []
        for line in file:
            if line.upper().strip().startswith(BEGIN):
                foundBeginning = True
            elif line.upper().strip().startswith(END):
                break
            elif foundBeginning:
                line = line.replace(b'\r', b'')
                line = line.replace(b'\n', b'')
                lines.append(line)
        return b'\n'.join(lines) if lines else None


def version_tuple(version):
    """Get a tuple from a version string that can be used for comparison.

    Version strings are typically of the form A.B.C-X where A, B and C
    are numbers, and X is extra text denoting dev status (e.g. alpha or beta).
    Given this structure, we cannot just use string comparison to get the order
    of versions; instead we parse the version into a tuple

    ((int(A), int(B), int(C)), version)

    If we cannot parse the numeric part, we just use the empty tuple for the
    first entry, and for such tuples the comparison will just fall back to
    alphabetic comparison on the full version string.
    """
    numstr, _, _extra = version.partition('-')
    try:
        nums = tuple(int(n) for n in numstr.split('.'))
    except Exception:
        nums = ()
    return (nums, version)
