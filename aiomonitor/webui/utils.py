import json
from contextlib import asynccontextmanager as actxmgr
from typing import AsyncIterator, Type, TypeVar

from aiohttp import web
from pydantic import BaseModel, ValidationError


class APIParams(BaseModel):
    pass


T_APIParams = TypeVar("T_APIParams", bound=APIParams)


@actxmgr
async def check_params(
    request: web.Request,
    model_class: Type[T_APIParams],
) -> AsyncIterator[T_APIParams]:
    try:
        if request.method in ("GET", "DELETE"):
            data = dict(request.query)
        else:
            body = await request.post()
            data = {k: v for k, v in body.items()}
        params = model_class.model_validate(data)
        yield params
    except ValidationError as e:
        error_messages = []
        for error in e.errors():
            field = ".".join(str(loc) for loc in error["loc"])
            message = error["msg"]
            error_messages.append(f"{field}: {message}")
        detail = "\n".join(error_messages)
        raise web.HTTPBadRequest(
            content_type="application/json",
            body=json.dumps({"msg": "Invalid parameters", "detail": detail}),
        ) from None
    except Exception as e:
        raise web.HTTPInternalServerError(
            content_type="application/json",
            body=json.dumps({"msg": "Internal server error", "detail": repr(e)}),
        ) from e
