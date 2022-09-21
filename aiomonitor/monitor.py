from __future__ import annotations

import asyncio
import inspect
import logging
import os
import signal
import sys
import threading
import time
import traceback
import weakref
from asyncio.coroutines import _format_coroutine  # type: ignore
from concurrent.futures import Future
from contextlib import suppress
from datetime import timedelta
from types import TracebackType
from typing import (
    Any,
    Callable,
    Generator,
    List,
    NamedTuple,
    Optional,
    Sequence,
    TextIO,
    Tuple,
    Type,
)

from prompt_toolkit import PromptSession
from prompt_toolkit.contrib.telnet.server import TelnetConnection, TelnetServer
from terminaltables import AsciiTable

from .mypy_types import Loop, OptLocals
from .task import TracedTask
from .utils import (
    _extract_stack_from_frame,
    _extract_stack_from_task,
    _filter_stack,
    _format_filename,
    _format_task,
    _format_timedelta,
    all_tasks,
    alt_names,
    cancel_task,
    close_server,
    console_proxy,
    init_console_server,
    task_by_id,
)

__all__ = ("Monitor", "start_monitor")
log = logging.getLogger(__name__)


MONITOR_HOST = "127.0.0.1"
MONITOR_PORT = 50101
CONSOLE_PORT = 50102


Server = asyncio.AbstractServer  # noqa


class CommandException(Exception):
    pass


class UnknownCommandException(CommandException):
    pass


class MultipleCommandException(CommandException):
    def __init__(self, cmds: List["CmdName"]) -> None:
        self.cmds = cmds
        super().__init__()


class ArgumentMappingException(CommandException):
    pass


CmdName = NamedTuple("CmdName", [("cmd_name", str), ("method_name", str)])


