import asyncio

import aiomonitor

loop = asyncio.get_event_loop()
with aiomonitor.start_monitor(loop=loop) as monitor:
    print("Now you can connect with:")
    print(f"  python -m aiomonitor.cli -H {monitor.host} -p {monitor.port}")
    print("or")
    print(f"  telnet {monitor.host} {monitor.port}  # Linux only")
    loop.run_forever()
