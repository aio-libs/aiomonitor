import asyncio
import logging
import os
import signal
import socket
import threading

from asyncio.coroutines import _format_coroutine

import aioconsole

from .utils import _format_stack, cancel_task, task_by_id

__all__ = ('Monitor',)


log = logging.getLogger(__name__)

MONITOR_HOST = '127.0.0.1'
MONITOR_PORT = 50123
CONSOLE_PORT = 50124


class Monitor:
    def __init__(self, *, loop=None, host=MONITOR_HOST, port=MONITOR_PORT):
        self.loop = loop or asyncio.get_event_loop()
        self.address = (host, port)

        log.info('Starting aiomonitor at %s:%d', host, port)

        # The monitor launches both a separate thread and helper task
        # that runs inside curio itself to manage cancellation events
        self._ui_thread = threading.Thread(
            target=self.server, args=(), daemon=True)
        self._closing = threading.Event()
        self._ui_thread.start()

    def __enter__(self):
        coro = aioconsole.start_interactive_server(
            host=MONITOR_HOST, port=CONSOLE_PORT)
        asyncio.run_coroutine_threadsafe(coro, loop=self.loop)
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    def close(self):
        self._closing.set()
        self._ui_thread.join()

    def server(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass

        # set the timeout to prevent the server loop from
        # blocking indefinitaly on sock.accept()
        sock.settimeout(0.5)
        sock.bind(self.address)
        sock.listen(1)
        with sock:
            while not self._closing.is_set():
                try:
                    client, addr = sock.accept()
                    with client:
                        sout = client.makefile('w', encoding='utf-8')
                        sin = client.makefile('r', encoding='utf-8')
                        self.interactive_loop(sout, sin)
                except socket.timeout:
                    continue

    def interactive_loop(self, sout, sin):
        '''
        Main interactive loop of the monitor
        '''
        (sout.write('\nAsyncio Monitor: %d tasks running\n' %
                    len(asyncio.Task.all_tasks(loop=self.loop))))
        sout.write('Type help for commands\n')
        while not self._closing.is_set():
            sout.write('aiomonitor > ')
            sout.flush()
            resp = sin.readline()
            try:
                if not resp or resp.startswith('q'):
                    self.command_exit(sout)
                    return

                elif resp.startswith('p'):
                    self.command_ps(sout)

                elif resp.startswith('exit'):
                    self.command_exit(sout)
                    return

                elif resp.startswith('cancel'):
                    _, taskid_s = resp.split()
                    self.command_cancel(sout, int(taskid_s))

                elif resp.startswith('signal'):
                    _, signame = resp.split()
                    self.command_signal(sout, signame)

                elif resp.startswith('w'):
                    _, taskid_s = resp.split()
                    self.command_where(sout, int(taskid_s))

                elif resp.startswith('h'):
                    self.command_help(sout)
                else:
                    sout.write('Unknown command. Type help.\n')
            except Exception as e:
                sout.write('Bad command. %s\n' % e)

    def command_help(self, sout):
        sout.write(
         '''Commands:
             ps               : Show task table
             where taskid     : Show stack frames for a task
             cancel taskid    : Cancel an indicated task
             signal signame   : Send a Unix signal
             quit             : Leave the monitor
            ''')

    def command_ps(self, sout):
        headers = ('Task', 'State', 'Cycles', 'Timeout', 'Task')
        widths = (12, 12, 10, 7, 50)
        for h, w in zip(headers, widths):
            sout.write('%-*s ' % (w, h))
        sout.write('\n')
        sout.write(' '.join(w * '-' for w in widths))
        sout.write('\n')
        # timestamp = time.monotonic()
        for task in sorted(asyncio.Task.all_tasks(loop=self.loop), key=id):
            taskid = id(task)
            if task:
                # remaining = format((task.timeout - timestamp), '0.6f')[:7]
                # if task.timeout else 'None'
                remaining = None
                sout.write('%-*d %-*s %-*d %-*s %-*s\n' % (
                    widths[0], taskid,
                    widths[1], task._state,
                    widths[2], 0,
                    widths[3], remaining,
                    widths[4], task))

    def command_where(self, sout, taskid):
        task = task_by_id(taskid, self.loop)
        if task:
            sout.write(_format_stack(task))
            sout.write('\n')
        else:
            sout.write('No task %d\n' % taskid)

    def command_signal(self, sout, signame):
        if hasattr(signal, signame):
            os.kill(os.getpid(), getattr(signal, signame))
        else:
            sout.write('Unknown signal %s\n' % signame)

    def command_cancel(self, sout, taskid):

        task = task_by_id(taskid, self.loop)
        if task:
            sout.write('Cancelling task %d\n' % taskid)
            fut = asyncio.run_coroutine_threadsafe(
                cancel_task(task), loop=self.loop)
            fut.result()

    def command_exit(self, sout):
        sout.write('Leaving monitor. Hit Ctrl-C to exit\n')
        sout.flush()
