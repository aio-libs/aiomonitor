from __future__ import annotations

import dataclasses
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Mapping, Tuple

from aiohttp import web
from jinja2 import Environment, PackageLoader, select_autoescape

from ..utils import all_tasks

if TYPE_CHECKING:
    from ..monitor import Monitor


@dataclasses.dataclass
class WebUIContext:
    monitor: Monitor
    jenv: Environment


@dataclasses.dataclass
class NavigationItem:
    title: str
    template: str
    current: bool


nav_menus: Mapping[str, NavigationItem] = {
    "/": NavigationItem(
        title="Dashboard",
        template="index.html",
        current=False,
    ),
    "/about": NavigationItem(
        title="About",
        template="about.html",
        current=False,
    ),
}


def get_navigation_info(
    route: str,
) -> Tuple[NavigationItem, Mapping[str, NavigationItem]]:
    nav_items: Dict[str, NavigationItem] = {}
    current_item = None
    for path, item in nav_menus.items():
        is_current = path == route
        nav_items[path] = NavigationItem(item.title, item.template, is_current)
        if is_current:
            current_item = item
    if current_item is None:
        raise web.HTTPNotFound
    return current_item, nav_items


async def root_page(request: web.Request) -> web.Response:
    ctx: WebUIContext = request.app["ctx"]
    nav_info, nav_items = get_navigation_info(request.path)
    template = ctx.jenv.get_template(nav_info.template)
    output = template.render(
        navigation=nav_items,
        num_monitored_tasks=len(all_tasks(ctx.monitor._monitored_loop)),
    )
    return web.Response(body=output, content_type="text/html")


async def get_version(request: web.Request) -> web.Response:
    return web.json_response(
        data={
            "value": version("aiomonitor"),
        }
    )


async def get_task_count(request: web.Request) -> web.Response:
    ctx: WebUIContext = request.app["ctx"]
    num_monitored_tasks = len(all_tasks(ctx.monitor._monitored_loop))
    return web.json_response(
        data={
            "value": num_monitored_tasks,
        }
    )


async def get_live_task_list(request: web.Request) -> web.Response:
    ctx: WebUIContext = request.app["ctx"]
    tasks = ctx.monitor.get_live_task_list("", False)
    return web.json_response(
        data={
            "tasks": [
                {
                    "task_id": t.task_id,
                    "state": t.state,
                    "name": t.name,
                    "coro": t.coro,
                    "created_location": t.created_location,
                    "since": t.since,
                }
                for t in tasks
            ]
        }
    )


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
    app.router.add_route("GET", "/api/version", get_version)
    app.router.add_route("POST", "/api/task-count", get_task_count)
    app.router.add_route("POST", "/api/live-tasks", get_live_task_list)
    app.router.add_static("/static", Path(__file__).parent / "static")
    return app
