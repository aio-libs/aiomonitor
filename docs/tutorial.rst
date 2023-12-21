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

    # A simple handler that returns response after 100s
    async def simple(request):
        print("Start sleeping")
        await asyncio.sleep(100)
        return web.Response(text="Simple answer")

    async def main():
       # create application and register route create route
       app = web.Application()
       app.router.add_get("/simple", simple)

       # init monitor just before run_app
       loop = asyncio.get_running_loop()
       with aiomonitor.start_monitor(loop):
           await web._run_app(app, port=20101, host="localhost")

    if __name__ == "__main__":
        asyncio.run(main())

Lets save this code in file ``simple_srv.py``, so we can run it with command::

    $ python simple_srv.py
    ======== Running on http://localhost:20101 ========
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
``telnet`` client in the host::

    $ python -m aiomonitor.cli
    Asyncio Monitor: 1 tasks running
    Type help for commands
    monitor >>>

Once connection established, one can type commands, for instance ``help``::

    monitor >>> help
    Usage: help [OPTIONS] COMMAND [ARGS]...

      To see the usage of each command, run them with "--help" option.

    Commands:
      cancel (ca)             Cancel an indicated task
      console                 Switch to async Python REPL
      exit (q,quit)           Leave the monitor client session
      help (?,h)              Show the list of commands
      ps (p)                  Show task table
      ps-terminated (pst,pt)  List recently terminated/cancelled tasks
      signal                  Send a Unix signal
      stacktrace (st,stack)   Print a stack trace from the event loop thread
      where (w)               Show stack frames and the task creation chain of a task
      where-terminated (wt)   Show stack frames and the termination/cancellation chain of a task

Additional commands can be added by defining a Click command function injected into :ref:`the monitor CLI <monitor-cli>`, see below :ref:`cust-commands`.

.. versionchanged:: 0.5.0

   As of 0.5.0, you must use a telnet client that implements the actual telnet
   protocol. Previously a simple socket-to-console redirector like ``nc``
   worked, but now it requires explicit negotiation of the terminal type to
   provide advanced terminal features including auto-completion of commands.


Python REPL
-----------

``aiomonitor`` supports also async python console inside running event loop
so you can explore state of your application::

    monitor >>> console
    Python 3.11.7 (main, Dec  9 2023, 21:41:50) [GCC 11.4.0] on linux
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
    with aiomonitor.start_monitor(loop, locals=locals):
        web.run_app(app, port=20101, host='127.0.0.1')


As result variable ``foo`` available in console::

    monitor >>> console
    >>> foo
    bar
    >>> exit()
    monitor >>>


.. _cust-commands:

Adding custom commands
----------------------

By defining a new :func:`Click command <click.command>` on :ref:`the monitor CLI <monitor-cli>`, we can add our own commands to the
telnet REPL.  Use the standard :func:`click.echo()` to print something in the telnet console.
You may also add additional arguments and options just like a normal Click application.

.. code:: python

    import aiohttp
    import click
    import requests
    from aiomonitor.termui.commands import (
        auto_async_command_done,
        auto_command_done,
        custom_help_option,
        monitor_cli,
    )

    @monitor_cli.command(name="hello")
    @click.argument("name", optional=True)
    @custom_help_option
    @auto_command_done  # sync version
    def do_hello(ctx: click.Context, name: Optional[str] = None) -> None:
        """An example command to say hello to another HTTP server."""
        name = "unknown" if name is None else name
        r = requests.get("http://example.com/hello/" + name)
        click.echo(r.text + "\n")

    @monitor_cli.command(name="hello-async")
    @click.argument("name", optional=True)
    @custom_help_option
    @auto_async_command_done  # async version
    async def do_async_hello(ctx: click.Context, name: Optional[str] = None) -> None:
        """An example command to asynchronously say hello to another HTTP server."""
        name = "unknown" if name is None else name
        async with aiohttp.ClientSession() as sess:
            async with sess.get("http://example.com/hello/" + name) as resp:
                click.echo(await resp.text())

This custom command will be able to do anything you could do in the python REPL,
so you can add custom shortcuts here, that would be tedious to do manually in
the console.

``auto_command_done`` or ``auto_async_command_done`` is requried to ensure that
the command function notifies its completion to the telnet's main loop coroutine.

``custom_help_option`` is required to provide a ``--help`` option to your command
that is compatible with completion notification like above.

By using the "locals" argument to ``start_monitor`` you can give any of your
commands access to anything they might need to do their jobs by accessing
them via ``ctx.obj.console_locals`` in the command function.


.. _aiohttp: https://github.com/aio-libs/aiohttp
