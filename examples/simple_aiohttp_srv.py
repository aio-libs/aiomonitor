import asyncio
import logging

import uvloop
from aiohttp import web

import aiomonitor


async def inner2() -> None:
    await asyncio.sleep(100)


async def inner1(tg: asyncio.TaskGroup) -> None:
    t = tg.create_task(inner2())
    await t


async def simple(request: web.Request) -> web.Response:
    print("Start sleeping")
    async with asyncio.TaskGroup() as tg:
        tg.create_task(inner1(tg))
    print("Finished sleeping")
    return web.Response(text="Simple answer")


async def main() -> None:
    loop = asyncio.get_running_loop()
    app = web.Application()
    app.router.add_get("/simple", simple)
    with aiomonitor.start_monitor(loop, hook_task_factory=True):
        await web._run_app(app, port=8090, host="localhost")


if __name__ == "__main__":
    logging.basicConfig()
    logging.getLogger("aiomonitor").setLevel(logging.DEBUG)
    uvloop.install()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
