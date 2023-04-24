"""Debugging monitor for asyncio app with asynchronous python REPL capabilities

To enable the monitor, just use context manager protocol with start function::

    import asyncio
    import aiomonitor

    loop = asyncio.get_event_loop()
    with aiomonitor.start_monitor():
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

from importlib.metadata import version

from .monitor import (
    CONSOLE_PORT,
    MONITOR_HOST,
    MONITOR_PORT,
    Monitor,
    monitor_cli,
    start_monitor,
)

__all__ = (
    "Monitor",
    "monitor_cli",
    "start_monitor",
    "MONITOR_HOST",
    "MONITOR_PORT",
    "CONSOLE_PORT",
)
__version__ = version("aiomonitor")
