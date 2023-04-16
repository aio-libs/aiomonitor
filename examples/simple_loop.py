import asyncio
import aiomonitor

loop = asyncio.get_event_loop()
with aiomonitor.start_monitor():
    print('Now you can connect with: nc localhost 50101')
    loop.run_forever()
