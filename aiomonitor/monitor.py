from __future__ import annotations

import asyncio
import functools
import logging
import os
import shlex
import signal
import sys
import threading
import time
import traceback
import weakref
from asyncio.coroutines import _format_coroutine  # type: ignore
from contextvars import ContextVar, copy_context
from datetime import timedelta
from types import TracebackType
from typing import Any, Dict, Final, List, Optional, TextIO, Tuple, Type

import click
from prompt_toolkit import PromptSession
from prompt_toolkit.application.current import get_app_session
from prompt_toolkit.contrib.telnet.server import TelnetConnection, TelnetServer
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.shortcuts import print_formatted_text
from terminaltables import AsciiTable

from . import console
from .task import TracedTask
from .utils import (
    AliasGroupMixin,
    _extract_stack_from_frame,
    _extract_stack_from_task,
    _filter_stack,
    _format_filename,
    _format_task,
    _format_timedelta,
    all_tasks,
    cancel_task,
    task_by_id,
)

__all__ = ("Monitor", "start_monitor")

log = logging.getLogger(__name__)
current_stdout: ContextVar[TextIO] = ContextVar("current_stdout")
command_done: ContextVar[asyncio.Event] = ContextVar("command_done")

MONITOR_HOST: Final = "127.0.0.1"
MONITOR_PORT: Final = 50101
CONSOLE_PORT: Final = 50102


@click.group(cls=AliasGroupMixin, add_help_option=False)
def monitor_cli():
    """
    To see the usage of each command, run them with "--help" option.
    """
    pass


def _get_current_stdout() -> TextIO:
    stdout = current_stdout.get(None)
    if stdout is None:
        return sys.stdout
    else:
        return stdout


def _get_current_stderr() -> TextIO:
    stdout = current_stdout.get(None)
    if stdout is None:
        return sys.stderr
    else:
        return stdout


