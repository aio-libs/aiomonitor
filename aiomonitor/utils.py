import asyncio
import linecache
import traceback

from contextlib import suppress


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
    with suppress(asyncio.CancelledError):
        task.cancel()
        await task
