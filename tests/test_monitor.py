import asyncio
import contextlib
import contextvars
import io
import os
import sys

import pytest

from aiomonitor import Monitor, start_monitor
from aiomonitor.cli import TelnetClient
from aiomonitor.monitor import MONITOR_HOST, MONITOR_PORT
from aiomonitor.utils import all_tasks


@contextlib.contextmanager
def monitor_common():
    def make_baz():
        return "baz"

    locals_ = {"foo": "bar", "make_baz": make_baz}
    event_loop = asyncio.get_running_loop()
    mon = Monitor(event_loop, locals=locals_)
    with mon:
        yield mon


@pytest.fixture
async def monitor(request, event_loop):
    with monitor_common() as monitor_instance:
        yield monitor_instance


@pytest.fixture
async def tn_client():
    dummy_stdout = open(os.devnull, "wb")
    dummy_stdin = open(os.devnull, "rb")
    for _ in range(10):
        try:
            async with TelnetClient(
                MONITOR_HOST,
                MONITOR_PORT,
                stdin=dummy_stdin,
                stdout=dummy_stdout,
                output_replication_queue=asyncio.Queue(),
            ) as client:
                yield client
            return
        except OSError as e:
            print("Retrying after error: {}".format(str(e)))
            await asyncio.sleep(1)
        finally:
            dummy_stdout.close()
    else:
        pytest.fail("Can not connect to the telnet server")


async def execute(tn, command, pattern=b">>>"):
    tn._conn_writer.write(command)
    await tn._conn_writer.drain()
    buf = io.BytesIO()
    while True:
        data = await tn._output_replication_queue.get()
        buf.write(data)
        if not data:
            return buf.getvalue()
        if pattern in data:
            return buf.getvalue()


async def execute_v2(monitor: Monitor, command, pattern=b">>>"):
    # TODO: mock TelnetConnection to directly interact with PromptSession
    pass


def get_task_ids(event_loop):
    return [id(t) for t in all_tasks(loop=event_loop)]


@pytest.fixture(params=[True, False], ids=["console:True", "console:False"])
def console_enabled(request):
    return request.param


@pytest.mark.asyncio
async def test_ctor(event_loop, unused_port, console_enabled):

    with Monitor(event_loop, console_enabled=console_enabled):
        await asyncio.sleep(0.01)
    with start_monitor(event_loop, console_enabled=console_enabled) as m:
        await asyncio.sleep(0.01)
    assert m.closed

    m = Monitor(event_loop, console_enabled=console_enabled)
    m.start()
    try:
        await asyncio.sleep(0.01)
    finally:
        m.close()
        m.close()  # make sure call is idempotent
    assert m.closed

    m = Monitor(event_loop, console_enabled=console_enabled)
    m.start()
    with m:
        await asyncio.sleep(0.01)
    assert m.closed

    # make sure that monitor inside async func can exit correctly
    with Monitor(event_loop, console_enabled=console_enabled):
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_basic_monitor(monitor, tn_client, event_loop):
    tn = tn_client
    resp = await execute(tn, b"help\r\n")
    assert b"Commands" in resp

    resp = await execute(tn, b"xxx\r\n")
    assert b"No such command" in resp

    resp = await execute(tn, b"ps\r\n")
    assert b"Task" in resp

    resp = await execute(tn, b"ps 123\n")
    assert b"TypeError" in resp

    resp = await execute(tn, b"signal name\n")
    assert b"Unknown signal name" in resp

    resp = await execute(tn, b"stacktrace\n")
    assert b"event_loop.run_forever()" in resp

    resp = await execute(tn, b"w 123\n")
    assert b"No task 123" in resp

    resp = await execute(tn, b"where 123\n")
    assert b"No task 123" in resp

    resp = await execute(tn, b"c 123\n")
    assert b"Ambiguous command" in resp

    resp = await execute(tn, b"cancel 123\n")
    assert b"No task 123" in resp

    resp = await execute(tn, b"ca 123\n")
    assert b"No task 123" in resp


myvar = contextvars.ContextVar("myvar", default=42)


@pytest.mark.asyncio
async def test_monitor_task_factory(event_loop):
    async def do():
        await asyncio.sleep(0)
        myself = asyncio.current_task()
        assert myself is not None
        assert myself.get_name() == "mytask"

    with Monitor(event_loop, console_enabled=False, hook_task_factory=True):
        t = asyncio.create_task(do(), name="mytask")
        await t


@pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="The context argument of asyncio.create_task() is added in Python 3.11",
)
@pytest.mark.asyncio
async def test_monitor_task_factory_with_context():
    ctx = contextvars.Context()
    # This context is bound at the outermost scope,
    # and inside it the initial value of myvar is kept intact.

    async def do():
        await asyncio.sleep(0)
        assert myvar.get() == 42  # we are referring the outer context
        myself = asyncio.current_task()
        assert myself is not None
        assert myself.get_name() == "mytask"

    myvar.set(99)  # override in the current task's context
    event_loop = asyncio.get_running_loop()
    with Monitor(event_loop, console_enabled=False, hook_task_factory=True):
        t = asyncio.create_task(do(), name="mytask", context=ctx)
        await t
    assert myvar.get() == 99


@pytest.mark.asyncio
async def test_cancel_where_tasks(monitor, tn_client, event_loop):
    tn = tn_client

    async def sleeper():
        await asyncio.sleep(100)  # xxx

    t = asyncio.create_task(sleeper())
    # TODO: we should not rely on timeout
    await asyncio.sleep(0.1)

    try:
        task_ids = get_task_ids(event_loop)
        assert len(task_ids) > 0
        for t_id in task_ids:
            resp = await execute(tn, b"where {}\n".format(t_id))
            assert b"Task" in resp
            resp = await execute(tn, b"cancel {}\n".format(t_id))
            assert b"Cancel task" in resp
    finally:
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_monitor_with_console(monitor, tn_client):
    tn = tn_client
    resp = await execute(tn, b"console\n")
    assert b"This console is running in an asyncio event event_loop" in resp
    await execute(tn, "await asyncio.sleep(0)\n")

    resp = await execute(tn, b"foo\n")
    assert b" 'bar'\n>>>" == resp
    resp = await execute(tn, b"make_baz()\n")
    assert b" 'baz'\n>>>" == resp

    await execute(tn, b"exit()\n")

    resp = await execute(tn, b"help\n")
    assert b"Commands" in resp


# TODO: rewrite to follow the new click-based command interface
# @pytest.mark.asyncio
# async def test_custom_monitor_class(monitor, tn_client):
#     tn = tn_client
#     resp = await execute(tn, "something someargument\n")
#     assert "doing something with someargument" in resp
