API
===

**aiomonitor** has tiny and simple to use API, just factory function and
class that support context management protocol. Starting a monitor is as
simple as opening a file.

.. code:: python

    import asyncio
    import aiomonitor

    loop = asyncio.get_event_loop()
    with aiomonitor.start_monitor(loop):
        print("Now you can connect with: nc localhost 50101")
        loop.run_forever()

Alternatively you can use more verbose try/finally approach but do not forget
call ``close()`` methods, to join thread and finalize resources:

.. code:: python

    m = Monitor()
    m.start()
    try:
        loop.run_forever()
    finally:
        m.close()

It is possible to subclass ``Monitor`` to add custom commands to it. These custom
commands are methods with names starting with `do_`. See examples.

Reference
---------

.. module:: aiomonitor
.. currentmodule:: aiomonitor

.. data:: MONITOR_HOST = '127.0.0.1'

    Specifies the default host for monitor, by default monitor binded to
    ``localhost``.

.. data:: MONITOR_PORT = 50101

    Specifies the default port for monitor, you can connect using telnet client

.. data:: CONSOLE_PORT = 50102

    Specifies the default port for asynchronous python REPL

.. function:: start_monitor(loop, monitor=Monitor, host=None, port=MONITOR_PORT,
                            console_port=CONSOLE_PORT, console_enabled=True,
                            locals=None)

    Factory function, creates instance of :class:`Monitor` and starts
    monitoring thread.

    :param Type[Monitor] monitor: Monitor class to use
    :param str host: hostname to serve monitor telnet server
    :param int port: monitor port, by default 50101
    :param int console_port: python REPL port, by default 50102
    :param bool console_enabled: flag indicates if python REPL is requred
        to start with instance of monitor.
    :param dict locals: dictionary with variables exposed in python console
        environment

.. class:: Monitor

    Class has same arguments as :func:`start_monitor`, except for the `monitor`
    argument.

   .. method:: start()

        Starts monitoring thread, where telnet server is executed.

   .. method:: close()

        Joins background thread, and cleans up resources.

   .. attribute:: Monitor.closed

        Flag indicates if monitor was closed, currntly instance of
        :class:`Monitor` can not be reused. For new monitor, new instance
        should be created.

   .. method:: do_<COMMAND>(sin, sout, ...)

        Subclasses of the Monitor class can define their own commands available in
        the REPL. See the tutorial :ref:`cust-commands`.

.. function:: aiomonitor.utils.alt_names(names)

        A decorator for the custom commands to define aliases, like `h` and `?`
        are aliases for the `help` command. `names` is a single string with a
        space separated list of aliases.
