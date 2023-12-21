.. aiomonitor documentation master file, created by
   sphinx-quickstart on Sun Dec 11 17:08:38 2016.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

aiomonitor's documentation!
===========================

**aiomonitor** is Python 3.8+ module that adds monitor and cli capabilities
for :mod:`asyncio` application. Idea and code borrowed from curio_ project.
Task monitor that runs concurrently to the :mod:`asyncio` loop (or fast drop in
replacement uvloop_) in a separate thread. This can inspect the loop and
provide debugging capabilities.

aiomonitor provides an python console using aioconsole_ library, it is possible
to execute asynchronous command inside your running application.

As of 0.6.0, it also provides a GUI to inspect and cancel asyncio tasks like below:

+----------------------------+
| .. image:: webui-demo1.gif |
+----------------------------+


Features
--------
* Telnet server that provides insides of operation of you app

* Supportes several commands that helps to list, cancel and trace running
  :mod:`asyncio` tasks

* Provides python REPL capabilities, that is executed in the running event loop;
  helps to inspect state of your :mod:`asyncio` application.

* Extensible with you own commands using :mod:`click`.

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
.. _curio: https://github.com/dabeaz/curio
.. _uvloop: https://github.com/MagicStack/uvloop
.. _cmd: http://docs.python.org/3/library/cmd.html
