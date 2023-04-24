import asyncio

import aiotools  # FIXME: replace with asyncio.TaskGroup in Python 3.11

import aiomonitor


async def inner2():
    await asyncio.sleep(100)


async def inner1():
    t = asyncio.create_task(inner2())
    await t


async def main():
    loop = asyncio.get_running_loop()
    with aiomonitor.start_monitor(loop, hook_task_factory=True):
        print("Starting...")
        async with aiotools.TaskGroup() as tg:
            for _ in range(10):
                tg.create_task(inner1())
        print("Done")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
