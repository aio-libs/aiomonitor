from __future__ import annotations

import asyncio
import contextlib
import linecache
import selectors
import sys
import telnetlib
import traceback
from asyncio.coroutines import _format_coroutine
from datetime import timedelta
from concurrent.futures import Future  # noqa
from pathlib import Path
from types import FrameType
from typing import Callable, IO, Any, Optional, List, Set, Sequence  # noqa

import aioconsole

from .mypy_types import Loop, OptLocals


Server = asyncio.AbstractServer  # noqa


def _format_task(task: asyncio.Task[Any]) -> str:
    """
    A simpler version of task's repr()
    """
    coro = _format_coroutine(task.get_coro()).partition(" ")[0]
    return f"<Task name={task.get_name()} coro={coro}>"


def _format_filename(filename: str) -> str:
    """
    Simplifies the site-pkg directory path of the given source filename.
    """
    stdlib = f"{sys.prefix}/lib/python{sys.version_info.major}.{sys.version_info.minor}/"
    site_pkg = f"{sys.prefix}/lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages/"
    home = f"{Path.home()}/"
    cwd = f"{Path.cwd()}/"
    if filename.startswith(site_pkg):
        return "<sitepkg>/" + filename[len(site_pkg):]
    if filename.startswith(stdlib):
        return "<stdlib>/" + filename[len(stdlib):]
    if filename.startswith(cwd):
        return "<cwd>/" + filename[len(cwd):]
    if filename.startswith(home):
        return "<home>/" + filename[len(home):]
    return filename


def _format_timedelta(td: timedelta) -> str:
    seconds = int(td.total_seconds())
    periods = [
        ('y', 60*60*24*365),
        ('m', 60*60*24*30),
        ('d', 60*60*24),
        ('h', 60*60),
        (':', 60),
        ('',  1)
    ]
    parts = []
    for period_name, period_seconds in periods:
        period_value, seconds = divmod(seconds, period_seconds)
        if period_name in (':', ''):
            parts.append(f"{period_value:02d}{period_name}")
        else:
            if period_value == 0:
                continue
            parts.append(f"{period_value}{period_name}")
    parts.append(f"{td.microseconds / 1e6:.03f}"[1:])
    return "".join(parts)


def _filter_stack(stack: List[traceback.FrameSummary]) -> List[traceback.FrameSummary]:
    """
    Filters out commonly repeated frames of the asyncio internals from the given stack.
    """
    # strip the task factory frame in the vanilla event loop
    if stack[-1].filename.endswith('asyncio/base_events.py') and stack[-1].name == 'create_task':
        stack = stack[:-1]
    # strip the loop.create_task frame
    if stack[-1].filename.endswith('asyncio/tasks.py') and stack[-1].name == 'create_task':
        stack = stack[:-1]
    cut_idx = 0
    for cut_idx, f in reversed(list(enumerate(stack))):
        # uvloop
        if f.filename.endswith('asyncio/runners.py') and f.name == 'run':
            break
        # vanilla
        if f.filename.endswith('asyncio/events.py') and f.name == '_run':
            break
    return stack[cut_idx + 1:]


def _extract_stack_from_task(task: asyncio.Task[Any]) -> List[traceback.FrameSummary]:
    """
    Extracts the stack as a list of FrameSummary objects from an asyncio task.
    """
    frames: List[Any] = []
    coro = task._coro  # type: ignore
    while coro:
        f = getattr(coro, 'cr_frame', getattr(coro, 'gi_frame', None))
        if f is not None:
            frames.append(f)
        coro = getattr(coro, 'cr_await', getattr(coro, 'gi_yieldfrom', None))
    extracted_list = []
    checked: Set[str] = set()
    for f in frames:
        lineno = f.f_lineno
        co = f.f_code
        filename = co.co_filename
        name = co.co_name
        if filename not in checked:
            checked.add(filename)
            linecache.checkcache(filename)
        line = linecache.getline(filename, lineno, f.f_globals)
        extracted_list.append(traceback.FrameSummary(filename, lineno, name, line=line))
    return extracted_list


def _extract_stack_from_frame(frame: FrameType) -> Sequence[traceback.FrameSummary]:
    stack = traceback.StackSummary.extract(traceback.walk_stack(frame))
    stack.reverse()
    return stack


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
