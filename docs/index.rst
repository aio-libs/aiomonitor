.. aiomonitor documentation master file, created by
   sphinx-quickstart on Sun Dec 11 17:08:38 2016.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

aiomonitor's documentation!
===========================

**aiomonitor** is Python 3.5+ module that adds monitor and cli capabilities
for asyncio_ application. Idea and code borrowed from curio_ project.
Task monitor that runs concurrently to the asyncio_ loop (or fast drop in
replacement uvloop_) in a separate thread. This can inspect the loop and
provide debugging capabilities.

Library provides an python console using aioconsole_ library, it is possible
to execute asynchronous command inside your running application.

+-------------------+
|.. image:: tty.gif |
+-------------------+


Features
--------
 * Telnet server that provides insides of operation of you app

 * Supportes several commands that helps to list, cancel and trace running
   asyncio_ tasks

 * Provides python REPL capabilities, that is executed in the running event loop;
   helps to inspect state of your ``asyncio`` application.

 * Extensible with you own commands, in the style of the standard library's cmd_
   module

Contents
--------

.. toctree::
   :maxdepth: 2

   tutorial
   examples
   api
   contributing


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`


.. _PEP492: https://www.python.org/dev/peps/pep-0492/
.. _Python: https://www.python.org
.. _aioconsole: https://github.com/vxgmichel/aioconsole
.. _aiohttp: https://github.com/KeepSafe/aiohttp
.. _asyncio: http://docs.python.org/3/library/asyncio.html
.. _curio: https://github.com/dabeaz/curio
.. _uvloop: https://github.com/MagicStack/uvloop
.. _cmd: http://docs.python.org/3/library/cmd.html
