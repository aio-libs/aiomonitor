Tutorial
========

Lets create simple aiohttp_ application, and see how ``aiomonitor`` can
integrate with it.

Basic aiohttp server
--------------------

.. code:: python

    import asyncio

    import aiomonitor
    from aiohttp import web

    # Simple handler that returns response after 100s
    async def simple(request):
        loop = request.app.loop

        print('Start sleeping')
        await asyncio.sleep(100)
        return web.Response(text="Simple answer")

    loop = asyncio.get_event_loop()
    # create application and register route create route
    app = web.Application(loop=loop)
    app.router.add_get('/simple', simple)

    # init monitor just before run_app
    with aiomonitor.start_monitor(loop):
        # run application with built in aoihttp run_app function
        web.run_app(app, port=8090, host='localhost')

Lets save this code in file ``simple_srv.py``, so we can run it with command::

    $ python simple_srv.py
    ======== Running on http://localhost:8090 ========
    (Press CTRL+C to quit)

Connection over telnet
----------------------

And now it is possible to connect to the running application from separate
terminal, by execution ``nc`` command, immediately ``aiomonitor`` will
respond with prompt::

    $ telnet localhost 20101
    Asyncio Monitor: 1 tasks running
    Type help for commands
    monitor >>>

*aiomonitor* packaged with own telnet client, just in case you do not have
``nc`` or other related utility::

    $ python -m aiomonitor.cli
    Asyncio Monitor: 1 tasks running
    Type help for commands
    monitor >>>

Once connection established, one can type commands, for instance ``help``::

    monitor >>> help
    Available Commands are:
                 cancel taskid: Cancel an indicated task
                 console: Switch to async Python REPL
                 ps: Show task table
                 quit: Leave the monitor
                 signal signame: Send a Unix signal
                 stacktrace: Print a stack trace from the event loop thread
                 where taskid: Show stack frames for a task

Library will respond with list of supported commands:

* *ps* -- shows table of alive tasks with their id and state
* *where* -- prints stack frame for the task, taskid must be supplied
* *cancel* -- command cancels task, taskid must be supplied
* *signal* -- command sends unix signal to the app process
* *stacktrace* -- prints a stack trace from the event loop thread
* *console* -- switch to python REPL
* *quit* -- stops telnet session

Additional commands can be added by subclassing ``Monitor``, see below :ref:`<cust-commands>`.


Python REPL
-----------

``aiomonitor`` supports also async python console inside running event loop
so you can explore state of your application::

    monitor >>> console
    Python 3.5.2 (default, Oct 11 2016, 05:05:28)
    [GCC 4.2.1 Compatible Apple LLVM 8.0.0 (clang-800.0.38)] on darwin
    Type "help", "copyright", "credits" or "license" for more information.
    ---
    This console is running in an asyncio event loop.
    It allows you to wait for coroutines using the 'await' syntax.
    Try: await asyncio.sleep(1, result=3)
    ---
    >>>

Now you may execute regular function as well as coroutines by
adding ``await`` keyword::

    >>> import aiohttp
    >>> session = aiohttp.ClientSession()
    >>> resp = await session.get('http://python.org')
    >>> resp.status
    200
    >>> data = await resp.read()
    >>> len(data)
    47373
    >>>

To leave console type ``exit()``::

    >>> exit()
    monitor >>>


Expose Local Variables in Python REPL
-------------------------------------

Local variables can be exposed in Python REPL by passing additional
``locals`` dictionary with mapping variable name in console to the value.

.. code:: python

    locals = {"foo": "bar"}
    with aiomonitor.start_monitor(loop):
        web.run_app(app, port=8090, host='localhost')


As result variable ``foo`` available in console::

    monitor >>> console
    >>> foo
    >>> bar
    >>> exit()
    monitor >>>


.. _cust-commands:

Adding custom commands
----------------------

By employing a custom ``Monitor`` subclass, we can add our own commands to the
telnet REPL. These are simply methods with names starting with `do_`. These methods
can use the in- and outgoing REPL sockets `self._sin` and `self._sout` for IO,
like `self._sout.write(string)` to print to the REPL.

Any parameters to the method will receive their value as a string, if they are meant
to be used as e.g. numbers, manual casting is needed.

.. code:: python

    class MyMon(Monitor):
        @alt_names('moc own')
        def do_my_own_command(self, some_argument):
            """This is a short description

            The first line of the doc will be shown in the help overview, this rest
            will only show up in the "help my_own_command" output.
            This command will have aliases "moc" and "own", just like "help" has "h"
            and "?".
            """
            results = self._do_stuff(self._locals['my_app_instance'])
            self._sout.write('The results are: {}\n'.format(results))

This custom command will be able to do anything you could do in the python REPL,
so you can add custom shortcuts here, that would be tedious to do manually in
the console.

By using the "locals" argument to ``start_monitor`` you can give any of your
commands access to anything they might need to do their jobs.

Modify the basic behaviour of the command loop
----------------------------------------------

Like the standard library's cmd_ module, you can customise how the behaviour of the
Monitor in various ways, see :ref:`api_reference`.

.. _aiohttp: https://github.com/KeepSafe/aiohttp
