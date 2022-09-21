aiomonitor-ng
=============

**aiomonitor-ng** is a (temporary) fork of **aiomonitor** with support for
Python 3.10+ and additional usability & debuggability improvements.

**aiomonitor** is a module that adds monitor and cli capabilities
for asyncio_ applications. Idea and code were borrowed from curio_ project.
Task monitor that runs concurrently to the asyncio_ loop (or fast drop-in
replacement uvloop_) in a separate thread as result monitor will work even if
the event loop is blocked for some reason.

This library provides a python console using aioconsole_ module. It is possible
to execute asynchronous commands inside your running application. Extensible
with you own commands, in the style of the standard library's cmd_ module

.. image:: https://raw.githubusercontent.com/achimnol/aiomonitor-ng/master/docs/screenshot-ps-where-example.png

Installation
------------
Installation process is simple, just::

    $ pip install aiomonitor-ng


Example
-------
Monitor has context manager interface:

.. code:: python

    import aiomonitor

    loop = asyncio.get_event_loop()
    with aiomonitor.start_monitor(loop=loop):
        loop.run_forever()

Now from separate terminal it is possible to connect to the application::

    $ telnet localhost 50101


or the included python client::

    $ python -m aiomonitor.cli
    
    
    

Tutorial
--------

Let's create a simple aiohttp_ application, and see how ``aiomonitor`` can
be integrated with it.

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

    # it is possible to pass a dictionary with local variables
    # to the python console environment
    host, port = "localhost", 8090
    locals_ = {"port": port, "host": host}
    # init monitor just before run_app
    with aiomonitor.start_monitor(loop=loop, locals=locals_):
        # run application with built-in aiohttp run_app function
        web.run_app(app, port=port, host=host)

Let's save this code in file ``simple_srv.py``, so we can run it with the following command::

    $ python simple_srv.py
    ======== Running on http://localhost:8090 ========
    (Press CTRL+C to quit)

And now one can connect to a running application from a separate terminal, with
the ``nc`` command, and ``aiomonitor`` will immediately respond with prompt::

    $ nc localhost 50101
    Asyncio Monitor: 1 tasks running
    Type help for commands
    monitor >>>


Note in order to make arrow keys and editing work properly just prepend command with `rlwrap`::

    $ rlwrap nc localhost 50101


Now you can type commands, for instance, ``help``::

    monitor >>> help
    Commands:
                 ps               : Show task table
                 where taskid     : Show stack frames for a task
                 cancel taskid    : Cancel an indicated task
                 signal signame   : Send a Unix signal
                 stacktrace       : Print a stack trace from the event loop thread
                 console          : Switch to async Python REPL
                 quit             : Leave the monitor

``aiomonitor`` also supports async python console inside a running event loop
so you can explore the state of your application::

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

To leave the console type ``exit()``::

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
