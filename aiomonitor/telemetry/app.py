from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from .prometheus import prometheus_exporter

if TYPE_CHECKING:
    from ..monitor import Monitor

from aiohttp import web


@dataclasses.dataclass
class TelemetryContext:
    monitor: Monitor


async def init_telemetry(monitor: Monitor) -> web.Application:
    app = web.Application()
    app["ctx"] = TelemetryContext(
        monitor=monitor,
    )
    app.router.add_route("GET", "/prometheus", prometheus_exporter)
    return app
