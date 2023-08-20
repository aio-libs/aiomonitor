import json
from contextlib import asynccontextmanager as actxmgr
from typing import Any, AsyncIterator

import trafaret as t
from aiohttp import web


@actxmgr
async def check_params(
    request: web.Request,
    checker: t.Trafaret,
) -> AsyncIterator[Any]:
    try:
        params = checker.check(request.query)
        yield params
    except t.DataError as e:
        raise web.HTTPBadRequest(
            content_type="application/json",
            body=json.dumps({"msg": "Invalid parameters", "data": e.as_dict()}),
        )
