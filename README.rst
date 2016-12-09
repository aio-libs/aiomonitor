aiomonitor
==========
.. image:: https://travis-ci.org/jettify/aiomonitor.svg?branch=master
    :target: https://travis-ci.org/jettify/aiomonitor
.. image:: https://codecov.io/gh/jettify/aiomonitor/branch/master/graph/badge.svg
    :target: https://codecov.io/gh/jettify/aiomonitor


**aiomonitor** is Python 3.5+ module that adds monitor and cli capabilities
for asyncio_ application. Idea and code borrowed from curio_ project.
Task monitor that runs concurrently to the asyncio_ loop (or fast drop in
replacement uvloop_) in a separate thread. This can inspect the loop and
provide debugging capabilities.

Library provides an python console using aioconsole_ library, it is possible
to execute asynchronous command inside your running application.


Install
------
Installation process is simple, just::

    $ pip install aiomonitor


Run tests
---------

For testing purposes you need to install development
requirements::

    $ pip install -r requirements-dev.txt
    $ pip install -e .

Then just execute tests with coverage::

    $ make cov

To run individual use following command::

    $ py.test -sv tests/test_monitor.py -k test_name


Requirements
------------

* Python_ 3.5+
* aioconsole_
* uvloop_ (optional)


.. _PEP492: https://www.python.org/dev/peps/pep-0492/
.. _Python: https://www.python.org
.. _aioconsole: https://github.com/vxgmichel/aioconsole
.. _aiohttp: https://github.com/KeepSafe/aiohttp
.. _asyncio: http://docs.python.org/3.5/library/asyncio.html
.. _curio: https://github.com/dabeaz/curio
.. _uvloop: https://github.com/MagicStack/uvloop
