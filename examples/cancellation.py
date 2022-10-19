import asyncio

import aiomonitor
from aiomonitor.task import preserve_termination_log


@preserve_termination_log
async def should_have_run_until_exit():
    print("should_have_run_until_exit: begin")
    await asyncio.sleep(5)
    print("should_have_run_until_exit: cancel")
    raise asyncio.CancelledError("cancelled-suspiciously")


async def chain3():
    await asyncio.sleep(10)


async def chain2():
    t = asyncio.create_task(chain3())
    try:
        await asyncio.sleep(10)
    finally:
        t.cancel()
        await t


async def chain1():
    t = asyncio.create_task(chain2())
    try:
        await asyncio.sleep(10)
    finally:
        t.cancel()
        await t


async def chain_main():
    try:
        while True:
            t = asyncio.create_task(chain1())
            await asyncio.sleep(0.5)
            t.cancel()
    finally:
        print("terminating chain_main")


async def self_cancel_main():
    async def do_self_cancel(tick):
        await asyncio.sleep(tick)
        raise asyncio.CancelledError("self-cancelled")

    try:
        while True:
            await asyncio.sleep(0.21)
            asyncio.create_task(do_self_cancel(0.2))
    finally:
        print("terminating self_cancel_main")


async def unhandled_exc_main():
    async def do_unhandled(tick):
        await asyncio.sleep(tick)
        return 1 / 0

    try:
        while True:
            try:
                await asyncio.create_task(do_unhandled(0.2))
            except ZeroDivisionError:
                continue
    finally:
        print("terminating unhandled_exc_main")


async def main():
    loop = asyncio.get_running_loop()
    with aiomonitor.start_monitor(
        loop,
        hook_task_factory=True,
        max_termination_history=10,
    ):
        asyncio.create_task(should_have_run_until_exit())
        chain_main_task = asyncio.create_task(chain_main())
        self_cancel_main_task = asyncio.create_task(self_cancel_main())
        unhandled_exc_main_task = asyncio.create_task(unhandled_exc_main())
        try:
            print("running some test workloads for 10 seconds ...")
            await asyncio.sleep(10)
        finally:
            print("stopping ...")
            chain_main_task.cancel()
            self_cancel_main_task.cancel()
            unhandled_exc_main_task.cancel()
            await asyncio.gather(
                chain_main_task,
                self_cancel_main_task,
                unhandled_exc_main_task,
                return_exceptions=True,
            )
        print("waiting inspection ...")
        while True:
            await asyncio.sleep(10)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("terminated")
