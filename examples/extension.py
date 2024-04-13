import asyncio

import click

import aiomonitor
from aiomonitor.termui.commands import (
    auto_async_command_done,
    auto_command_done,
    print_fail,
    print_ok,
)


@aiomonitor.monitor_cli.command(name="hello")
@auto_command_done
def do_hello(ctx: click.Context) -> None:
    """
    Command extension example
    """
    # To send outputs to the telnet client,
    # you should use either:

    click.echo("Hello, world!")

    # or:

    from aiomonitor.termui.commands import current_stdout

    stdout = current_stdout.get()
    print("Hello, world, again!", file=stdout)

    # or:

    from prompt_toolkit import print_formatted_text
    from prompt_toolkit.formatted_text import FormattedText

    print_formatted_text(
        FormattedText([
            ("ansibrightblue", "Hello, "),
            ("ansibrightyellow", "world, "),
            ("ansibrightmagenta", "with color!"),
        ])
    )

    # or:

    print_ok("Hello, world, success!")
    print_fail("Hello, world, failure!")


@aiomonitor.monitor_cli.command(name="hello-async")
def do_async_hello(ctx: click.Context) -> None:
    """
    Command extension example (async)
    """

    @auto_async_command_done
    async def _do_async_hello(ctx: click.Context):
        await asyncio.sleep(1)
        click.echo("Hello, world, after sleep!")

    asyncio.create_task(_do_async_hello(ctx))


async def main():
    loop = asyncio.get_running_loop()
    with aiomonitor.start_monitor(loop=loop) as monitor:
        print("Now you can connect with:")
        print(f"  python -m aiomonitor.cli -H {monitor.host} -p {monitor.port}")
        print("or")
        print(f"  telnet {monitor.host} {monitor.port}  # Linux only")
        # run forever until interrupted
        while True:
            await asyncio.sleep(60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
