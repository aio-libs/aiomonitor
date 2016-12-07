import asyncio
import uvloop
from aiomonitor import Monitor

from aiohttp.web import Application, Response, StreamResponse, run_app


async def simple(request):
    loop = request.app.loop
    await asyncio.sleep(10, loop=loop)
    await asyncio.sleep(10, loop=loop)
    return Response(text="Simple answer")


async def hello(request):
    resp = StreamResponse()
    name = request.match_info.get('name', 'Anonymous')
    answer = ('Hello, ' + name).encode('utf8')
    resp.content_length = len(answer)
    resp.content_type = 'text/plain'
    await resp.prepare(request)
    await asyncio.sleep(100, loop=loop)
    resp.write(answer)
    await resp.write_eof()
    return resp


async def init(loop):
    app = Application(loop=loop)
    app.router.add_get('/simple', simple)
    app.router.add_get('/hello/{name}', hello)
    app.router.add_get('/hello', hello)
    return app

# loop = asyncio.get_event_loop()
loop = uvloop.new_event_loop()
asyncio.set_event_loop(loop)
app = loop.run_until_complete(init(loop))

with Monitor(loop=loop):
    run_app(app, port=8090, host='localhost')
