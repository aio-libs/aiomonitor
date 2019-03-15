import asyncio
import inspect
import logging
import os
import signal
import socket
import sys
import threading
import traceback
from textwrap import wrap
from types import TracebackType
from typing import (IO, Dict, Any, Callable, Optional, Tuple, Generator,  # noqa
                    List, Type, TypeVar, NamedTuple, get_type_hints,  # noqa
                    cast, Sequence)  # noqa
from contextlib import suppress
from concurrent.futures import Future  # noqa

from terminaltables import AsciiTable

from .utils import (_format_stack, cancel_task, task_by_id, console_proxy,
                    init_console_server, close_server, alt_names, all_tasks)
from .mypy_types import Loop, OptLocals


__all__ = ('Monitor', 'start_monitor')
log = logging.getLogger(__name__)


MONITOR_HOST = '127.0.0.1'
MONITOR_PORT = 50101
CONSOLE_PORT = 50102


Server = asyncio.AbstractServer  # noqa


class CommandException(Exception):
    pass


class UnknownCommandException(CommandException):
    pass


class MultipleCommandException(CommandException):
    def __init__(self, cmds: List['CmdName']) -> None:
        self.cmds = cmds
        super().__init__()


class ArgumentMappingException(CommandException):
    pass


CmdName = NamedTuple('CmdName', [('cmd_name', str), ('method_name', str)])


