from __future__ import annotations

import asyncio
import contextvars
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
from typing import (
    Any,
    Awaitable,
    Coroutine,
    Dict,
    Final,
    Generator,
    Iterable,
    List,
    Optional,
    TextIO,
    Tuple,
    Type,
    TypeVar,
    cast,
)

import click
import janus
from click.parser import split_arg_string
from click.shell_completion import CompletionItem, _resolve_context, _resolve_incomplete
from prompt_toolkit import PromptSession
from prompt_toolkit.application.current import get_app_session
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.contrib.telnet.server import TelnetConnection, TelnetServer
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.shortcuts import print_formatted_text
from terminaltables import AsciiTable

from . import console
from .task import TracedTask, persistent_coro
from .types import CancellationChain, TerminatedTaskInfo
from .utils import (
    AliasGroupMixin,
    _extract_stack_from_exception,
    _extract_stack_from_frame,
    _extract_stack_from_task,
    _filter_stack,
    _format_filename,
    _format_task,
    _format_terminated_task,
    _format_timedelta,
    all_tasks,
    cancel_task,
    get_default_args,
    task_by_id,
)

__all__ = (
    "Monitor",
    "monitor_cli",
    "start_monitor",
)

log = logging.getLogger(__name__)
current_monitor: ContextVar[Monitor] = ContextVar("current_monitor")
current_stdout: ContextVar[TextIO] = ContextVar("current_stdout")
command_done: ContextVar[asyncio.Event] = ContextVar("command_done")

MONITOR_HOST: Final = "127.0.0.1"
MONITOR_PORT: Final = 50101
CONSOLE_PORT: Final = 50102

T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)


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


class ClickCompleter(Completer):
    def __init__(self, root_command: click.BaseCommand) -> None:
        self._root_command = root_command

    def get_completions(
        self,
        document: Document,
        complete_event: CompleteEvent,
    ) -> Iterable[Completion]:
        args = split_arg_string(document.current_line)
        incomplete = document.get_word_under_cursor()
        if incomplete and args and args[-1] == incomplete:
            args.pop()
        click_ctx = _resolve_context(self._root_command, {}, "", args)
        cmd_or_param, incomplete = _resolve_incomplete(click_ctx, args, incomplete)
        completions: List[CompletionItem] = cmd_or_param.shell_complete(
            click_ctx, incomplete
        )
        start_position = document.find_backwards(incomplete) or 0
        for completion in completions:
            yield Completion(
                completion.value,
                start_position=start_position,
            )


def complete_task_id(
    ctx: click.Context,
    param: click.Parameter,
    incomplete: str,
) -> Iterable[str]:
    # ctx here is created in the completer and does not have ctx.obj set as monitor.
    # We take the monitor instance from the global context variable instead.
    try:
        self: Monitor = current_monitor.get()
    except LookupError:
        return []
    return [
        task_id
        for task_id in map(str, sorted(map(id, all_tasks(loop=self._monitored_loop))))
        if task_id.startswith(incomplete)
    ][:10]


def complete_trace_id(
    ctx: click.Context,
    param: click.Parameter,
    incomplete: str,
) -> Iterable[str]:
    try:
        self: Monitor = current_monitor.get()
    except LookupError:
        return []
    return [
        trace_id
        for trace_id in map(str, sorted(self._terminated_tasks.keys()))
        if trace_id.startswith(incomplete)
    ][:10]


