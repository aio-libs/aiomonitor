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
        print("Now you can connect with: nc localhost 20101")
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

.. _api-reference:

Reference
---------

.. module:: aiomonitor
.. currentmodule:: aiomonitor

.. data:: MONITOR_HOST = '127.0.0.1'

    Specifies the default host to bind the services for the monitor

    .. warning::

       Since aiomonitor exposes the internal states of the traced process, never bind it to
       publicly accessible address to prevent potential security breaches and denial of services!

.. data:: MONITOR_TERMUI_PORT = 20101

    Specifies the default telnet port for teh monitor where you can connect using a telnet client

.. data:: MONITOR_WEBUI_PORT = 20102

    Specifies the default HTTP port for the monitor where you can connect using a web browser

.. data:: CONSOLE_PORT = 20103

    Specifies the default port for asynchronous python REPL

.. function:: start_monitor(loop, monitor=Monitor, host=None, port=MONITOR_TERMUI_PORT, webui_port=MONITOR_WEBUI_PORT, console_port=CONSOLE_PORT, console_enabled=True, locals=None)
    :single-line-parameter-list:

    Factory function, creates instance of :class:`Monitor` and starts
    monitoring thread.

    :param Type[Monitor] monitor: Monitor class to use
    :param str host: hostname to serve monitor telnet server
    :param int port: monitor port (terminal UI), by default 20101
    :param int webui_port: monitor port (web UI), by default 20102
    :param int console_port: python REPL port, by default 20103
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

   .. attribute:: Monitor.prompt

        The string that prompts you to enter a command, defaults to 'monitor >>> '

   .. attribute:: Monitor.intro

        Template for the intro text you see when you connect to the running monitor.
        Available fields to be filled in are:
        - tasknum: Number of tasks in the event loop
        - s: 's' if tasknum is >1 or 0

   .. attribute:: Monitor.help_template

        Template string that gets filled in and displayed when `help <COMMAND>` is
        executed. Available fields to be filled in are:
        - cmd_name: the commands name
        - arg_list: the arguments it takes
        - doc: the docstring of the command method
        - doc_firstline: first line of the docstring

   .. attribute:: Monitor.help_short_template

        Like `help_template`, but gets called when `help` is executed, once per
        available command

   .. attribute:: Monitor.lastcmd

        Stores the last entered command line, whether it properly executed or not.

   .. method:: precmd(comm: str, args: Sequence[str]) -> Tuple[do_<COMMAND> function: Callable, args: Sequence[Any]]

        Gets executed by the loop before the command is run, and is acutally
        resonsible for resolving the entered command string to the method that gets
        called. If you overwrite this method, you can use self._getcmd(comm) to
        resolve it. Afterwards the default implementation uses
        list(self._map_args(cmd_method, args)) to map the given arguments to the
        methods type annotation.

   .. method:: postcmd(comm: str, args: Sequence[Any], result: Any, exception: Optional[Exception]) -> None

        Runs after the command unconditionally. It takes the entered command string,
        the arguments (with type annotation applied, see above), the return value of
        the command, and the exception the command raised.
        If the command raised an exception, the result will be set to
        `self._empty_result`; if no exception was raised, it will be set to None.
        The default implementation does nothing.

   .. method:: emptyline()

        Gets executed when an empty line is entered. A line is considered empty
        when `line.strip() == ''` is true.
        By default takes the last run command (stored in `self.lastcmd`) and runs it
        again, using `self._command_dispatch(self.lastcmd)`

   .. method:: default(comm: str, args: Sequence[str]) -> None

        Gets run when precmd cannot find a command method to execute.

   .. method:: do_<COMMAND>(...)

        Subclasses of the Monitor class can define their own commands available in
        the REPL. See the tutorial :ref:`cust-commands`.

.. decorator:: aiomonitor.utils.alt_names(names)

        A decorator for the custom commands to define aliases, like `h` and `?`
        are aliases for the `help` command. `names` is a single string with a
        space separated list of aliases.
