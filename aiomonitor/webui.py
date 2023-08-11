from __future__ import annotations

import dataclasses
from importlib.metadata import version
from typing import TYPE_CHECKING

from aiohttp import web

from .utils import all_tasks

if TYPE_CHECKING:
    from .monitor import Monitor


@dataclasses.dataclass
class WebUIContext:
    monitor: Monitor


async def index(request: web.Request) -> web.Response:
    pkg_version = version("aiomonitor")
    ctx: WebUIContext = request.app["ctx"]
    return web.json_response(
        {
            "version": pkg_version,
            "num_monitored_tasks": len(all_tasks(ctx.monitor._monitored_loop)),
        }
    )


async def init_webui(monitor: Monitor) -> web.Application:
    app = web.Application()
    app["ctx"] = WebUIContext(
        monitor=monitor,
    )
    app.router.add_route("GET", "/", index)
    return app
