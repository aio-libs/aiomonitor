from __future__ import annotations

import asyncio
import contextlib
import linecache
import sys
import traceback
from asyncio.coroutines import _format_coroutine  # type: ignore
from datetime import timedelta
from pathlib import Path
from types import FrameType
from typing import Any, List, Optional, Set

import click

from .mypy_types import Loop


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
    stdlib = (
        f"{sys.prefix}/lib/python{sys.version_info.major}.{sys.version_info.minor}/"
    )
    site_pkg = f"{sys.prefix}/lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages/"
    home = f"{Path.home()}/"
    cwd = f"{Path.cwd()}/"
    if filename.startswith(site_pkg):
        return "<sitepkg>/" + filename[len(site_pkg) :]
    if filename.startswith(stdlib):
        return "<stdlib>/" + filename[len(stdlib) :]
    if filename.startswith(cwd):
        return "<cwd>/" + filename[len(cwd) :]
    if filename.startswith(home):
        return "<home>/" + filename[len(home) :]
    return filename


def _format_timedelta(td: timedelta) -> str:
    seconds = int(td.total_seconds())
    periods = [
        ("y", 60 * 60 * 24 * 365),
        ("m", 60 * 60 * 24 * 30),
        ("d", 60 * 60 * 24),
        ("h", 60 * 60),
        (":", 60),
        ("", 1),
    ]
    parts = []
    for period_name, period_seconds in periods:
        period_value, seconds = divmod(seconds, period_seconds)
        if period_name in (":", ""):
            parts.append(f"{period_value:02d}{period_name}")
        else:
            if period_value == 0:
                continue
            parts.append(f"{period_value}{period_name}")
    parts.append(f"{td.microseconds / 1e6:.03f}"[1:])
    return "".join(parts)


def _filter_stack(
    stack: List[traceback.FrameSummary],
) -> List[traceback.FrameSummary]:
    """
    Filters out commonly repeated frames of the asyncio internals from the given stack.
    """
    # strip the task factory frame in the vanilla event loop
    if (
        stack[-1].filename.endswith("asyncio/base_events.py")
        and stack[-1].name == "create_task"
    ):
        stack = stack[:-1]
    # strip the loop.create_task frame
    if (
        stack[-1].filename.endswith("asyncio/tasks.py")
        and stack[-1].name == "create_task"
    ):
        stack = stack[:-1]
    _cut_idx = 0
    for _cut_idx, f in reversed(list(enumerate(stack))):
        # uvloop
        if f.filename.endswith("asyncio/runners.py") and f.name == "run":
            break
        # vanilla
        if f.filename.endswith("asyncio/events.py") and f.name == "_run":
            break
    return stack[_cut_idx + 1 :]


def _extract_stack_from_task(
    task: asyncio.Task[Any],
) -> List[traceback.FrameSummary]:
    """
    Extracts the stack as a list of FrameSummary objects from an asyncio task.
    """
    frames: List[Any] = []
    coro = task._coro  # type: ignore
    while coro:
        f = getattr(coro, "cr_frame", getattr(coro, "gi_frame", None))
        if f is not None:
            frames.append(f)
        coro = getattr(coro, "cr_await", getattr(coro, "gi_yieldfrom", None))
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


def _extract_stack_from_frame(frame: FrameType) -> List[traceback.FrameSummary]:
    stack = traceback.StackSummary.extract(traceback.walk_stack(frame))
    stack.reverse()
    return stack


class AliasGroupMixin(click.Group):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._commands = {}
        self._aliases = {}

    def command(self, *args, **kwargs):
        aliases = kwargs.pop("aliases", [])
        decorator = super().command(*args, **kwargs)

        def _decorator(f):
            cmd = decorator(click.pass_context(f))
            if aliases:
                self._commands[cmd.name] = aliases
                for alias in aliases:
                    self._aliases[alias] = cmd.name
            return cmd

        return _decorator

    def group(self, *args, **kwargs):
        aliases = kwargs.pop("aliases", [])
        # keep the same class type
        kwargs["cls"] = type(self)
        decorator = super().group(*args, **kwargs)
        if not aliases:
            return decorator

        def _decorator(f):
            cmd = decorator(f)
            if aliases:
                self._commands[cmd.name] = aliases
                for alias in aliases:
                    self._aliases[alias] = cmd.name
            return cmd

        return _decorator

    def get_command(self, ctx, cmd_name):
        if cmd_name in self._aliases:
            cmd_name = self._aliases[cmd_name]
        command = super().get_command(ctx, cmd_name)
        if command:
            return command

    def format_commands(self, ctx, formatter):
        commands = []
        for subcommand in self.list_commands(ctx):
            cmd = self.get_command(ctx, subcommand)
            # What is this, the tool lied about a command. Ignore it
            if cmd is None:
                continue
            if cmd.hidden:
                continue
            if subcommand in self._commands:
                aliases = ",".join(sorted(self._commands[subcommand]))
                subcommand = "{0} ({1})".format(subcommand, aliases)
            commands.append((subcommand, cmd))

        # allow for 3 times the default spacing
        if len(commands):
            limit = formatter.width - 6 - max(len(cmd[0]) for cmd in commands)
            rows = []
            for subcommand, cmd in commands:
                help = cmd.get_short_help_str(limit)
                rows.append((subcommand, help))
            if rows:
                with formatter.section("Commands"):
                    formatter.write_dl(rows)


def task_by_id(
    taskid: int, loop: asyncio.AbstractEventLoop
) -> Optional[asyncio.Task[Any]]:
    tasks = all_tasks(loop=loop)
    return next(filter(lambda t: id(t) == taskid, tasks), None)


async def cancel_task(task: asyncio.Task[Any]) -> None:
    with contextlib.suppress(asyncio.CancelledError):
        task.cancel()
        await task


def all_tasks(loop: Loop) -> Set[asyncio.Task[Any]]:
    if sys.version_info >= (3, 7):
        tasks = asyncio.all_tasks(loop=loop)
    else:
        tasks = asyncio.Task.all_tasks(loop=loop)
    return tasks
