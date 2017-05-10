import asyncio
import os
import gc
import socket

import pytest
import uvloop


@pytest.fixture(scope='session')
def unused_port():
    def f():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', 0))
            return s.getsockname()[1]
    return f


def pytest_generate_tests(metafunc):
    if 'loop_type' in metafunc.fixturenames:
        loop_type = ['asyncio', 'uvloop']
        if os.environ.get('TOKIO') == 'y':
            loop_type.append('tokio')
        metafunc.parametrize("loop_type", loop_type)


@pytest.yield_fixture
def loop(request, loop_type):
    old_loop = asyncio.get_event_loop()
    asyncio.set_event_loop(None)
    if loop_type == 'uvloop':
        loop = uvloop.new_event_loop()
    elif loop_type == 'tokio':
        import tokio
        policy = tokio.TokioLoopPolicy()
        asyncio.set_event_loop_policy(policy)
        loop = tokio.new_event_loop()
    else:
        loop = asyncio.new_event_loop()

    yield loop

    loop.close()
    asyncio.set_event_loop(old_loop)
    gc.collect()
