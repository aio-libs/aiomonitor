import asyncio
import contextlib
import linecache
import selectors
import telnetlib
import traceback

import aioconsole


def _get_stack(task):
    frames = []
    coro = task._coro
    while coro:
        if hasattr(coro, 'cr_frame') or hasattr(coro, 'gi_frame'):
            f = coro.cr_frame if hasattr(coro, 'cr_frame') else coro.gi_frame
        else:
            f = None

        if f is not None:
            frames.append(f)

        if hasattr(coro, 'cr_await') or hasattr(coro, 'gi_yieldfrom'):
            coro = (coro.cr_await if hasattr(coro, 'cr_await')
                    else coro.gi_yieldfrom)
        else:
            coro = None
    return frames


def _format_stack(task):
    extracted_list = []
    checked = set()
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
        resp += ''.join(traceback.format_list(extracted_list))
    return resp


def task_by_id(taskid, loop):
    tasks = asyncio.Task.all_tasks(loop=loop)
    return next(filter(lambda t: id(t) == taskid, tasks), None)


async def cancel_task(task):
    with contextlib.suppress(asyncio.CancelledError):
        task.cancel()
        await task


def init_console_server(host, port, loop):
    coro = aioconsole.start_interactive_server(host=host, port=port, loop=loop)
    console_future = asyncio.run_coroutine_threadsafe(coro, loop=loop)
    return console_future


if hasattr(selectors, 'PollSelector'):
    _TelnetSelector = selectors.PollSelector
else:
    _TelnetSelector = selectors.SelectSelector


def console_proxy(sin, sout, host, port):
    tn = telnetlib.Telnet()
    with contextlib.closing(tn):
        tn.open(host, port, timeout=10)
        with _TelnetSelector() as selector:
            selector.register(tn, selectors.EVENT_READ)
            selector.register(sin, selectors.EVENT_READ)

            while True:
                for key, events in selector.select():
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
