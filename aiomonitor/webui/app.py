from __future__ import annotations

import dataclasses
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiohttp import web
from jinja2 import Environment, PackageLoader, select_autoescape

from ..utils import all_tasks

if TYPE_CHECKING:
    from ..monitor import Monitor


@dataclasses.dataclass
class WebUIContext:
    monitor: Monitor
    jenv: Environment


def get_navigation_info(route: str):
    nav_menus: dict[str, dict[str, Any]] = {
        "/": {
            "title": "Dashboard",
            "template": "index.html",
            "current": False,
        },
        "/about": {
            "title": "About",
            "template": "about.html",
            "current": False,
        },
    }
    nav_items = {}
    current_item = None
    for path, item in nav_menus.items():
        nav_items[path] = {
            **item,
        }
        if path == route:
            nav_items[path]["current"] = True
            current_item = item
    if current_item is None:
        raise web.HTTPNotFound
    return current_item, nav_items


async def root_page(request: web.Request) -> web.Response:
    ctx: WebUIContext = request.app["ctx"]
    nav_info, nav_items = get_navigation_info(request.path)
    template = ctx.jenv.get_template(nav_info["template"])
    output = template.render(
        navigation=nav_items,
        num_monitored_tasks=len(all_tasks(ctx.monitor._monitored_loop)),
    )
    return web.Response(body=output, content_type="text/html")


async def get_version(request: web.Request) -> web.Response:
    ctx: WebUIContext = request.app["ctx"]
    output = ctx.jenv.from_string("{{ v }}").render(v=version("aiomonitor"))
    return web.Response(body=output, content_type="text/html")


async def get_task_count(request: web.Request) -> web.Response:
    ctx: WebUIContext = request.app["ctx"]
    num_monitored_tasks = len(all_tasks(ctx.monitor._monitored_loop))
    output = ctx.jenv.from_string("{{ v }}").render(v=num_monitored_tasks)
    return web.Response(body=output, content_type="text/html")


async def init_webui(monitor: Monitor) -> web.Application:
    jenv = Environment(
        loader=PackageLoader("aiomonitor.webui"), autoescape=select_autoescape()
    )
    app = web.Application()
    app["ctx"] = WebUIContext(
        monitor=monitor,
        jenv=jenv,
    )
    app.router.add_route("GET", "/", root_page)
    app.router.add_route("GET", "/about", root_page)
    app.router.add_route("GET", "/fragment/version", get_version)
    app.router.add_route("GET", "/fragment/task-count", get_task_count)
    app.router.add_static("/static", Path(__file__).parent / "static")
    return app
