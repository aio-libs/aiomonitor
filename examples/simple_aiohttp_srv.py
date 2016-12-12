import asyncio

import aiomonitor
from aiohttp import web


async def simple(request):
    loop = request.app.loop
    print('Start sleeping')
    await asyncio.sleep(100, loop=loop)
    return web.Response(text="Simple answer")


async def init(loop):
    app = web.Application(loop=loop)
    app.router.add_get('/simple', simple)
    return app

loop = asyncio.get_event_loop()
app = loop.run_until_complete(init(loop))

with aiomonitor.start_monitor(loop=loop):
    web.run_app(app, port=8090, host='localhost')
