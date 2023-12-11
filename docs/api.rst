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

.. toctree::
   :maxdepth: 2

   reference/index
