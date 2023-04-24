import asyncio

import uvloop
from aiohttp import web

import aiomonitor


async def simple(request: web.Request) -> web.Response:
    await asyncio.sleep(10)
    await asyncio.sleep(10)
    return web.Response(text="Simple answer")


async def hello(request: web.Request) -> web.StreamResponse:
    resp = web.StreamResponse()
    name = request.match_info.get("name", "Anonymous")
    answer = ("Hello, " + name).encode("utf8")
    resp.content_length = len(answer)
    resp.content_type = "text/plain"
    await resp.prepare(request)
    await asyncio.sleep(100)
    await resp.write(answer)
    await resp.write_eof()
    return resp


async def main() -> None:
    loop = asyncio.get_running_loop()
    app = web.Application()
    app.router.add_get("/simple", simple)
    app.router.add_get("/hello/{name}", hello)
    app.router.add_get("/hello", hello)
    host, port = "localhost", 8090
    with aiomonitor.start_monitor(loop):
        web.run_app(app, port=port, host=host)


if __name__ == "__main__":
    uvloop.install()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
