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
        await asyncio.sleep(3.0)

    scope: weakref.WeakSet[asyncio.Task] = weakref.WeakSet()
    try:
        while True:
            await asyncio.sleep(1.0)
            if len(scope) < 10:
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


async def main(
    *,
    history_limit: int,
    num_timers: int,
) -> None:
    loop = asyncio.get_running_loop()
    log_timer_loop = logging.getLogger("demo.timer_loop")
    log_aiohttp_server = logging.getLogger("demo.aiohttp_server")
    with aiomonitor.start_monitor(
        loop,
        hook_task_factory=True,
        max_termination_history=history_limit,
    ):
        app = web.Application()
        app.router.add_get("/", simple)
        timer_loop_tasks = set()
        for idx in range(num_timers):
            timer_loop_tasks.add(
                asyncio.create_task(timer_loop(), name=f"timer-loop-{idx}")
            )
            log_timer_loop.info("started a timer loop (%d)", idx)
        app["timer_loop_tasks"] = timer_loop_tasks

        async def _shutdown_timer_loop_task(app: web.Application) -> None:
            for idx, t in enumerate(app["timer_loop_tasks"]):
                log_timer_loop.info("shutting down a timer loop (%d)", idx)
                t.cancel()
                await t

        app.on_cleanup.append(_shutdown_timer_loop_task)
        log_aiohttp_server.info(
            "started a sample aiohttp server: http://localhost:8090/"
        )
        await web._run_app(app, port=8090, host="localhost")


if __name__ == "__main__":
    logging.basicConfig()
    logging.getLogger("aiomonitor").setLevel(logging.DEBUG)
    logging.getLogger("demo").setLevel(logging.DEBUG)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--loop",
        type=LoopImpl,
        choices=list(LoopImpl),
        default=LoopImpl.ASYNCIO,
        help="The event loop implementation to use [default: asyncio]",
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        metavar="COUNT",
        default=10,
        help="Set the maximum number of task termination history [default: 10]",
    )
    parser.add_argument(
        "--num-timers",
        type=int,
        metavar="COUNT",
        default=5,
        help="Set the number of timer loop tasks to demonstrate persistent termination logs [default: 5]",
    )
    args = parser.parse_args()
    match args.loop:
        case LoopImpl.UVLOOP:
            uvloop.install()
        case _:
            pass
    try:
        asyncio.run(
            main(
                history_limit=args.history_limit,
                num_timers=args.num_timers,
            )
        )
    except KeyboardInterrupt:
        pass