def complete_signal_names(
    ctx: click.Context,
    param: click.Parameter,
    incomplete: str,
) -> Iterable[str]:
    return [sig.name for sig in signal.Signals if sig.name.startswith(incomplete)]


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
        weakref.ReferenceType[asyncio.Task[Any]],
    ]
    _created_tracebacks: weakref.WeakKeyDictionary[
        asyncio.Task[Any], List[traceback.FrameSummary]
    ]
    _terminated_tasks: Dict[str, TerminatedTaskInfo]
    _terminated_history: List[str]
    _termination_info_queue: janus.Queue[TerminatedTaskInfo]
    _canceller_chain: Dict[str, str]
    _canceller_stacks: Dict[str, List[traceback.FrameSummary] | None]
    _cancellation_chain_queue: janus.Queue[CancellationChain]

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        *,
        host: str = MONITOR_HOST,
        port: int = MONITOR_PORT,
        console_port: int = CONSOLE_PORT,
        console_enabled: bool = True,
        hook_task_factory: bool = False,
        max_termination_history: int = 1000,
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

        self._closed = False
        self._started = False
        self._console_tasks = weakref.WeakSet()

        self._hook_task_factory = hook_task_factory
        self._created_traceback_chains = weakref.WeakKeyDictionary()
        self._created_tracebacks = weakref.WeakKeyDictionary()
        self._terminated_tasks = {}
        self._canceller_chain = {}
        self._canceller_stacks = {}
        self._terminated_history = []
        self._max_termination_history = max_termination_history

        self._ui_started = threading.Event()
        self._ui_thread = threading.Thread(target=self._ui_main, args=(), daemon=True)

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

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
        self._ui_started.wait()

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
            self._ui_loop.call_soon_threadsafe(
                self._ui_forever_future.cancel,
            )
            self._ui_thread.join()
            self._monitored_loop.set_task_factory(self._original_task_factory)
            self._closed = True

    async def _coro_wrapper(self, coro: Awaitable[T_co]) -> T_co:
        myself = asyncio.current_task()
        assert isinstance(myself, TracedTask)
        try:
            return await coro
        except BaseException as e:
            myself._termination_stack = _extract_stack_from_exception(e)[:-1]
            raise

    def _create_task(
        self,
        loop: asyncio.AbstractEventLoop,
        coro: Coroutine[Any, Any, T_co] | Generator[Any, None, T_co],
        *,
        name: str | None = None,
        context: contextvars.Context | None = None,
    ) -> asyncio.Future[T_co]:
        assert loop is self._monitored_loop
        try:
            parent_task = asyncio.current_task()
        except RuntimeError:
            parent_task = None
        persistent = coro in persistent_coro
        task = TracedTask(
            self._coro_wrapper(coro),  # type: ignore
            termination_info_queue=self._termination_info_queue.sync_q,
            cancellation_chain_queue=self._cancellation_chain_queue.sync_q,
            persistent=persistent,
            loop=self._monitored_loop,
            name=name,  # since Python 3.8
            context=context,  # since Python 3.11
        )
        task._orig_coro = cast(Coroutine[Any, Any, T_co], coro)
        self._created_tracebacks[task] = _extract_stack_from_frame(sys._getframe())[
            :-1
        ]  # strip this wrapper method
        if parent_task is not None:
            self._created_traceback_chains[task] = weakref.ref(parent_task)
        return task

    def _ui_main(self) -> None:
        asyncio.run(self._ui_main_async())

    async def _ui_main_async(self) -> None:
        loop = asyncio.get_running_loop()
        self._termination_info_queue = janus.Queue()
        self._cancellation_chain_queue = janus.Queue()
        self._ui_loop = loop
        self._ui_forever_future = loop.create_future()
        self._ui_termination_handler_task = asyncio.create_task(
            self._ui_handle_termination_updates()
        )
        self._ui_cancellation_handler_task = asyncio.create_task(
            self._ui_handle_cancellation_updates()
        )
        telnet_server = TelnetServer(
            interact=self._interact, host=self._host, port=self._port
        )
        telnet_server.start()
        await asyncio.sleep(0)
        self._ui_started.set()
        try:
            await self._ui_forever_future
        except asyncio.CancelledError:
            pass
        finally:
            console_tasks = {*self._console_tasks}
            for console_task in console_tasks:
                console_task.cancel()
            await asyncio.gather(*console_tasks, return_exceptions=True)
            self._ui_termination_handler_task.cancel()
            self._ui_cancellation_handler_task.cancel()
            await self._ui_termination_handler_task
            await self._ui_cancellation_handler_task
            await telnet_server.stop()

    async def _ui_handle_termination_updates(self) -> None:
        while True:
            try:
                update: TerminatedTaskInfo = (
                    await self._termination_info_queue.async_q.get()
                )
            except asyncio.CancelledError:
                return
            self._terminated_tasks[update.id] = update
            if not update.persistent:
                self._terminated_history.append(update.id)
            # canceller stack is already put in _ui_handle_cancellation_updates()
            if canceller_stack := self._canceller_stacks.pop(update.id, None):
                update.canceller_stack = canceller_stack
            while len(self._terminated_history) > self._max_termination_history:
                removed_id = self._terminated_history.pop(0)
                self._terminated_tasks.pop(removed_id, None)
                self._canceller_chain.pop(removed_id, None)
                self._canceller_stacks.pop(removed_id, None)

    async def _ui_handle_cancellation_updates(self) -> None:
        while True:
            try:
                update: CancellationChain = (
                    await self._cancellation_chain_queue.async_q.get()
                )
            except asyncio.CancelledError:
                return
            self._canceller_stacks[update.target_id] = update.canceller_stack
            self._canceller_chain[update.target_id] = update.canceller_id

    def print_ok(self, msg: str) -> None:
        print_formatted_text(
            FormattedText(
                [
                    ("ansibrightgreen", "✓ "),
                    ("", msg),
                ]
            )
        )

    def print_fail(self, msg: str) -> None:
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
        current_monitor_token = current_monitor.set(self)
        current_stdout_token = current_stdout.set(connection.stdout)
        # NOTE: prompt_toolkit's all internal console output automatically uses
        #       an internal contextvar to keep the stdout consistent with the
        #       current telnet connection.
        prompt_session: PromptSession[str] = PromptSession(
            completer=ClickCompleter(monitor_cli),
            complete_while_typing=False,
        )
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
                    self.print_fail("To terminate, press Ctrl+D or type 'exit'.")
                except (EOFError, asyncio.CancelledError):
                    return
                except Exception:
                    self.print_fail(traceback.format_exc())
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
                        self.print_fail(str(e))
                    except asyncio.CancelledError:
                        return
                    except Exception:
                        self.print_fail(traceback.format_exc())
                    finally:
                        command_done.reset(command_done_token)
        finally:
            current_stdout.reset(current_stdout_token)
            current_monitor.reset(current_monitor_token)


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
@click.argument("signame", type=str, shell_complete=complete_signal_names)
@custom_help_option
@auto_command_done
def do_signal(ctx: click.Context, signame: str) -> None:
    """Send a Unix signal"""
    self: Monitor = ctx.obj
    if hasattr(signal, signame):
        os.kill(os.getpid(), getattr(signal, signame))
        self.print_ok(f"Sent signal to {signame} PID {os.getpid()}")
    else:
        self.print_fail(f"Unknown signal {signame}")


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


