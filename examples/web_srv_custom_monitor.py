import asyncio
from typing import Optional

import click
import requests
import uvloop
from aiohttp import web

import aiomonitor
from aiomonitor.termui.commands import (
    auto_command_done,
    custom_help_option,
    monitor_cli,
)


async def simple(request: web.Request) -> web.Response:
    await asyncio.sleep(10)
    return web.Response(text="Simple answer")


async def hello(request: web.Request) -> web.StreamResponse:
    resp = web.StreamResponse()
    name = request.match_info.get("name", "Anonymous")
    answer = ("Hello, " + name).encode("utf8")
    resp.content_length = len(answer)
    resp.content_type = "text/plain"
    await resp.prepare(request)
    await asyncio.sleep(10)
    await resp.write(answer)
    await resp.write_eof()
    return resp


@monitor_cli.command(name="hello")
@click.argument("name", optional=True)
@custom_help_option
@auto_command_done
def do_hello(ctx: click.Context, name: Optional[str] = None) -> None:
    """Using the /hello GET interface

    There is one optional argument, "name".  This name argument must be
    provided with proper URL escape codes, like %20 for spaces.
    """
    name = "" if name is None else "/" + name
    r = requests.get("http://localhost:8090/hello" + name)
    click.echo(r.text + "\n")


async def main() -> None:
    loop = asyncio.get_running_loop()
    app = web.Application()
    app.router.add_get("/simple", simple)
    app.router.add_get("/hello/{name}", hello)
    app.router.add_get("/hello", hello)
    host, port = "localhost", 8090
    with aiomonitor.start_monitor(loop, locals=locals()):
        web.run_app(app, port=port, host=host)


if __name__ == "__main__":
    uvloop.install()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
