The Monitor
===========

``aiomonitor.monitor``
----------------------

.. module:: aiomonitor.monitor
.. currentmodule:: aiomonitor.monitor

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

.. autofunction:: start_monitor()

.. class:: Monitor

   .. automethod:: start()

   .. automethod:: close()

   .. autoattribute:: closed

   .. autoattribute:: prompt

   .. autoproperty:: host

   .. autoproperty:: port
