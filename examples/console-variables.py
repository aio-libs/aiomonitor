import asyncio

import aiomonitor


async def main():
    loop = asyncio.get_running_loop()
    data = {
        "a": 123,
        "b": 456,
    }
    with aiomonitor.start_monitor(loop=loop) as monitor:
        monitor.console_locals["data"] = data
        print("Now you can connect with:")
        print(f"  python -m aiomonitor.cli -H {monitor.host} -p {monitor.port}")
        print("or")
        print(f"  telnet {monitor.host} {monitor.port}  # Linux only")
        print("\nTry 'console' command and inspect 'data' variable.")
        # run forever until interrupted
        while True:
            await asyncio.sleep(60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