@monitor_cli.command(name="cancel", aliases=["ca"])
@click.argument("taskid", shell_complete=complete_task_id)
@custom_help_option
@auto_command_done
def do_cancel(ctx: click.Context, taskid: str) -> None:
    """Cancel an indicated task"""
    self: Monitor = ctx.obj
    task_id = int(taskid)
    task = task_by_id(task_id, self._monitored_loop)
    if task:
        if self._monitored_loop == asyncio.get_running_loop():
            asyncio.create_task(cancel_task(task))
        else:
            fut = asyncio.run_coroutine_threadsafe(
                cancel_task(task), loop=self._monitored_loop
            )
            fut.result(timeout=3)
        self.print_ok(f"Cancelled task {task_id}")
    else:
        self.print_fail(f"No task {task_id}")


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
        self.print_fail("Python console is disabled for this session!")
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
            self.print_ok("The console session is closed.")

    # Since we are already inside the UI's event loop,
    # spawn the async command function as a new task and let it
    # set `command_done_event` internally.
    task = asyncio.create_task(_console(ctx))
    self._console_tasks.add(task)


@monitor_cli.command(name="ps", aliases=["p"])
@click.option("-f", "--filter", "filter_", help="filter by coroutine or task name")
@click.option("-p", "--persistent", is_flag=True, help="show only persistent tasks")
@custom_help_option
@auto_command_done
def do_ps(
    ctx: click.Context,
    filter_: str,
    persistent: bool,
) -> None:
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
    all_running_tasks = all_tasks(loop=self._monitored_loop)

    for task in sorted(all_running_tasks, key=id):
        taskid = str(id(task))
        if isinstance(task, TracedTask):
            coro_repr = _format_coroutine(task._orig_coro).partition(" ")[0]
            if persistent and task._orig_coro not in persistent_coro:
                continue
        else:
            coro_repr = _format_coroutine(task.get_coro()).partition(" ")[0]
            if persistent:
                # untracked tasks should be skipped when showing persistent ones only
                continue
        if filter_ and (filter_ not in coro_repr and filter_ not in task.get_name()):
            continue
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
                    seconds=(time.perf_counter() - task._started_at),
                )
            )
        else:
            running_since = "-"
        table_data.append(
            (
                taskid,
                task._state,
                task.get_name(),
                coro_repr,
                created_location,
                running_since,
            )
        )
    table = AsciiTable(table_data)
    table.inner_row_border = False
    table.inner_column_border = False
    if filter_ or persistent:
        stdout.write(
            f"{len(all_running_tasks)} tasks running "
            f"(showing {len(table_data) - 1} tasks)\n"
        )
    else:
        stdout.write(f"{len(all_running_tasks)} tasks running\n")
    stdout.write(table.table)
    stdout.write("\n")
    stdout.flush()


