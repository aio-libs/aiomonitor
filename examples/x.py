import asyncio


async def do():
    await asyncio.sleep(100)


async def main():
    t = asyncio.create_task(do())
    await asyncio.sleep(1)
    t.cancel()
    await t


asyncio.run(main())