class Monitor:
    _event_loop_thread_id: Optional[int] = None
    _cmd_prefix = "do_"
    _empty_result = object()

    prompt = "monitor >>> "
    intro = "\nAsyncio Monitor: {tasknum} task{s} running\nType help for available commands\n\n"  # noqa
    help_template = "{cmd_name} {arg_list}\n    {doc}\n"
    help_short_template = (
        "    {cmd_name}{cmd_arg_sep}{arg_list}: {doc_firstline}"  # noqa
    )

    _sout: TextIO
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
        locals: OptLocals = None,
    ) -> None:
        self._monitored_loop = loop or asyncio.get_event_loop()
        self._host = host
        self._port = port
        self._console_port = console_port
        self._console_enabled = console_enabled
        self._locals = locals

        log.info("Starting aiomonitor at %s:%d", host, port)

        self._ui_thread = threading.Thread(target=self._server, args=(), daemon=True)
        self._closed = False
        self._started = False
        self._console_future = None  # type: Optional[Future[Any]]

        self.lastcmd = None  # type: Optional[str]

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

    @property
    def closed(self) -> bool:
        return self._closed

    def __enter__(self) -> "Monitor":
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
            await telnet_server.stop()

    async def _interact(self, connection: TelnetConnection) -> None:
        """Main interactive loop of the monitor"""
        await asyncio.sleep(0.3)  # wait until telnet negotiation is done
        self._sout = connection.stdout
        tasknum = len(all_tasks(loop=self._monitored_loop))
        s = "" if tasknum == 1 else "s"
        self._sout.write(self.intro.format(tasknum=tasknum, s=s))
        prompt_session: PromptSession[str] = PromptSession(self.prompt)
        while True:
            try:
                user_input = (await prompt_session.prompt_async()).strip()
            except (EOFError, KeyboardInterrupt):
                return
            except Exception as e:
                msg = "Could not read from user input due to:\n{}\n"
                log.exception(msg)
                self._sout.write(msg.format(repr(e)))
                self._sout.flush()
            else:
                try:
                    self._command_dispatch(user_input)
                except Exception as e:
                    msg = "Unexpected Exception during command execution:\n{}\n"  # noqa
                    log.exception(msg)
                    self._sout.write(msg.format(repr(e)))
                    self._sout.flush()

    def _command_dispatch(self, user_input: str) -> None:
        if not user_input:
            return self.emptyline()
        assert self._sout is not None

        result = None
        self.lastcmd = user_input
        comm, *args = user_input.split(" ")
        try:
            cmd, args = self.precmd(comm, args)
            result = cmd(*args)
        except UnknownCommandException as e:
            result = self._empty_result
            caught_ex = e  # type: Optional[Exception]
            self.default(comm, *args)
        except MultipleCommandException as e:
            result = self._empty_result
            caught_ex = e
            msg = 'Ambiguous command "{}"'.format(comm)
            self._sout.write(msg + "\n")
        except ArgumentMappingException as e:
            result = self._empty_result
            caught_ex = e
            msg = "An argument to {} could not be converted according to the methods type annotation because of this error:\n{}\n"  # noqa
            self._sout.write(msg.format(e, repr(e.__cause__)))
        except TypeError as e:
            result = self._empty_result
            caught_ex = e
            msg = "Probably incorrect number of arguments to command method:\n{}\n"  # noqa
            traceback.print_exc(file=self._sout)
        except Exception as e:
            result = self._empty_result
            caught_ex = e
        else:
            caught_ex = None
        finally:
            self.postcmd(comm, args, result, caught_ex)

    def _filter_cmds(
        self, *, startswith: str = "", with_alts: bool = True
    ) -> Generator[CmdName, None, None]:
        cmds = (cmd for cmd in dir(self) if cmd.startswith(self._cmd_prefix))
        for name in cmds:
            if name.startswith(self._cmd_prefix + startswith):
                yield CmdName(name[len(self._cmd_prefix) :], name)
            meth = getattr(self, name)
            if with_alts and hasattr(meth, "alt_names"):
                for altname in meth.alt_names:
                    if altname.startswith(startswith):
                        yield CmdName(altname, name)

    def map_args(
        self, cmd: Callable[..., Any], args: Sequence[str]
    ) -> Generator[Any, None, None]:
        params = inspect.signature(cmd).parameters.values()
        ia = iter(args)
        for param in params:
            if param.annotation is param.empty or not callable(param.annotation):

                def type_(x: Any) -> Any:
                    return x

            else:
                type_ = param.annotation
            try:
                if str(param).startswith("*"):
                    for arg in ia:
                        yield type_(arg)
                else:
                    # We iterate over the functions' annotation for its
                    # parameters and also manually over the given arguments
                    # (they can have arbitrarily different lengths).
                    # Here we could be in the situation where a further
                    # parameter exists, but no argument is given to it.
                    # Since we might have a method with optional, non-star
                    # arguments, we must ignore a StopIteration from this call
                    # to next.
                    with suppress(StopIteration):
                        yield type_(next(ia))
            except Exception as e:
                raise ArgumentMappingException(cmd.__name__) from e
        if tuple(ia):
            msg = "Too many arguments for command {}()"
            raise TypeError(msg.format(cmd.__name__))

    def precmd(
        self, comm: str, args: Sequence[str]
    ) -> Tuple[Callable[..., Any], List[str]]:
        cmd = self.getcmd(comm)
        return cmd, list(self.map_args(cmd, args))

    def postcmd(
        self,
        comm: str,
        args: Sequence[str],
        result: Any,
        exception: Optional[Exception] = None,
    ) -> None:
        if exception is not None and not isinstance(
            exception, (CommandException, TypeError)
        ):
            raise exception

    def getcmd(self, comm: str) -> Callable[..., Any]:
        allcmds = sorted(self._filter_cmds(startswith=comm))
        if not allcmds:
            raise UnknownCommandException(comm)
        if len(allcmds) > 1 and allcmds[0].cmd_name != comm:
            raise MultipleCommandException(allcmds)
        return getattr(self, allcmds[0].method_name)  # type: ignore

    def emptyline(self) -> None:
        if self.lastcmd is not None:
            self._command_dispatch(self.lastcmd)

    def default(self, comm: str, *args: str) -> None:
        assert self._sout is not None
        self._sout.write("No such command: {}\n".format(comm))

    @alt_names("? h")
    def do_help(self, *cmd_names: str) -> None:
        """Show help for command name

        Any number of command names may be given to help, and the long help
        text for all of them will be shown.
        """
        assert self._sout is not None

        def _h(cmd: str, template: str) -> None:
            assert self._sout is not None
            try:
                func = getattr(self, cmd)
            except AttributeError:
                self._sout.write("No such command: {}\n".format(cmd))
            else:
                doc = func.__doc__ if func.__doc__ else ""
                doc_firstline = doc.split("\n", maxsplit=1)[0]
                arg_list = " ".join(p for p in inspect.signature(func).parameters)
                self._sout.write(
                    template.format(
                        cmd_name=cmd[len(self._cmd_prefix) :],
                        arg_list=arg_list,
                        cmd_arg_sep=" " if arg_list else "",
                        doc=doc,
                        doc_firstline=doc_firstline,
                    )
                    + "\n"
                )

        if not cmd_names:
            cmds = sorted(c.method_name for c in self._filter_cmds(with_alts=False))
            self._sout.write("Available Commands are:\n\n")
            for cmd in cmds:
                _h(cmd, self.help_short_template)
        else:
            for cmd in cmd_names:
                _h(self._cmd_prefix + cmd, self.help_template)

    @alt_names("p")
    def do_ps(self) -> None:
        """Show task table"""
        headers = (
            "Task ID",
            "State",
            "Name",
            "Coroutine",
            "Created Location",
            "Since",
        )
        table_data: List[Tuple[str, str, str, str, str, str]] = [headers]
        assert self._sout is not None

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
        self._sout.write(f"{len(table_data)} tasks running\n")
        self._sout.write(table.table)
        self._sout.write("\n")
        self._sout.flush()

    @alt_names("w")
    def do_where(self, taskid: int) -> None:
        """Show stack frames and its task creation chain of a task"""
        assert self._sout is not None
        depth = 0
        task = task_by_id(taskid, self._monitored_loop)
        if task is None:
            self._sout.write("No task %d\n" % taskid)
            return
        task_chain: List[asyncio.Task[Any]] = []
        while task is not None:
            task_chain.append(task)
            task = self._created_traceback_chains.get(task)
        prev_task = None
        for task in reversed(task_chain):
            if depth == 0:
                self._sout.write(
                    "Stack of the root task or coroutine scheduled in the event loop (most recent call last):\n\n"
                )
            elif depth > 0:
                assert prev_task is not None
                self._sout.write(
                    "Stack of %s when creating the next task (most recent call last):\n\n"
                    % _format_task(prev_task)
                )
            stack = self._created_tracebacks.get(task)
            if stack is None:
                self._sout.write(
                    "  No stack available (maybe it is a native code or the event loop itself)\n"
                )
            else:
                stack = _filter_stack(stack)
                self._sout.write("".join(traceback.format_list(stack)))
            prev_task = task
            depth += 1
            self._sout.write("\n")
        task = task_chain[0]
        self._sout.write(
            "Stack of %s (most recent call last):\n\n" % _format_task(task)
        )
        stack = _extract_stack_from_task(task)
        if not stack:
            self._sout.write("  No stack available for %s" % _format_task(task))
        else:
            self._sout.write("".join(traceback.format_list(stack)))
        self._sout.write("\n")

    def do_signal(self, signame: str) -> None:
        """Send a Unix signal"""
        assert self._sout is not None
        if hasattr(signal, signame):
            os.kill(os.getpid(), getattr(signal, signame))
        else:
            self._sout.write("Unknown signal %s\n" % signame)

    @alt_names("st")
    def do_stacktrace(self) -> None:
        """Print a stack trace from the event loop thread"""
        assert self._sout is not None
        tid = self._event_loop_thread_id
        assert tid is not None
        frame = sys._current_frames()[tid]
        traceback.print_stack(frame, file=self._sout)

    def do_cancel(self, taskid: int) -> None:
        """Cancel an indicated task"""
        assert self._sout is not None
        task = task_by_id(taskid, self._monitored_loop)
        if task:
            fut = asyncio.run_coroutine_threadsafe(
                cancel_task(task), loop=self._monitored_loop
            )
            fut.result(timeout=3)
            self._sout.write("Cancel task %d\n" % taskid)
        else:
            self._sout.write("No task %d\n" % taskid)

    @alt_names("quit q")
    def do_exit(self) -> None:
        """Leave the monitor"""
        assert self._sout is not None
        self._sout.write("Leaving monitor. Hit Ctrl-C to exit\n")
        self._sout.flush()

    def do_console(self) -> None:
        """Switch to async Python REPL"""
        assert self._sin is not None
        assert self._sout is not None
        if not self._console_enabled:
            self._sout.write("Python console disabled for this sessiong\n")
            self._sout.flush()
            return

        h, p = self._host, self._console_port
        log.info("Starting console at %s:%d", h, p)
        fut = init_console_server(
            self._host, self._console_port, self._locals, self._monitored_loop
        )
        server = fut.result(timeout=3)
        try:
            console_proxy(self._sin, self._sout, self._host, self._console_port)
        finally:
            coro = close_server(server)
            close_fut = asyncio.run_coroutine_threadsafe(
                coro, loop=self._monitored_loop
            )
            close_fut.result(timeout=15)


def start_monitor(
    loop: Loop,
    *,
    monitor: Type[Monitor] = Monitor,
    host: str = MONITOR_HOST,
    port: int = MONITOR_PORT,
    console_port: int = CONSOLE_PORT,
    console_enabled: bool = True,
    hook_task_factory: bool = False,
    locals: OptLocals = None,
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
