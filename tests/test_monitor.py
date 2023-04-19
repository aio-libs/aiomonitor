import asyncio
import contextvars
import sys
import telnetlib
import threading
import time

import pytest

from aiomonitor import Monitor, start_monitor
from aiomonitor.monitor import MONITOR_HOST, MONITOR_PORT
from aiomonitor.utils import all_tasks


def monitor_common(loop, monitor_cls):
    def make_baz():
        return "baz"

    locals_ = {"foo": "bar", "make_baz": make_baz}
    mon = monitor_cls(loop, locals=locals_)
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
def monitor(request, loop):
    class MonitorSubclass(Monitor):
        def do_something(self, arg):
            self._sout.write("doing something with " + arg)
            self._sout.flush()

    yield from monitor_common(loop, MonitorSubclass)


@pytest.yield_fixture
def tn_client(monitor):
    tn = telnetlib.Telnet()
    for _ in range(10):
        try:
            tn.open(MONITOR_HOST, MONITOR_PORT, timeout=5)
            break
        except OSError as e:
            print("Retrying after error: {}".format(str(e)))
        time.sleep(1)
    else:
        pytest.fail("Can not connect to the telnet server")
    tn.read_until(b"monitor >>>", 10)
    yield tn
    tn.close()


@pytest.fixture(params=[True, False], ids=["console:True", "console:False"])
def console_enabled(request):
    return request.param


def test_ctor(loop, unused_port, console_enabled):

    with Monitor(loop, console_enabled=console_enabled):
        loop.run_until_complete(asyncio.sleep(0.01, loop=loop))

    with start_monitor(loop, console_enabled=console_enabled) as m:
        loop.run_until_complete(asyncio.sleep(0.01, loop=loop))
    assert m.closed

    m = Monitor(loop, console_enabled=console_enabled)
    m.start()
    try:
        loop.run_until_complete(asyncio.sleep(0.01, loop=loop))
    finally:
        m.close()
        m.close()  # make sure call is idempotent
    assert m.closed

    m = Monitor(loop, console_enabled=console_enabled)
    m.start()
    with m:
        loop.run_until_complete(asyncio.sleep(0.01, loop=loop))
    assert m.closed

    # make sure that monitor inside async func can exit correctly
    async def f():
        with Monitor(loop, console_enabled=console_enabled):
            await asyncio.sleep(0.01, loop=loop)

    loop.run_until_complete(f())


def execute(tn, command, pattern=b">>>"):
    tn.write(command.encode("utf-8"))
    data = tn.read_until(pattern, 100)
    return data.decode("utf-8")


def get_task_ids(loop):
    return [id(t) for t in all_tasks(loop=loop)]


def test_basic_monitor(monitor, tn_client, loop):
    tn = tn_client
    resp = execute(tn, "help\n")
    assert "Commands" in resp

    resp = execute(tn, "xxx\n")
    assert "No such command" in resp

    resp = execute(tn, "ps\n")
    assert "Task" in resp

    resp = execute(tn, "ps 123\n")
    assert "TypeError" in resp

    resp = execute(tn, "signal name\n")
    assert "Unknown signal name" in resp

    resp = execute(tn, "stacktrace\n")
    assert "loop.run_forever()" in resp

    resp = execute(tn, "w 123\n")
    assert "No task 123" in resp

    resp = execute(tn, "where 123\n")
    assert "No task 123" in resp

    resp = execute(tn, "c 123\n")
    assert "Ambiguous command" in resp

    resp = execute(tn, "cancel 123\n")
    assert "No task 123" in resp

    resp = execute(tn, "ca 123\n")
    assert "No task 123" in resp


myvar = contextvars.ContextVar("myvar", default=42)


def test_monitor_task_factory():
    async def do():
        await asyncio.sleep(0)
        myself = asyncio.current_task()
        assert myself is not None
        assert myself.get_name() == "mytask"

    async def main():
        loop = asyncio.get_running_loop()
        with Monitor(loop, console_enabled=False, hook_task_factory=True):
            t = asyncio.create_task(do(), name="mytask")
            await t

    asyncio.run(main())


@pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="The context argument of asyncio.create_task() is added in Python 3.11",
)
def test_monitor_task_factory_with_context():
    ctx = contextvars.Context()
    # This context is bound at the outermost scope,
    # and inside it the initial value of myvar is kept intact.

    async def do():
        await asyncio.sleep(0)
        assert myvar.get() == 42  # we are referring the outer context
        myself = asyncio.current_task()
        assert myself is not None
        assert myself.get_name() == "mytask"

    async def main():
        myvar.set(99)  # override in the current task's context
        loop = asyncio.get_running_loop()
        with Monitor(loop, console_enabled=False, hook_task_factory=True):
            t = asyncio.create_task(do(), name="mytask", context=ctx)
            await t
        assert myvar.get() == 99

    asyncio.run(main())


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
        resp = execute(tn, "where {}\n".format(t_id))
        assert "Task" in resp
        resp = execute(tn, "cancel {}\n".format(t_id))
        assert "Cancel task" in resp
    fut.cancel()


def test_monitor_with_console(monitor, tn_client):
    tn = tn_client
    resp = execute(tn, "console\n")
    assert "This console is running in an asyncio event loop" in resp
    execute(tn, "await asyncio.sleep(0, loop=loop)\n")

    resp = execute(tn, "foo\n")
    assert " 'bar'\n>>>" == resp
    resp = execute(tn, "make_baz()\n")
    assert " 'baz'\n>>>" == resp

    execute(tn, "exit()\n")

    resp = execute(tn, "help\n")
    assert "Commands" in resp


def test_custom_monitor_class(monitor, tn_client):
    tn = tn_client
    resp = execute(tn, "something someargument\n")
    assert "doing something with someargument" in resp
