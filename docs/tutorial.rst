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
    # create application and register route create route
    app = web.Application(loop=loop)
    app.router.add_get('/simple', simple)

    # init monitor just befor run_app
    with aiomonitor.start_monitor(loop):
        # run application with built in aoihttp run_app function
        web.run_app(app, port=8090, host='localhost')

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


.. _aiohttp: https://github.com/KeepSafe/aiohttp
