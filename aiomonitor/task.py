import asyncio
import base64
import struct
import sys
import time
import traceback
from asyncio.coroutines import _format_coroutine  # type: ignore
from typing import Any, Generator, List, Optional

import janus

from .types import CancellationChain, TerminatedTaskInfo
from .utils import _extract_stack_from_frame


class TracedTask(asyncio.Task):
    _orig_coro: Generator[Any, Any, Any]
    _termination_stack: Optional[List[traceback.FrameSummary]]

    def __init__(
        self,
        *args,
        termination_info_queue: janus._SyncQueueProxy[TerminatedTaskInfo],
        cancellation_chain_queue: janus._SyncQueueProxy[CancellationChain],
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._termination_info_queue = termination_info_queue
        self._cancellation_chain_queue = cancellation_chain_queue
        self._started_at = time.perf_counter()
        self._termination_stack = None
        self.add_done_callback(self._trace_termination)

    def get_trace_id(self) -> str:
        h = hash(
            (
                id(self),
                self.get_name(),
            )
        )
        b = struct.pack("P", h)
        return base64.b32encode(b).rstrip(b"=").decode()

    def _trace_termination(self, _: asyncio.Task[Any]) -> None:
        self_id = self.get_trace_id()
        exc_repr = (
            repr(self.exception())
            if not self.cancelled() and self.exception()
            else None
        )
        task_info = TerminatedTaskInfo(
            self_id,
            name=self.get_name(),
            coro=_format_coroutine(self._orig_coro).partition(" ")[0],
            cancelled=self.cancelled(),
            exc_repr=exc_repr,
            started_at=self._started_at,
            terminated_at=time.perf_counter(),
            termination_stack=self._termination_stack,
            canceller_stack=None,
        )
        self._termination_info_queue.put_nowait(task_info)

    def cancel(self, msg: Optional[str] = None) -> bool:
        try:
            canceller_task = asyncio.current_task()
        except RuntimeError:
            canceller_task = None
        if canceller_task is not None and isinstance(canceller_task, TracedTask):
            canceller_stack = _extract_stack_from_frame(sys._getframe())[:-1]
            cancellation_chain = CancellationChain(
                self.get_trace_id(),
                canceller_task.get_trace_id(),
                canceller_stack,
            )
            self._cancellation_chain_queue.put_nowait(cancellation_chain)
        return super().cancel(msg)
