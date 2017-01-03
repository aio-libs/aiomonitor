"""Debugging monitor for asyncio with asynchronous python REPL capablities

To enable the monitor, just use context manager protocol with start function::

    import asyncio
    import aiomonitor

    loop = asyncio.get_event_loop()
    with aiomonitor.start_monitor(loop=loop):
        print("Now you can connect with: nc localhost 50101")
        loop.run_forever()

Alternatively you can use more verbose try/finally approach::

    m = Monitor()
    m.start()
    try:
        loop.run_forever()
    finally:
        m.close()
"""

from .monitor import (Monitor, start_monitor,
                      MONITOR_HOST, MONITOR_PORT, CONSOLE_PORT)


__all__ = ('Monitor', 'start_monitor', 'MONITOR_HOST', 'MONITOR_PORT',
           'CONSOLE_PORT')
__version__ = '0.2.1'
