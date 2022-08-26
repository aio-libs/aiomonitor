import asyncio
import uvloop

import aiomonitor
from aiohttp import web


async def inner2():
    await asyncio.sleep(100)


async def inner1():
    t = asyncio.create_task(inner2())
    await t


async def simple(request):
    print('Start sleeping')
    t = asyncio.create_task(inner1())
    await t
    return web.Response(text='Simple answer')


async def main():
    loop = asyncio.get_running_loop()
    app = web.Application()
    app.router.add_get('/simple', simple)
    with aiomonitor.start_monitor(loop, hook_task_factory=True):
        await web._run_app(app, port=8090, host='localhost')


uvloop.install()
asyncio.run(main())
