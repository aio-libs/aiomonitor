import asyncio

import aiomonitor


async def main() -> None:
    loop = asyncio.get_running_loop()
    with aiomonitor.start_monitor(loop=loop) as monitor:
        print("Now you can connect with:")
        print(f"  python -m aiomonitor.cli -H {monitor.host} -p {monitor.port}")
        print("or")
        print(f"  telnet {monitor.host} {monitor.port}  # Linux only")
        loop.run_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
