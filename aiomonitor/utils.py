import asyncio
import contextlib
import linecache
import selectors
import sys
import telnetlib
import traceback
from concurrent.futures import Future  # noqa
from typing import Callable, IO, Any, Optional, List, Set  # noqa

import aioconsole

from .mypy_types import Loop, OptLocals


Server = asyncio.AbstractServer  # noqa


def _get_stack(task: 'asyncio.Task[Any]') -> List[Any]:
    frames = []  # type: List[Any]
    coro = task._coro  # type: ignore
    while coro:
        f = getattr(coro, 'cr_frame', getattr(coro, 'gi_frame', None))

        if f is not None:
            frames.append(f)

        coro = getattr(coro, 'cr_await', getattr(coro, 'gi_yieldfrom', None))
    return frames


def _format_stack(task: 'asyncio.Task[Any]') -> str:
    extracted_list = []
    checked = set()  # type: Set[str]
    for f in _get_stack(task):
        lineno = f.f_lineno
        co = f.f_code
        filename = co.co_filename
        name = co.co_name
        if filename not in checked:
            checked.add(filename)
            linecache.checkcache(filename)
        line = linecache.getline(filename, lineno, f.f_globals)
        extracted_list.append((filename, lineno, name, line))
    if not extracted_list:
        resp = 'No stack for %r' % task
    else:
        resp = 'Stack for %r (most recent call last):\n' % task
        resp += ''.join(traceback.format_list(extracted_list))  # type: ignore
    return resp


def task_by_id(taskid: int, loop: Loop) -> 'Optional[asyncio.Task[Any]]':
    tasks = all_tasks(loop=loop)
    return next(filter(lambda t: id(t) == taskid, tasks), None)


async def cancel_task(task: 'asyncio.Task[Any]') -> None:
    with contextlib.suppress(asyncio.CancelledError):
        task.cancel()
        await task


def init_console_server(host: str,
                        port: int,
                        locals: OptLocals,
                        loop: Loop) -> 'Future[Server]':
    def _factory(streams: Any = None) -> aioconsole.AsynchronousConsole:
        return aioconsole.AsynchronousConsole(
            locals=locals, streams=streams, loop=loop)

    coro = aioconsole.start_interactive_server(
        host=host, port=port, factory=_factory, loop=loop)
    console_future = asyncio.run_coroutine_threadsafe(coro, loop=loop)
    return console_future


async def close_server(server: Server) -> None:
    server.close()
    await server.wait_closed()


_TelnetSelector = getattr(
    selectors, 'PollSelector',
    selectors.SelectSelector)  # Type: selectors.BaseSelector


def console_proxy(sin: IO[str], sout: IO[str], host: str, port: int) -> None:
    tn = telnetlib.Telnet()
    with contextlib.closing(tn):
        tn.open(host, port, timeout=10)
        with _TelnetSelector() as selector:
            selector.register(tn, selectors.EVENT_READ)
            selector.register(sin, selectors.EVENT_READ)

            while True:
                for key, _ in selector.select():
                    if key.fileobj is tn:
                        try:
                            data = tn.read_eager()
                        except EOFError:
                            print('*Connection closed by remote host*')
                            return

                        if data:
                            sout.write(data.decode('utf-8'))
                            sout.flush()
                    else:
                        resp = sin.readline()
                        if not resp:
                            return
                        tn.write(resp.encode('utf-8'))


def alt_names(names: str) -> Callable[..., Any]:
    """Add alternative names to you custom commands.

    `names` is a single string with a space separated list of aliases for the
    decorated command.
    """
    names_split = names.split()

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        func.alt_names = names_split  # type: ignore
        return func
    return decorator


def all_tasks(loop: Loop) -> 'Set[asyncio.Task[Any]]':
    if sys.version_info >= (3, 7):
        tasks = asyncio.all_tasks(loop=loop)  # type: Set[asyncio.Task[Any]]
    else:
        tasks = asyncio.Task.all_tasks(loop=loop)
    return tasks