@monitor_cli.command(name="ps-terminated", aliases=["pt", "pst"])
@click.option("-f", "--filter", "filter_", help="filter by coroutine or task name")
@click.option("-p", "--persistent", is_flag=True, help="show only persistent tasks")
@custom_help_option
@auto_command_done
def do_ps_terminated(
    ctx: click.Context,
    filter_: str,
    persistent: bool,
) -> None:
    """List recently terminated/cancelled tasks"""
    headers = (
        "Trace ID",
        "Name",
        "Coro",
        "Since Started",
        "Since Terminated",
    )
    self: Monitor = ctx.obj
    stdout = _get_current_stdout()
    table_data: List[Tuple[str, str, str, str, str]] = [headers]
    terminated_tasks = self._terminated_tasks.values()
    for item in sorted(
        terminated_tasks,
        key=lambda info: info.terminated_at,
        reverse=True,
    ):
        if persistent and not item.persistent:
            continue
        if filter_ and (filter_ not in item.coro and filter_ not in item.name):
            continue
        run_since = _format_timedelta(
            timedelta(seconds=time.perf_counter() - item.started_at)
        )
        cancelled_since = _format_timedelta(
            timedelta(seconds=time.perf_counter() - item.terminated_at)
        )
        table_data.append(
            (
                str(item.id),
                item.name,
                item.coro,
                run_since,
                cancelled_since,
            )
        )
    table = AsciiTable(table_data)
    table.inner_row_border = False
    table.inner_column_border = False
    if filter_ or persistent:
        stdout.write(
            f"{len(terminated_tasks)} tasks terminated "
            f"(showing {len(table_data) - 1} tasks)\n"
        )
    else:
        stdout.write(
            f"{len(terminated_tasks)} tasks terminated (old ones may be stripped)\n"
        )
    stdout.write(table.table)
    stdout.write("\n")
    stdout.flush()


@monitor_cli.command(name="where", aliases=["w"])
@click.argument("taskid", shell_complete=complete_task_id)
@custom_help_option
@auto_command_done
def do_where(ctx: click.Context, taskid: str) -> None:
    """Show stack frames and the task creation chain of a task"""
    self: Monitor = ctx.obj
    stdout = _get_current_stdout()
    depth = 0
    task_id = int(taskid)
    task = task_by_id(task_id, self._monitored_loop)
    if task is None:
        self.print_fail(f"No task {task_id}")
        return
    task_chain: List[asyncio.Task[Any]] = []
    while task is not None:
        task_chain.append(task)
        task_ref = self._created_traceback_chains.get(task)
        task = task_ref() if task_ref is not None else None
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
                "  No stack available (maybe it is a native code, a synchronous callback function, or the event loop itself)\n"
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


@monitor_cli.command(name="where-terminated", aliases=["wt"])
@click.argument("trace_id", shell_complete=complete_trace_id)
@custom_help_option
@auto_command_done
def do_where_terminated(ctx: click.Context, trace_id: str) -> None:
    """Show stack frames and the termination/cancellation chain of a task"""
    self: Monitor = ctx.obj
    stdout = _get_current_stdout()
    depth = 0
    tinfo_chain: List[TerminatedTaskInfo] = []
    while trace_id is not None:
        tinfo_chain.append(self._terminated_tasks[trace_id])
        trace_id = self._canceller_chain.get(trace_id)  # type: ignore
    prev_tinfo = None
    for tinfo in reversed(tinfo_chain):
        if depth == 0:
            stdout.write(
                "Stack of the root task or coroutine scheduled in the event loop (most recent call last):\n\n"
            )
        elif depth > 0:
            assert prev_tinfo is not None
            stdout.write(
                "Stack of %s when creating the next task (most recent call last):\n\n"
                % _format_terminated_task(prev_tinfo)
            )
        stack = tinfo.canceller_stack
        if stack is None:
            stdout.write(
                "  No stack available (maybe it is a self-raised cancellation or exception)\n"
            )
        else:
            stack = _filter_stack(stack)
            stdout.write("".join(traceback.format_list(stack)))
        prev_tinfo = tinfo
        depth += 1
        stdout.write("\n")
    tinfo = tinfo_chain[0]
    stdout.write(
        "Stack of %s (most recent call last):\n\n" % _format_terminated_task(tinfo)
    )
    stack = tinfo.termination_stack
    if not stack:
        stdout.write(
            "  No stack available for %s (the task has run to completion)"
            % _format_terminated_task(tinfo)
        )
    else:
        stdout.write("".join(traceback.format_list(stack)))
    stdout.write("\n")


def start_monitor(
    loop: asyncio.AbstractEventLoop,
    *,
    monitor_cls: Type[Monitor] = Monitor,
    host: str = MONITOR_HOST,
    port: int = MONITOR_PORT,
    console_port: int = CONSOLE_PORT,
    console_enabled: bool = True,
    hook_task_factory: bool = False,
    max_termination_history: Optional[int] = None,
    locals: Optional[Dict[str, Any]] = None,
) -> Monitor:
    m = monitor_cls(
        loop,
        host=host,
        port=port,
        console_port=console_port,
        console_enabled=console_enabled,
        hook_task_factory=hook_task_factory,
        max_termination_history=max_termination_history
        or get_default_args(monitor_cls.__init__)["max_termination_history"],
        locals=locals,
    )
    m.start()
    return m
