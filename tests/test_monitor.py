import asyncio
import pytest
import telnetlib
import threading
import time

from aiomonitor import Monitor
from aiomonitor.aiomonitor import MONITOR_HOST, MONITOR_PORT


@pytest.yield_fixture
def monitor(loop):
    mon = Monitor(loop)
    ev = threading.Event()

    def f(mon, loop, ev):
        asyncio.set_event_loop(loop)
        with mon:
            ev.set()
            loop.run_forever()

    thread = threading.Thread(target=f, args=(mon, loop, ev))
    thread.start()
    ev.wait()
    yield mon
    loop.call_soon_threadsafe(loop.stop)
    thread.join()


@pytest.yield_fixture
def tn_client(monitor):
    tn = telnetlib.Telnet()
    tn.open(MONITOR_HOST, MONITOR_PORT, timeout=5)
    tn.read_until(b'monitor >>>', 10)
    yield tn
    tn.close()


def test_ctor(loop, unused_port):

    with Monitor(loop):
        loop.run_until_complete(asyncio.sleep(1, loop=loop))


def execute(tn, command, pattern=b'>>>'):
    tn.write(command.encode('utf-8'))
    data = tn.read_until(pattern, 100)
    return data.decode('utf-8')


def get_task_ids(loop):
    return [id(t) for t in asyncio.Task.all_tasks(loop=loop)]


def test_basic_monitor(monitor, tn_client, loop):
    tn = tn_client
    resp = execute(tn, 'help\n')
    assert 'Commands' in resp

    resp = execute(tn, 'xxx\n')
    assert 'Unknown command' in resp

    resp = execute(tn, 'ps\n')
    assert 'Task' in resp

    resp = execute(tn, 'signal name\n')
    assert 'Unknown signal name' in resp

    resp = execute(tn, 'wehere 123\n')
    assert 'No task 123' in resp

    resp = execute(tn, 'cancel 123\n')
    assert 'No task 123' in resp


def test_cancel_where_tasks(monitor, tn_client, loop):
    tn = tn_client

    async def sleeper(loop):
        await asyncio.sleep(100, loop=loop)  # xxx

    fut = asyncio.run_coroutine_threadsafe(sleeper(loop), loop=loop)
    # TODO: we should not rely on timeout
    time.sleep(0.1)

    task_ids = get_task_ids(loop)
    assert len(task_ids) > 0
    for t_id in task_ids:
        resp = execute(tn, 'where {}\n'.format(t_id))
        assert 'Task' in resp
        resp = execute(tn, 'cancel {}\n'.format(t_id))
        assert 'Cancel task' in resp
    fut.cancel()


def test_monitor_with_console(monitor, tn_client):
    tn = tn_client
    # TODO: fix this, we need proper way to wait for console to start
    monitor._console_future.result()
    resp = execute(tn, 'console\n')
    assert 'This console is running in an asyncio event loop' in resp
    execute(tn, 'await asyncio.sleep(0, loop=loop)\n')
    execute(tn, 'exit()\n')

    resp = execute(tn, 'help\n')
    assert 'Commands' in resp
