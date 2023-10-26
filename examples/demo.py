# NOTE: This example requires Python 3.11 or higher.
# Use `requirements-dev.txt` to install dependencies.

from __future__ import annotations

import argparse
import asyncio
import contextlib
import enum
import logging
import weakref

import uvloop
from aiohttp import web

import aiomonitor
from aiomonitor.task import preserve_termination_log


class LoopImpl(enum.StrEnum):
    ASYNCIO = "asyncio"
    UVLOOP = "uvloop"


async def inner2() -> None:
    await asyncio.sleep(100)


async def inner1(tg: asyncio.TaskGroup) -> None:
    t = tg.create_task(inner2())
    await t


@preserve_termination_log
async def timer_loop() -> None:
    async def interval_work():
        await asyncio.sleep(1.5)

    scope: weakref.WeakSet[asyncio.Task] = weakref.WeakSet()
    try:
        while True:
            await asyncio.sleep(2.0)
            t = asyncio.create_task(interval_work(), name="interval-worker")
            scope.add(t)
    except asyncio.CancelledError:
        for t in {*scope}:
            with contextlib.suppress(asyncio.CancelledError):
                t.cancel()
                await t


async def simple(request: web.Request) -> web.Response:
    log = logging.getLogger("demo.aiohttp_server.simple")
    log.info("Start sleeping")
    async with asyncio.TaskGroup() as tg:
        tg.create_task(inner1(tg))
    log.info("Finished sleeping")
    return web.Response(text="Simple answer")


async def main() -> None:
    loop = asyncio.get_running_loop()
    with aiomonitor.start_monitor(loop, hook_task_factory=True):
        app = web.Application()
        app.router.add_get("/", simple)
        app["timer_loop_task"] = asyncio.create_task(timer_loop())

        async def _shutdown_timer_loop_task(app: web.Application) -> None:
            t = app["timer_loop_task"]
            t.cancel()
            await t

        app.on_cleanup.append(_shutdown_timer_loop_task)
        await web._run_app(app, port=8090, host="localhost")


if __name__ == "__main__":
    logging.basicConfig()
    logging.getLogger("aiomonitor").setLevel(logging.DEBUG)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--loop",
        type=LoopImpl,
        choices=list(LoopImpl),
        help="The event loop implementation to use",
    )
    args = parser.parse_args()
    match args.loop:
        case LoopImpl.UVLOOP:
            uvloop.install()
        case _:
            pass
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
