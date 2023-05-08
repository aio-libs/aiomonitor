import asyncio
import contextlib
import contextvars
import functools
import io
import sys
import unittest.mock
from typing import Sequence

import click
import pytest
from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from prompt_toolkit.shortcuts import print_formatted_text

from aiomonitor import Monitor, start_monitor
from aiomonitor.monitor import (
    auto_command_done,
    command_done,
    current_monitor,
    current_stdout,
    custom_help_option,
    monitor_cli,
)
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


def get_task_ids(event_loop):
    return [id(t) for t in all_tasks(loop=event_loop)]


class BufferedOutput(DummyOutput):
    def __init__(self) -> None:
        self._buffer = io.StringIO()

    def write(self, data: str) -> None:
        self._buffer.write(data)

    def write_raw(self, data: str) -> None:
        self._buffer.write(data)


async def invoke_command(monitor: Monitor, args: Sequence[str]) -> str:
    dummy_stdout = io.StringIO()
    current_monitor_token = current_monitor.set(monitor)
    current_stdout_token = current_stdout.set(dummy_stdout)
    command_done_event = asyncio.Event()
    command_done_token = command_done.set(command_done_event)
    with unittest.mock.patch(
        "aiomonitor.monitor.print_formatted_text",
        functools.partial(print_formatted_text, file=dummy_stdout),
    ):
        try:
            ctx = contextvars.copy_context()
            ctx.run(
                monitor_cli.main,
                args,
                prog_name="",
                obj=monitor,
                standalone_mode=False,  # type: ignore
            )
            await command_done_event.wait()
            return dummy_stdout.getvalue()
        finally:
            command_done.reset(command_done_token)
            current_stdout.reset(current_stdout_token)
            current_monitor.reset(current_monitor_token)


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
async def test_basic_monitor(monitor: Monitor):
    resp = await invoke_command(monitor, ["help"])
    assert "Commands:" in resp

    with pytest.raises(click.UsageError):
        await invoke_command(monitor, ["xxx"])

    resp = await invoke_command(monitor, ["ps"])
    assert "Task" in resp

    with pytest.raises(click.UsageError):
        await invoke_command(monitor, ["ps", "123"])

    resp = await invoke_command(monitor, ["signal", "name"])
    assert "Unknown signal" in resp

    resp = await invoke_command(monitor, ["stacktrace"])
    assert "self.run_forever()" in resp

    resp = await invoke_command(monitor, ["w", "123"])
    assert "No task 123" in resp

    resp = await invoke_command(monitor, ["where", "123"])
    assert "No task 123" in resp

    with pytest.raises(click.UsageError):
        await invoke_command(monitor, ["c", "123"])

    resp = await invoke_command(monitor, ["cancel", "123"])
    assert "No task 123" in resp

    resp = await invoke_command(monitor, ["ca", "123"])
    assert "No task 123" in resp


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
async def test_cancel_where_tasks(
    monitor: Monitor,
    event_loop: asyncio.AbstractEventLoop,
) -> None:
    async def sleeper():
        await asyncio.sleep(100)  # xxx

    t = asyncio.create_task(sleeper())
    t_id = id(t)
    await asyncio.sleep(0.1)

    try:
        task_ids = get_task_ids(event_loop)
        assert len(task_ids) > 0
        assert t_id in task_ids
        resp = await invoke_command(monitor, ["where", str(t_id)])
        assert "Task" in resp
        resp = await invoke_command(monitor, ["cancel", str(t_id)])
        assert "Cancelled task" in resp
        await asyncio.sleep(0.1)
    finally:
        if not t.done():
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass


@pytest.mark.asyncio
async def test_monitor_with_console(monitor: Monitor) -> None:
    with create_pipe_input() as pipe_input:
        stdout_buf = BufferedOutput()
        with create_app_session(input=pipe_input, output=stdout_buf):
            await invoke_command(monitor, ["console"])
            await asyncio.sleep(0.2)
            pipe_input.send_text("await asyncio.sleep(0.1, result=333)\r\n")
            pipe_input.send_text("foo\r\n")
            await asyncio.sleep(0.5)
            resp = stdout_buf._buffer.getvalue()
            assert "This console is running in an asyncio event loop." in resp
            assert "333" in resp
            assert "bar" in resp
            pipe_input.send_text("exit()\r\n")
            await asyncio.sleep(0.2)
    # Check if we are back to the original shell.
    resp = await invoke_command(monitor, ["help"])
    assert "Commands" in resp


@pytest.mark.asyncio
async def test_custom_monitor_command(monitor: Monitor):
    @monitor_cli.command(name="something")
    @click.argument("arg")
    @custom_help_option
    @auto_command_done
    def do_something(ctx: click.Context, arg: str) -> None:
        self: Monitor = ctx.obj
        self.print_ok(f"doing something with {arg}")

    resp = await invoke_command(monitor, ["something", "someargument"])
    assert "doing something with someargument" in resp
