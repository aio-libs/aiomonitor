import asyncio
import sys
import time

from .utils import _extract_stack_from_frame


class TracedTask(asyncio.Task):
    def __init__(
        self,
        *args,
        cancelled_tracebacks=None,
        cancelled_traceback_chains=None,
        **kwargs
    ) -> None:
        super().__init__(*args, **kwargs)
        self._cancelled_tracebacks = cancelled_tracebacks
        self._cancelled_traceback_chains = cancelled_traceback_chains
        self._started_at = time.monotonic()

    def cancel(self, msg: str = None) -> bool:
        try:
            canceller_task = asyncio.current_task()
        except RuntimeError:
            canceller_task = None
        if canceller_task is not None and self._cancelled_traceback_chains:
            self._cancelled_traceback_chains[self] = canceller_task
        if self._cancelled_tracebacks:
            self._cancelled_tracebacks[self] = _extract_stack_from_frame(
                sys._getframe()
            )[:-1]
        return super().cancel()
