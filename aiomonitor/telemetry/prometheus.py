from __future__ import annotations

import asyncio
import io
import time
from typing import TYPE_CHECKING

from aiohttp import web

if TYPE_CHECKING:
    from .app import TelemetryContext


async def prometheus_exporter(request: web.Request) -> web.Response:
    ctx: TelemetryContext = request.app["ctx"]
    out = io.StringIO()
    print("# TYPE asyncio_tasks gauge", file=out)
    now = time.time_ns() // 1000  # unix timestamp in msec
    all_task_count = len(asyncio.all_tasks(ctx.monitor._monitored_loop))
    print(f"asyncio_running_tasks {all_task_count} {now}", file=out)
    # TODO: count per name of explicitly named tasks (using labels)
    return web.Response(body=out.getvalue())
