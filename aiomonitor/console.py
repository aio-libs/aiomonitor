from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import aioconsole
from prompt_toolkit import PromptSession
from prompt_toolkit.input.base import Input
from prompt_toolkit.output.base import Output


class ConsoleProxy:
    def __init__(
        self,
        stdin: Input,
        stdout: Output,
        host: str,
        port: int,
    ) -> None:
        self._host = host
        self._port = port
        self._stdin = stdin
        self._stdout = stdout

    async def __aenter__(self) -> ConsoleProxy:
        self._stdout.write_raw("\r\n")
        self._conn_reader, self._conn_writer = await asyncio.open_connection(
            self._host, self._port
        )
        self._closed = asyncio.Event()
        self._recv_task = asyncio.create_task(self._handle_received())
        self._input_task = asyncio.create_task(self._handle_user_input())
        return self

    async def __aexit__(self, *exc_info) -> Optional[bool]:
        self._input_task.cancel()
        await self._input_task
        self._conn_writer.close()
        try:
            await self._conn_writer.wait_closed()
        except NotImplementedError:
            pass
        self._conn_reader.feed_eof()
        await self._recv_task
        return None

    async def interact(self) -> None:
        try:
            await self._closed.wait()
        finally:
            self._closed.set()
            self._conn_writer.write_eof()

    async def _handle_user_input(self) -> None:
        prompt_session: PromptSession[str] = PromptSession(
            input=self._stdin, output=self._stdout
        )
        try:
            while not self._conn_reader.at_eof():
                try:
                    user_input = await prompt_session.prompt_async("")
                    self._conn_writer.write(user_input.encode("utf8"))
                    self._conn_writer.write(b"\n")
                    await self._conn_writer.drain()
                except KeyboardInterrupt:
                    # Send Ctrl+C to the console server.
                    self._conn_writer.write(b"\x03")
                    await self._conn_writer.drain()
                except EOFError:
                    return
        except asyncio.CancelledError:
            pass
        finally:
            self._closed.set()

    async def _handle_received(self) -> None:
        try:
            while True:
                buf = await self._conn_reader.read(1024)
                if not buf:
                    return
                self._stdout.write_raw(buf.decode("utf8"))
                self._stdout.flush()
        except asyncio.CancelledError:
            pass
        finally:
            self._closed.set()


async def start(
    host: str,
    port: int,
    locals: Optional[Dict[str, Any]],
    monitor_loop: asyncio.AbstractEventLoop,
) -> asyncio.AbstractServer:
    ui_loop = asyncio.get_running_loop()
    done = asyncio.Event()

    async def _start(done: asyncio.Event) -> asyncio.AbstractServer:
        def _factory(streams: Any = None) -> aioconsole.AsynchronousConsole:
            return aioconsole.AsynchronousConsole(
                locals=locals, streams=streams, loop=monitor_loop
            )

        try:
            server = await aioconsole.start_interactive_server(
                host=host,
                port=port,
                factory=_factory,
                loop=monitor_loop,
            )
        finally:
            ui_loop.call_soon_threadsafe(done.set)
        return server

    console_future = asyncio.run_coroutine_threadsafe(
        _start(done),
        loop=monitor_loop,
    )
    try:
        await done.wait()
    finally:
        server = console_future.result()
    return server


async def close(
    server: asyncio.AbstractServer,
    monitor_loop: asyncio.AbstractEventLoop,
) -> None:
    ui_loop = asyncio.get_running_loop()
    done = asyncio.Event()

    async def _close(done: asyncio.Event) -> None:
        try:
            server.close()
            await server.wait_closed()
        except NotImplementedError:
            pass
        finally:
            ui_loop.call_soon_threadsafe(done.set)

    close_future = asyncio.run_coroutine_threadsafe(
        _close(done),
        loop=monitor_loop,
    )
    try:
        # NOTE: If the monitor is interrupted before the aioconsole session is closed,
        #       run_coroutine_threadsafe() seems to get deadlocked.
        #       In that case, you may need to send SIGINT multiple times to the
        #       aiomonitor-running process.
        await done.wait()
    finally:
        close_future.result()


async def proxy(sin: Input, sout: Output, host: str, port: int) -> None:
    async with ConsoleProxy(sin, sout, host, port) as proxy:
        await proxy.interact()
