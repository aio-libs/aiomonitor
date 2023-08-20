from __future__ import annotations

import dataclasses
from importlib.metadata import version
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    AsyncContextManager,
    Dict,
    Mapping,
    Tuple,
    TypedDict,
    cast,
)

import trafaret as t
from aiohttp import web
from jinja2 import Environment, PackageLoader, select_autoescape

from ..utils import all_tasks
from .utils import check_params

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


async def show_list_page(request: web.Request) -> web.Response:
    class Params(TypedDict):
        list_type: str

    ctx: WebUIContext = request.app["ctx"]
    nav_info, nav_items = get_navigation_info(request.path)
    template = ctx.jenv.get_template(nav_info.template)
    async with cast(
        AsyncContextManager[Params],
        check_params(
            request,
            t.Dict(
                {
                    t.Key("list_type", default="running"): t.Enum(
                        "running", "terminated"
                    ),
                }
            ),
        ),
    ) as params:
        output = template.render(
            navigation=nav_items,
            page={
                "title": nav_info.title,
            },
            current_list_type=params["list_type"],
            list_types=[
                {"id": "running", "title": "Running"},
                {"id": "terminated", "title": "Terminated"},
            ],
            num_monitored_tasks=len(all_tasks(ctx.monitor._monitored_loop)),
        )
        return web.Response(body=output, content_type="text/html")


async def show_about_page(request: web.Request) -> web.Response:
    ctx: WebUIContext = request.app["ctx"]
    nav_info, nav_items = get_navigation_info(request.path)
    template = ctx.jenv.get_template(nav_info.template)
    output = template.render(
        navigation=nav_items,
        page={
            "title": nav_info.title,
        },
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


class ListFilterParams(TypedDict):
    filter: str
    persistent: bool


list_filter_params_check = t.Dict(
    {
        t.Key("filter", default=""): t.String(allow_blank=True),
        t.Key("persistent", default=False): t.ToBool,
    }
)


async def get_live_task_list(request: web.Request) -> web.Response:
    ctx: WebUIContext = request.app["ctx"]
    async with cast(
        AsyncContextManager[ListFilterParams],
        check_params(
            request,
            list_filter_params_check,
        ),
    ) as params:
        tasks = ctx.monitor.format_live_task_list(
            params["filter"],
            params["persistent"],
        )
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
                        "isRoot": t.created_location == "-",
                    }
                    for t in tasks
                ]
            }
        )


async def get_terminated_task_list(request: web.Request) -> web.Response:
    ctx: WebUIContext = request.app["ctx"]
    async with cast(
        AsyncContextManager[ListFilterParams],
        check_params(
            request,
            list_filter_params_check,
        ),
    ) as params:
        tasks = ctx.monitor.format_terminated_task_list(
            params["filter"],
            params["persistent"],
        )
        return web.json_response(
            data={
                "tasks": [
                    {
                        "task_id": t.task_id,
                        "name": t.name,
                        "coro": t.coro,
                        "started_since": t.started_since,
                        "terminated_since": t.terminated_since,
                    }
                    for t in tasks
                ]
            }
        )


async def cancel_task(request: web.Request) -> web.Response:
    class Params(TypedDict):
        task_id: str

    ctx: WebUIContext = request.app["ctx"]
    async with cast(
        AsyncContextManager[Params],
        check_params(
            request,
            t.Dict(
                {
                    t.Key("task_id"): t.String,
                }
            ),
        ),
    ) as params:
        try:
            await ctx.monitor.cancel_monitored_task(params["task_id"])
            return web.json_response(
                data={"msg": f"Successfully cancelled {params['task_id']}"},
            )
        except ValueError as e:
            return web.json_response(
                status=404,
                data={"msg": repr(e)},
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
    app.router.add_route("GET", "/", show_list_page)
    app.router.add_route("GET", "/about", show_about_page)
    app.router.add_route("GET", "/api/version", get_version)
    app.router.add_route("POST", "/api/task-count", get_task_count)
    app.router.add_route("POST", "/api/live-tasks", get_live_task_list)
    app.router.add_route("POST", "/api/terminated-tasks", get_terminated_task_list)
    app.router.add_route("DELETE", "/api/task", cancel_task)
    app.router.add_static("/static", Path(__file__).parent / "static")
    return app
