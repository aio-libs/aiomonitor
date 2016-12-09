aiomonitor
==========
.. image:: https://travis-ci.org/jettify/aiomonitor.svg?branch=master
    :target: https://travis-ci.org/jettify/aiomonitor
.. image:: https://codecov.io/gh/jettify/aiomonitor/branch/master/graph/badge.svg
    :target: https://codecov.io/gh/jettify/aiomonitor


**aiomonitor** is Python 3.5+ module that adds monitor and cli capabilities
for asyncio_ application. Idea and code borrowed from curio_ project.


Run tests
---------

For testing purposes you need to install development
requirements::

    $ pip install -r requirements-dev.txt
    $ pip install -e .

Then just execute tests with coverage::

    $ make cov


Requirements
------------

* Python_ 3.5+
* uvloop_ (optional)


.. _Python: https://www.python.org
.. _asyncio: http://docs.python.org/3.4/library/asyncio.html
.. _uvloop: https://github.com/MagicStack/uvloop
.. _PEP492: https://www.python.org/dev/peps/pep-0492/
.. _curio: https://github.com/dabeaz/curio
.. _aioconsole: https://github.com/vxgmichel/aioconsole
