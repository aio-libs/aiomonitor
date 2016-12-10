import asyncio
from aiomonitor import Monitor

loop = asyncio.get_event_loop()
with Monitor(loop=loop):
    print("Now you can connect with: nc localhost 50101")
    loop.run_forever()
