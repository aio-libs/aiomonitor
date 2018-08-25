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
                    List, Type, TypeVar, NamedTuple, get_type_hints, cast)  # noqa
from concurrent.futures import Future  # noqa

from terminaltables import AsciiTable

from .utils import (_format_stack, cancel_task, task_by_id, console_proxy,
                    init_console_server, alt_names)
from .mypy_types import Loop, OptLocals


__all__ = ('Monitor', 'start_monitor')
log = logging.getLogger(__name__)


MONITOR_HOST = '127.0.0.1'
MONITOR_PORT = 50101
CONSOLE_PORT = 50102


class CommandException(Exception):
    pass


class UnknownCommandException(CommandException):
    pass


class MultipleCommandException(CommandException):
    def __init__(self, cmds: List['CmdName']) -> None:
        self.cmds = cmds
        super().__init__()


class CmdName(NamedTuple):
    cmd_name: str
    method_name: str


class Monitor:
    _event_loop_thread_id = None  # type: int
    _cmd_prefix = 'do_'

    prompt = 'monitor >>> '
    help_template = '{cmd_name} {arg_list}\n    {doc}\n'
    help_short_template = '    {cmd_name}{cmd_arg_sep}{arg_list}: {doc_firstline}'  # noqa

    def __init__(self,
                 loop: asyncio.AbstractEventLoop, *,
                 host: str=MONITOR_HOST,
                 port: int=MONITOR_PORT,
                 console_port: int=CONSOLE_PORT,
                 console_enabled: bool=True,
                 locals: OptLocals=None) -> None:
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

    def __init_subclass__(cls, **kwargs: Any) -> None:
        # test command names
        pass

    def __repr__(self) -> str:
        name = self.__class__.__name__
        return '<{name}: {host}:{port}>'.format(
            name=name, host=self._host, port=self._port)

    def start(self) -> None:
        assert not self._closed
        assert not self._started

        self._started = True
        h, p = self._host, self._console_port
        self._event_loop_thread_id = threading.get_ident()
        self._ui_thread.start()
        if self._console_enabled:
            log.info('Starting console at %s:%d', h, p)
            self._console_future = init_console_server(
                self._host, self._console_port, self._locals, self._loop)

    @property
    def closed(self) -> bool:
        return self._closed

    def __enter__(self) -> 'Monitor':
        if not self._started:
            self.start()
        return self

    def __exit__(self, exc_type: Optional[Type[BaseException]],
                 exc_value: Optional[BaseException],
                 traceback: Optional[TracebackType]) -> None:
        self.close()

    def close(self) -> None:
        if not self._closed:
            self._closing.set()
            self._ui_thread.join()
            if self._console_future is not None:
                self._console_future.result(timeout=15)
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

    def _filter_cmds(self, *,
                     startswith: str='',
                     with_alts: bool=True) -> Generator[CmdName, None, None]:
        cmds = (cmd for cmd in dir(self) if cmd.startswith(self._cmd_prefix))
        for name in cmds:
            if name.startswith(self._cmd_prefix + startswith):
                yield CmdName(name[len(self._cmd_prefix):], name)
            meth = getattr(self, name)
            if with_alts and hasattr(meth, 'alt_names'):
                for altname in meth.alt_names:
                    if altname.startswith(startswith):
                        yield CmdName(altname, name)

    def _command_dispatch(self,
                          sin: IO[str],
                          sout: IO[str],
                          user_input: str) -> None:
        comm, *args = user_input.split(' ')
        cmd = self._getcmd(comm)
        try:
            cmd(sin, sout, *args)
        except Exception as e:
            msg = 'Exception occured during command "{}": {}'
            msg = msg.format(user_input, repr(e))
            sout.write(msg + '\n')
            log.exception(msg)

    def _getcmd(self, comm: str) -> Callable:
        allcmds = sorted(self._filter_cmds(startswith=comm))
        if not allcmds:
            raise UnknownCommandException()
        if len(allcmds) > 1 and allcmds[0].cmd_name != comm:
            raise MultipleCommandException(allcmds)
        return getattr(self, allcmds[0].method_name)  # type: ignore

    def _interactive_loop(self, sin: IO[str], sout: IO[str]) -> None:
        """Main interactive loop of the monitor
        """
        (sout.write('\nAsyncio Monitor: %d tasks running\n' %
                    len(asyncio.Task.all_tasks(loop=self._loop))))
        sout.write('Type help for commands\n')
        while not self._closing.is_set():
            sout.write(self.prompt)
            sout.flush()
            try:
                user_input = sin.readline().strip()
            except Exception:
                msg = 'Could not read from user input'
                sout.write(msg + '\n')
                log.exception(msg)
            else:
                try:
                    self._command_dispatch(sin, sout, user_input)
                except MultipleCommandException as e:
                    cmds = ', '.join(i.cmd_name for i in e.cmds)
                    sout.write('Multiple possible commands: {}\n'.format(cmds))
                except UnknownCommandException:
                    sout.write('Unknown command: {}\n'.format(user_input))

    @alt_names('? h')
    def do_help(self, sin: IO[str], sout: IO[str], *args: str) -> None:
        def _h(cmd: str, template: str) -> None:
            func = getattr(self, cmd)
            doc = func.__doc__ if func.__doc__ else ''
            doc_firstline = doc.split('\n', maxsplit=1)[0]
            arg_list = ' '.join(
                        p for p in inspect.signature(func).parameters
                        if p not in ('sin', 'sout')
                      )
            sout.write(
                template.format(
                    cmd_name=cmd[3:],
                    arg_list=arg_list,
                    cmd_arg_sep=' ' if arg_list else '',
                    doc=doc,
                    doc_firstline=doc_firstline
                ) + '\n'
            )

        if not args:
            cmds = sorted(
                    c.method_name for c in self._filter_cmds(with_alts=False)
            )
            sout.write('Available Commands are:\n\n')
            for cmd in cmds:
                _h(cmd, self.help_short_template)
        else:
            for cmd in args:
                _h(self._cmd_prefix + cmd, self.help_template)

    @alt_names('p')
    def do_ps(self, sin: IO[str], sout: IO[str]) -> None:
        """Show task table"""
        headers = ('Task ID', 'State', 'Task')
        table_data = [headers]
        for task in sorted(asyncio.Task.all_tasks(loop=self._loop), key=id):
            taskid = str(id(task))
            if task:
                t = '\n'.join(wrap(str(task), 80))
                table_data.append((taskid, task._state, t))
        table = AsciiTable(table_data)
        sout.write(table.table)
        sout.write('\n')
        sout.flush()

    @alt_names('w')
    def do_where(self, sin: IO[str], sout: IO[str], taskid: int) -> None:
        """Show stack frames for a task"""
        taskid = int(taskid)
        task = task_by_id(taskid, self._loop)
        if task:
            sout.write(_format_stack(task))
            sout.write('\n')
        else:
            sout.write('No task %d\n' % taskid)

    def do_signal(self, sin: IO[str], sout: IO[str], signame: str) -> None:
        """Send a Unix signal"""
        if hasattr(signal, signame):
            os.kill(os.getpid(), getattr(signal, signame))
        else:
            sout.write('Unknown signal %s\n' % signame)

    def do_stacktrace(self, sin: IO[str], sout: IO[str]) -> None:
        """Print a stack trace from the event loop thread"""
        frame = sys._current_frames()[self._event_loop_thread_id]
        traceback.print_stack(frame, file=sout)

    def do_cancel(self, sin: IO[str], sout: IO[str], taskid: int) -> None:
        """Cancel an indicated task"""
        taskid = int(taskid)
        task = task_by_id(taskid, self._loop)
        if task:
            fut = asyncio.run_coroutine_threadsafe(
                cancel_task(task), loop=self._loop)
            fut.result(timeout=3)
            sout.write('Cancel task %d\n' % taskid)
        else:
            sout.write('No task %d\n' % taskid)

    @alt_names('quit q')
    def do_exit(self, sin: IO[str], sout: IO[str]) -> None:
        """Leave the monitor"""
        sout.write('Leaving monitor. Hit Ctrl-C to exit\n')
        sout.flush()

    def do_console(self, sin: IO[str], sout: IO[str]) -> None:
        """Switch to async Python REPL"""
        if not self._console_enabled:
            sout.write('Python console disabled for this sessiong\n')
            sout.flush()

        if self._console_future is not None:
            self._console_future.result()
        console_proxy(sin, sout, self._host, self._console_port)


def start_monitor(loop: Loop, *,
                  monitor: Type[Monitor]=Monitor,
                  host: str=MONITOR_HOST,
                  port: int=MONITOR_PORT,
                  console_port: int=CONSOLE_PORT,
                  console_enabled: bool=True,
                  locals: OptLocals=None) -> Monitor:

    m = monitor(loop, host=host, port=port, console_port=console_port,
                console_enabled=console_enabled, locals=locals)
    m.start()

    return m
