# pylabrad

[![Build Status](https://secure.travis-ci.org/labrad/pylabrad.png)](http://travis-ci.org/labrad/pylabrad)
[![Coverage Status](https://coveralls.io/repos/labrad/pylabrad/badge.svg)](https://coveralls.io/r/labrad/pylabrad)

pylabrad is an interface to the LabRAD system in python with support for both clients and servers.
For general information about the LabRAD system/protocol see [the labrad repository](https://github.com/labrad/labrad) and associated [wiki](https://github.com/labrad/labrad/wiki).
For help getting started and understanding pylabrad take a look at the [wiki](https://github.com/labrad/pylabrad/wiki).

## Node Server

In addition to the basic labrad client/server support, this package also includes a tool called the "node" server in the `labrad.node` package.
This server just runs other labrad servers, allowing you to start and stop them by sending labrad requests to the node.
By running node servers on one or more machines connected to labrad, you can remotely control which labrad servers are running on those machines.
This can be very useful in distributed setups.
For more information, see the [source](https://github.com/labrad/pylabrad/blob/master/labrad/node/__init__.py).
The node module is executable, so you should launch it with `python -m labrad.node`.
To see documentation of the available command-line parameters run `python -m labrad.node --help`.

## Contributing

For instructions on how to contribute to pylabrad, see [contributing.md](https://github.com/labrad/labrad/blob/master/contributing.md).

## Tests

New code should have tests, and changes to existing code should not break existing tests.
To run the test suite, you'll need to have `pytest` installed, then run `py.test` from the command line when in the pylabrad directory.

## Migration note

This repo was moved from the martinisgroup organization.
To tell git to pull updates from the new location, you'll
want to update the 'origin' remote in your local repository.
Use `git remote -v` to see the names and urls for all remotes
you have defined, then `git remote set-url` to update the url,
changing the organization to labrad:

```
$ git remote -v
origin	git@github.com:martinisgroup/pylabrad (fetch)
origin	git@github.com:martinisgroup/pylabrad (push)

$ git remote set-url origin git@github.com:labrad/pylabrad
```

## Credits

```
PyParsing Copyright (c) 2003-2007  Paul T. McGuire
```

```
unwrap.py from http://www.wave.co.nz/~glyn/
```