class Monitor:
    _event_loop_thread_id: Optional[int] = None
    _cmd_prefix = "do_"
    _empty_result = object()

    intro = "\nAsyncio Monitor: {tasknum} task{s} running\nType help for available commands\n"  # noqa
    help_template = "{cmd_name} {arg_list}\n    {doc}\n"
    help_short_template = (
        "    {cmd_name}{cmd_arg_sep}{arg_list}: {doc_firstline}"  # noqa
    )

    console_locals: Dict[str, Any]
    _console_tasks: weakref.WeakSet[asyncio.Task[Any]]

    _created_traceback_chains: weakref.WeakKeyDictionary[
        asyncio.Task[Any],
        asyncio.Task[Any],
    ]
    _created_tracebacks: weakref.WeakKeyDictionary[
        asyncio.Task[Any], List[traceback.FrameSummary]
    ]
    _cancelled_traceback_chains: weakref.WeakKeyDictionary[
        asyncio.Task[Any],
        asyncio.Task[Any],
    ]
    _cancelled_tracebacks: weakref.WeakKeyDictionary[
        asyncio.Task[Any], List[traceback.FrameSummary]
    ]

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        *,
        host: str = MONITOR_HOST,
        port: int = MONITOR_PORT,
        console_port: int = CONSOLE_PORT,
        console_enabled: bool = True,
        hook_task_factory: bool = False,
        locals: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._monitored_loop = loop or asyncio.get_running_loop()
        self._host = host
        self._port = port
        self._console_port = console_port
        self._console_enabled = console_enabled
        if locals is None:
            self.console_locals = {"__name__": "__console__", "__doc__": None}
        else:
            self.console_locals = locals

        self.prompt = "monitor >>> "

        log.info("Starting aiomonitor at %s:%d", host, port)

        self._ui_thread = threading.Thread(target=self._server, args=(), daemon=True)
        self._closed = False
        self._started = False
        self._console_tasks = weakref.WeakSet()

        self._hook_task_factory = hook_task_factory
        self._created_traceback_chains = weakref.WeakKeyDictionary()
        self._created_tracebacks = weakref.WeakKeyDictionary()
        self._cancelled_traceback_chains = weakref.WeakKeyDictionary()
        self._cancelled_tracebacks = weakref.WeakKeyDictionary()

    def __repr__(self) -> str:
        name = self.__class__.__name__
        return "<{name}: {host}:{port}>".format(
            name=name, host=self._host, port=self._port
        )

    def start(self) -> None:
        assert not self._closed
        assert not self._started
        self._started = True
        self._original_task_factory = self._monitored_loop.get_task_factory()
        if self._hook_task_factory:
            self._monitored_loop.set_task_factory(self._create_task)
        self._event_loop_thread_id = threading.get_ident()
        self._ui_thread.start()

        # Override the Click's stdout/stderr reference cache functions
        # to let them use the correct stdout handler.
        click.utils._default_text_stdout = _get_current_stdout
        click.utils._default_text_stderr = _get_current_stderr

    @property
    def closed(self) -> bool:
        return self._closed

    def __enter__(self) -> Monitor:
        if not self._started:
            self.start()
        return self

    # exc_type should be Optional[Type[BaseException]], but
    # this runs into https://github.com/python/typing/issues/266
    # on Python 3.5.
    def __exit__(
        self,
        exc_type: Any,
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.close()

    def close(self) -> None:
        assert self._started, "The monitor must have been started to close it."
        if not self._closed:
            self._telnet_server_loop.call_soon_threadsafe(
                self._telnet_server_future.cancel,
            )
            self._ui_thread.join()
            self._monitored_loop.set_task_factory(self._original_task_factory)
            self._closed = True

    def _create_task(self, loop, coro) -> asyncio.Task:
        assert loop is self._monitored_loop
        try:
            parent_task = asyncio.current_task()
        except RuntimeError:
            parent_task = None
        task = TracedTask(coro, loop=self._monitored_loop)
        self._created_tracebacks[task] = _extract_stack_from_frame(sys._getframe())[
            :-1
        ]  # strip this wrapper method
        if parent_task is not None:
            self._created_traceback_chains[task] = parent_task
        return task

    def _server(self) -> None:
        asyncio.run(self._server_async())

    async def _server_async(self) -> None:
        loop = asyncio.get_running_loop()
        self._telnet_server_loop = loop
        self._telnet_server_future = loop.create_future()
        telnet_server = TelnetServer(
            interact=self._interact, host=self._host, port=self._port
        )
        telnet_server.start()
        try:
            await self._telnet_server_future
        except asyncio.CancelledError:
            pass
        finally:
            console_tasks = {*self._console_tasks}
            for console_task in console_tasks:
                console_task.cancel()
            await asyncio.gather(*console_tasks, return_exceptions=True)
            del console_tasks
            await asyncio.sleep(0.1)
            await telnet_server.stop()

    def _print_ok(self, msg: str) -> None:
        print_formatted_text(
            FormattedText(
                [
                    ("ansibrightgreen", "✓ "),
                    ("", msg),
                ]
            )
        )

    def _print_error(self, msg: str) -> None:
        print_formatted_text(
            FormattedText(
                [
                    ("ansibrightred", "✗ "),
                    ("", msg),
                ]
            )
        )

    async def _interact(self, connection: TelnetConnection) -> None:
        """
        The interactive loop for each telnet client connection.
        """
        await asyncio.sleep(0.3)  # wait until telnet negotiation is done
        tasknum = len(all_tasks(loop=self._monitored_loop))
        s = "" if tasknum == 1 else "s"
        print(self.intro.format(tasknum=tasknum, s=s), file=connection.stdout)
        current_stdout_token = current_stdout.set(connection.stdout)
        # NOTE: prompt_toolkit's all internal console output automatically uses
        #       an internal contextvar to keep the stdout consistent with the
        #       current telnet connection.
        prompt_session: PromptSession[str] = PromptSession()
        lastcmd = "noop"
        style_prompt = "#5fd7ff bold"
        try:
            while True:
                try:
                    user_input = (
                        await prompt_session.prompt_async(
                            FormattedText(
                                [
                                    (style_prompt, self.prompt),
                                ]
                            )
                        )
                    ).strip()
                except KeyboardInterrupt:
                    self._print_error("To terminate, press Ctrl+D or type 'exit'.")
                except (EOFError, asyncio.CancelledError):
                    return
                except Exception:
                    self._print_error(traceback.format_exc())
                else:
                    command_done_event = asyncio.Event()
                    command_done_token = command_done.set(command_done_event)
                    try:
                        if not user_input and lastcmd is not None:
                            user_input = lastcmd
                        args = shlex.split(user_input)
                        term_size = prompt_session.output.get_size()
                        ctx = copy_context()
                        ctx.run(
                            monitor_cli.main,
                            args,
                            prog_name="",
                            obj=self,
                            standalone_mode=False,  # type: ignore
                            max_content_width=term_size.columns,
                        )
                        await command_done_event.wait()
                        if args[0] == "console":
                            lastcmd = "noop"
                        else:
                            lastcmd = user_input
                    except (click.BadParameter, click.UsageError) as e:
                        self._print_error(str(e))
                    except asyncio.CancelledError:
                        return
                    except Exception:
                        self._print_error(traceback.format_exc())
                    finally:
                        command_done.reset(command_done_token)
        finally:
            current_stdout.reset(current_stdout_token)


def auto_command_done(cmdfunc):
    @functools.wraps(cmdfunc)
    def _inner(ctx: click.Context, *args, **kwargs):
        command_done_event = command_done.get()
        try:
            return cmdfunc(ctx, *args, **kwargs)
        finally:
            command_done_event.set()

    return _inner


def auto_async_command_done(cmdfunc):
    @functools.wraps(cmdfunc)
    async def _inner(ctx: click.Context, *args, **kwargs):
        command_done_event = command_done.get()
        try:
            return await cmdfunc(ctx, *args, **kwargs)
        finally:
            command_done_event.set()

    return _inner


def custom_help_option(cmdfunc):
    """
    A custom help option to ensure setting `command_done_event`.
    """

    @auto_command_done
    def show_help(ctx: click.Context, param: click.Parameter, value: bool) -> None:
        if not value:
            return
        click.echo(ctx.get_help(), color=ctx.color)
        ctx.exit()

    return click.option(
        "--help",
        is_flag=True,
        expose_value=False,
        is_eager=True,
        callback=show_help,
        help="Show the help message",
    )(cmdfunc)


@monitor_cli.command(name="noop", hidden=True)
@auto_command_done
def do_noop(ctx: click.Context) -> None:
    pass


@monitor_cli.command(name="help", aliases=["?", "h"])
@custom_help_option
@auto_command_done
def do_help(ctx: click.Context) -> None:
    """Show the list of commands"""
    click.echo(monitor_cli.get_help(ctx))


@monitor_cli.command(name="signal")
@click.argument("signame", type=str)
@custom_help_option
@auto_command_done
def do_signal(ctx: click.Context, signame: str) -> None:
    """Send a Unix signal"""
    self: Monitor = ctx.obj
    if hasattr(signal, signame):
        os.kill(os.getpid(), getattr(signal, signame))
        self._print_ok(f"Sent signal to {signame} PID {os.getpid()}")
    else:
        self._print_error(f"Unknown signal {signame}")


@monitor_cli.command(name="stacktrace", aliases=["st", "stack"])
@custom_help_option
@auto_command_done
def do_stacktrace(ctx: click.Context) -> None:
    """Print a stack trace from the event loop thread"""
    self: Monitor = ctx.obj
    stdout = _get_current_stdout()
    tid = self._event_loop_thread_id
    assert tid is not None
    frame = sys._current_frames()[tid]
    traceback.print_stack(frame, file=stdout)


@monitor_cli.command(name="cancel")
@click.argument("taskid", type=int)
@custom_help_option
@auto_command_done
def do_cancel(ctx: click.Context, taskid: int) -> None:
    """Cancel an indicated task"""
    self: Monitor = ctx.obj
    task = task_by_id(taskid, self._monitored_loop)
    if task:
        fut = asyncio.run_coroutine_threadsafe(
            cancel_task(task), loop=self._monitored_loop
        )
        fut.result(timeout=3)
        self._print_ok(f"Cancelled task {taskid}")
    else:
        self._print_error(f"No task {taskid}")


@monitor_cli.command(name="exit", aliases=["q", "quit"])
@custom_help_option
@auto_command_done
def do_exit(ctx: click.Context) -> None:
    """Leave the monitor client session"""
    raise asyncio.CancelledError("exit by user")


@monitor_cli.command(name="console")
@custom_help_option
def do_console(ctx: click.Context) -> None:
    """Switch to async Python REPL"""
    self: Monitor = ctx.obj
    if not self._console_enabled:
        self._print_error("Python console is disabled for this session!")
        return

    @auto_async_command_done
    async def _console(ctx: click.Context) -> None:
        h, p = self._host, self._console_port
        log.info("Starting aioconsole at %s:%d", h, p)
        app_session = get_app_session()
        server = await console.start(
            self._host,
            self._console_port,
            self.console_locals,
            self._monitored_loop,
        )
        try:
            await console.proxy(
                app_session.input,
                app_session.output,
                self._host,
                self._console_port,
            )
        except asyncio.CancelledError:
            return
        finally:
            await console.close(server, self._monitored_loop)
            log.info("Terminated aioconsole at %s:%d", h, p)
            self._print_ok("The console session is closed.")

    # Since we are already inside the UI's event loop,
    # spawn the async command function as a new task and let it
    # set `command_done_event` internally.
    task = asyncio.create_task(_console(ctx))
    self._console_tasks.add(task)


@monitor_cli.command(name="ps", aliases=["p"])
@custom_help_option
@auto_command_done
def do_ps(ctx: click.Context) -> None:
    """Show task table"""
    headers = (
        "Task ID",
        "State",
        "Name",
        "Coroutine",
        "Created Location",
        "Since",
    )
    self: Monitor = ctx.obj
    stdout = _get_current_stdout()
    table_data: List[Tuple[str, str, str, str, str, str]] = [headers]

    for task in sorted(all_tasks(loop=self._monitored_loop), key=id):
        taskid = str(id(task))
        if task:
            coro = _format_coroutine(task.get_coro()).partition(" ")[0]
            creation_stack = self._created_tracebacks.get(task)
            # Some values are masked as "-" when they are unavailable
            # if it's the root task/coro or if the task factory is not applied.
            if not creation_stack:
                created_location = "-"
            else:
                creation_stack = _filter_stack(creation_stack)
                fn = _format_filename(creation_stack[-1].filename)
                lineno = creation_stack[-1].lineno
                created_location = f"{fn}:{lineno}"
            if isinstance(task, TracedTask):
                running_since = _format_timedelta(
                    timedelta(
                        seconds=(time.monotonic() - task._started_at),
                    )
                )
            else:
                running_since = "-"
            table_data.append(
                (
                    taskid,
                    task._state,
                    task.get_name(),
                    coro,
                    created_location,
                    running_since,
                )
            )
    table = AsciiTable(table_data)
    table.inner_row_border = False
    table.inner_column_border = False
    stdout.write(f"{len(table_data)} tasks running\n")
    stdout.write(table.table)
    stdout.write("\n")
    stdout.flush()


@monitor_cli.command(name="where", aliases=["w"])
@click.argument("taskid", type=int)
@custom_help_option
@auto_command_done
def do_where(ctx: click.Context, taskid: int) -> None:
    """Show stack frames and its task creation chain of a task"""
    self: Monitor = ctx.obj
    stdout = _get_current_stdout()
    depth = 0
    task = task_by_id(taskid, self._monitored_loop)
    if task is None:
        self._print_error(f"No task {taskid}")
        return
    task_chain: List[asyncio.Task[Any]] = []
    while task is not None:
        task_chain.append(task)
        task = self._created_traceback_chains.get(task)
    prev_task = None
    for task in reversed(task_chain):
        if depth == 0:
            stdout.write(
                "Stack of the root task or coroutine scheduled in the event loop (most recent call last):\n\n"
            )
        elif depth > 0:
            assert prev_task is not None
            stdout.write(
                "Stack of %s when creating the next task (most recent call last):\n\n"
                % _format_task(prev_task)
            )
        stack = self._created_tracebacks.get(task)
        if stack is None:
            stdout.write(
                "  No stack available (maybe it is a native code or the event loop itself)\n"
            )
        else:
            stack = _filter_stack(stack)
            stdout.write("".join(traceback.format_list(stack)))
        prev_task = task
        depth += 1
        stdout.write("\n")
    task = task_chain[0]
    stdout.write("Stack of %s (most recent call last):\n\n" % _format_task(task))
    stack = _extract_stack_from_task(task)
    if not stack:
        stdout.write("  No stack available for %s" % _format_task(task))
    else:
        stdout.write("".join(traceback.format_list(stack)))
    stdout.write("\n")


def start_monitor(
    loop: asyncio.AbstractEventLoop,
    *,
    monitor: Type[Monitor] = Monitor,
    host: str = MONITOR_HOST,
    port: int = MONITOR_PORT,
    console_port: int = CONSOLE_PORT,
    console_enabled: bool = True,
    hook_task_factory: bool = False,
    locals: Optional[Dict[str, Any]] = None,
) -> Monitor:
    m = monitor(
        loop,
        host=host,
        port=port,
        console_port=console_port,
        console_enabled=console_enabled,
        hook_task_factory=hook_task_factory,
        locals=locals,
    )
    m.start()
    return m
