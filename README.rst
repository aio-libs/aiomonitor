aiomonitor
==========
.. image:: https://travis-ci.com/aio-libs/aiomonitor.svg?branch=master
    :target: https://travis-ci.com/aio-libs/aiomonitor
.. image:: https://codecov.io/gh/aio-libs/aiomonitor/branch/master/graph/badge.svg
    :target: https://codecov.io/gh/aio-libs/aiomonitor
.. image:: https://api.codeclimate.com/v1/badges/d14af4cfb0c4ff52b1ef/maintainability
   :target: https://codeclimate.com/github/aio-libs/aiomonitor/maintainability
   :alt: Maintainability
.. image:: https://img.shields.io/pypi/v/aiomonitor.svg
    :target: https://pypi.python.org/pypi/aiomonitor
.. image:: https://readthedocs.org/projects/aiomonitor/badge/?version=latest
    :target: http://aiomonitor.readthedocs.io/en/latest/?badge=latest
    :alt: Documentation Status
.. image:: https://badges.gitter.im/Join%20Chat.svg
    :target: https://gitter.im/aio-libs/Lobby
    :alt: Chat on Gitter

**aiomonitor** is Python 3.5+ module that adds monitor and cli capabilities
for asyncio_ application. Idea and code borrowed from curio_ project.
Task monitor that runs concurrently to the asyncio_ loop (or fast drop in
replacement uvloop_) in a separate thread as result monitor will work even if
event loop is blocked for some reason.

Library provides an python console using aioconsole_ module, it is possible
to execute asynchronous command inside your running application. Extensible
with you own commands, in the style of the standard library's cmd_ module

+--------------------------------------------------------------------------------------+
| .. image:: https://raw.githubusercontent.com/aio-libs/aiomonitor/master/docs/tty.gif |
+--------------------------------------------------------------------------------------+

Installation
------------
Installation process is simple, just::

    $ pip install aiomonitor


Example
-------
Monitor has context manager interface:

.. code:: python

    import aiomonitor

    loop = asyncio.get_event_loop()
    with aiomonitor.start_monitor(loop=loop):
        loop.run_forever()

Now from separate terminal it is possible to connect to the application::

    $ nc localhost 50101

or using included python client::

    $ python -m aiomonitor.cli

Tutorial
--------

Lets create simple aiohttp_ application, and see how ``aiomonitor`` can
integrates with it.

.. code:: python

    import asyncio

    import aiomonitor
    from aiohttp import web

    # Simple handler that returns response after 100s
    async def simple(request):
        loop = request.app.loop

        print('Start sleeping')
        await asyncio.sleep(100, loop=loop)
        return web.Response(text="Simple answer")

    loop = asyncio.get_event_loop()
    # create application and register route
    app = web.Application(loop=loop)
    app.router.add_get('/simple', simple)

    # it is possible to pass dictionary with local variables
    # to the python console environment
    host, port = "localhost", 8090
    locals_ = {"port": port, "host": host}
    # init monitor just before run_app
    with aiomonitor.start_monitor(loop=loop, locals=locals_):
        # run application with built in aiohttp run_app function
        web.run_app(app, port=port, host=host)

Lets save this code in file ``simple_srv.py``, so we can run it with command::

    $ python simple_srv.py
    ======== Running on http://localhost:8090 ========
    (Press CTRL+C to quit)

And now one can connect running application from separate terminal, with
``nc`` command, immediately ``aiomonitor`` will respond with prompt::

    $ nc localhost 50101
    Asyncio Monitor: 1 tasks running
    Type help for commands
    monitor >>>

Now you can type commands, for instance ``help``::

    monitor >>> help
    Commands:
                 ps               : Show task table
                 where taskid     : Show stack frames for a task
                 cancel taskid    : Cancel an indicated task
                 signal signame   : Send a Unix signal
                 stacktrace       : Print a stack trace from the event loop thread
                 console          : Switch to async Python REPL
                 quit             : Leave the monitor

``aiomonitor`` supports also async python console inside running event loop
so you can explore state of your application::

    monitor >>> console
    Python 3.5.2 (default, Oct 11 2016, 05:05:28)
    [GCC 4.2.1 Compatible Apple LLVM 8.0.0 (clang-800.0.38)] on darwin
    Type "help", "copyright", "credits" or "license" for more information.
    ---
    This console is running in an asyncio event loop.
    It allows you to wait for coroutines using the 'await' syntax.
    Try: await asyncio.sleep(1, result=3, loop=loop)
    ---
    >>> await asyncio.sleep(1, result=3, loop=loop)

To leave console type ``exit()``::

    >>> exit()
    monitor >>>


``aiomonitor`` is very easy to extend with your own console commands.

.. code:: python

   class WebMonitor(aiomonitor.Monitor):
       def do_hello(self, sin, sout, name=None):
           """Using the /hello GET interface

           There is one optional argument, "name".  This name argument must be
           provided with proper URL excape codes, like %20 for spaces.
           """
           name = '' if name is None else '/' + name
           r = requests.get('http://localhost:8090/hello' + name)
           sout.write(r.text + '\n')


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
.. _cmd: http://docs.python.org/3/library/cmd.html