class Monitor:
    _event_loop_thread_id = None  # type: int
    _cmd_prefix = 'do_'
    _empty_result = object()

    prompt = 'monitor >>> '
    intro = '\nAsyncio Monitor: {tasknum} task{s} running\nType help for available commands\n\n'  # noqa
    help_template = '{cmd_name} {arg_list}\n    {doc}\n'
    help_short_template = '    {cmd_name}{cmd_arg_sep}{arg_list}: {doc_firstline}'  # noqa

    _sin = None  # type: IO[str]
    _sout = None  # type: IO[str]

    def __init__(self,
                 loop: asyncio.AbstractEventLoop, *,
                 host: str = MONITOR_HOST,
                 port: int = MONITOR_PORT,
                 console_port: int = CONSOLE_PORT,
                 console_enabled: bool = True,
                 locals: OptLocals = None) -> None:
        self._loop = loop or asyncio.get_event_loop()
        self._host = host
        self._port = port
        self._console_port = console_port
        self._console_enabled = console_enabled
        self._locals = locals

        log.info('Starting aiomonitor at %s:%d', host, port)

        self._ui_thread = threading.Thread(target=self._server, args=(),
                                           daemon=True)
        self._closing = threading.Event()
        self._closed = False
        self._started = False
        self._console_future = None  # type: Optional[Future[Any]]

        self.lastcmd = None  # type: Optional[str]

    def __repr__(self) -> str:
        name = self.__class__.__name__
        return '<{name}: {host}:{port}>'.format(
            name=name, host=self._host, port=self._port)

    def start(self) -> None:
        assert not self._closed
        assert not self._started

        self._started = True
        self._event_loop_thread_id = threading.get_ident()
        self._ui_thread.start()

    @property
    def closed(self) -> bool:
        return self._closed

    def __enter__(self) -> 'Monitor':
        if not self._started:
            self.start()
        return self

    # exc_type should be Optional[Type[BaseException]], but
    # this runs into https://github.com/python/typing/issues/266
    # on Python 3.5.
    def __exit__(self, exc_type: Any,
                 exc_value: Optional[BaseException],
                 traceback: Optional[TracebackType]) -> None:
        self.close()

    def close(self) -> None:
        if not self._closed:
            self._closing.set()
            self._ui_thread.join()
            self._closed = True

    def _server(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass

        # set the timeout to prevent the server loop from
        # blocking indefinitaly on sock.accept()
        sock.settimeout(0.5)
        sock.bind((self._host, self._port))
        sock.listen(1)
        with sock:
            while not self._closing.is_set():
                try:
                    client, addr = sock.accept()
                    with client:
                        sout = client.makefile('w', encoding='utf-8')
                        sin = client.makefile('r', encoding='utf-8')
                        self._interactive_loop(sin, sout)
                except (socket.timeout, OSError):
                    continue

    def _interactive_loop(self, sin: IO[str], sout: IO[str]) -> None:
        """Main interactive loop of the monitor"""
        self._sin = sin
        self._sout = sout
        tasknum = len(all_tasks(loop=self._loop))
        s = '' if tasknum == 1 else 's'
        self._sout.write(self.intro.format(tasknum=tasknum, s=s))
        try:
            while not self._closing.is_set():
                self._sout.write(self.prompt)
                self._sout.flush()
                try:
                    user_input = sin.readline().strip()
                except Exception as e:
                    msg = 'Could not read from user input due to:\n{}\n'
                    log.exception(msg)
                    self._sout.write(msg.format(repr(e)))
                    self._sout.flush()
                else:
                    try:
                        self._command_dispatch(user_input)
                    except Exception as e:
                        msg = 'Unexpected Exception during command execution:\n{}\n'  # noqa
                        log.exception(msg)
                        self._sout.write(msg.format(repr(e)))
                        self._sout.flush()
        finally:
            self._sin = None  # type: ignore
            self._sout = None  # type: ignore

    def _command_dispatch(self, user_input: str) -> None:
        if not user_input:
            return self.emptyline()

        self.lastcmd = user_input
        comm, *args = user_input.split(' ')
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
            self._sout.write(msg + '\n')
        except ArgumentMappingException as e:
            result = self._empty_result
            caught_ex = e
            msg = 'An argument to {} could not be converted according to the methods type annotation because of this error:\n{}\n'  # noqa
            self._sout.write(msg.format(e, repr(e.__cause__)))
        except TypeError as e:
            result = self._empty_result
            caught_ex = e
            msg = 'Probably incorrect number of arguments to command method:\n{}\n'  # noqa
            self._sout.write(msg.format(repr(e)))
        except Exception as e:
            result = self._empty_result
            caught_ex = e
        else:
            caught_ex = None
        finally:
            self.postcmd(comm, args, result, caught_ex)

    def _filter_cmds(self, *,
                     startswith: str = '',
                     with_alts: bool = True) -> Generator[CmdName, None, None]:
        cmds = (cmd for cmd in dir(self) if cmd.startswith(self._cmd_prefix))
        for name in cmds:
            if name.startswith(self._cmd_prefix + startswith):
                yield CmdName(name[len(self._cmd_prefix):], name)
            meth = getattr(self, name)
            if with_alts and hasattr(meth, 'alt_names'):
                for altname in meth.alt_names:
                    if altname.startswith(startswith):
                        yield CmdName(altname, name)

    def map_args(self, cmd: Callable[..., Any], args: Sequence[str]
                 ) -> Generator[Any, None, None]:
        params = inspect.signature(cmd).parameters.values()
        ia = iter(args)
        for param in params:
            if (param.annotation is param.empty or
                    not callable(param.annotation)):

                def type_(x: Any) -> Any:
                    return x

            else:
                type_ = param.annotation
            try:
                if str(param).startswith('*'):
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
            msg = 'Too many arguments for command {}()'
            raise TypeError(msg.format(cmd.__name__))

    def precmd(self, comm: str, args: Sequence[str]
               ) -> Tuple[Callable[..., Any], List[str]]:
        cmd = self.getcmd(comm)
        return cmd, list(self.map_args(cmd, args))

    def postcmd(self,
                comm: str,
                args: Sequence[str],
                result: Any,
                exception: Optional[Exception] = None) -> None:
        if (exception is not None
                and not isinstance(exception, (CommandException, TypeError))):
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
        self._sout.write('No such command: {}\n'.format(comm))

    @alt_names('? h')
    def do_help(self, *cmd_names: str) -> None:
        """Show help for command name

        Any number of command names may be given to help, and the long help
        text for all of them will be shown.
        """
        def _h(cmd: str, template: str) -> None:
            try:
                func = getattr(self, cmd)
            except AttributeError:
                self._sout.write('No such command: {}\n'.format(cmd))
            else:
                doc = func.__doc__ if func.__doc__ else ''
                doc_firstline = doc.split('\n', maxsplit=1)[0]
                arg_list = ' '.join(
                    p for p in inspect.signature(func).parameters)
                self._sout.write(
                    template.format(
                        cmd_name=cmd[len(self._cmd_prefix):],
                        arg_list=arg_list,
                        cmd_arg_sep=' ' if arg_list else '',
                        doc=doc,
                        doc_firstline=doc_firstline
                    ) + '\n'
                )

        if not cmd_names:
            cmds = sorted(
                c.method_name for c in self._filter_cmds(with_alts=False)
            )
            self._sout.write('Available Commands are:\n\n')
            for cmd in cmds:
                _h(cmd, self.help_short_template)
        else:
            for cmd in cmd_names:
                _h(self._cmd_prefix + cmd, self.help_template)

    @alt_names('p')
    def do_ps(self) -> None:
        """Show task table"""
        headers = ('Task ID', 'State', 'Task')
        table_data = [headers]
        for task in sorted(all_tasks(loop=self._loop), key=id):
            taskid = str(id(task))
            if task:
                t = '\n'.join(wrap(str(task), 80))
                table_data.append((taskid, task._state, t))
        table = AsciiTable(table_data)
        self._sout.write(table.table)
        self._sout.write('\n')
        self._sout.flush()

    @alt_names('w')
    def do_where(self, taskid: int) -> None:
        """Show stack frames for a task"""
        task = task_by_id(taskid, self._loop)
        if task:
            self._sout.write(_format_stack(task))
            self._sout.write('\n')
        else:
            self._sout.write('No task %d\n' % taskid)

    def do_signal(self, signame: str) -> None:
        """Send a Unix signal"""
        if hasattr(signal, signame):
            os.kill(os.getpid(), getattr(signal, signame))
        else:
            self._sout.write('Unknown signal %s\n' % signame)

    @alt_names('st')
    def do_stacktrace(self) -> None:
        """Print a stack trace from the event loop thread"""
        frame = sys._current_frames()[self._event_loop_thread_id]
        traceback.print_stack(frame, file=self._sout)

    def do_cancel(self, taskid: int) -> None:
        """Cancel an indicated task"""
        task = task_by_id(taskid, self._loop)
        if task:
            fut = asyncio.run_coroutine_threadsafe(
                cancel_task(task), loop=self._loop)
            fut.result(timeout=3)
            self._sout.write('Cancel task %d\n' % taskid)
        else:
            self._sout.write('No task %d\n' % taskid)

    @alt_names('quit q')
    def do_exit(self) -> None:
        """Leave the monitor"""
        self._sout.write('Leaving monitor. Hit Ctrl-C to exit\n')
        self._sout.flush()

    def do_console(self) -> None:
        """Switch to async Python REPL"""
        if not self._console_enabled:
            self._sout.write('Python console disabled for this sessiong\n')
            self._sout.flush()
            return

        h, p = self._host, self._console_port
        log.info('Starting console at %s:%d', h, p)
        fut = init_console_server(
            self._host, self._console_port, self._locals, self._loop)
        server = fut.result(timeout=3)
        try:
            console_proxy(
                self._sin, self._sout, self._host, self._console_port)
        finally:
            coro = close_server(server)
            close_fut = asyncio.run_coroutine_threadsafe(coro, loop=self._loop)
            close_fut.result(timeout=15)


def start_monitor(loop: Loop, *,
                  monitor: Type[Monitor] = Monitor,
                  host: str = MONITOR_HOST,
                  port: int = MONITOR_PORT,
                  console_port: int = CONSOLE_PORT,
                  console_enabled: bool = True,
                  locals: OptLocals = None) -> Monitor:

    m = monitor(loop, host=host, port=port, console_port=console_port,
                console_enabled=console_enabled, locals=locals)
    m.start()

    return m
