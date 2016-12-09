import asyncio
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
        metafunc.parametrize("loop_type", loop_type)


@pytest.yield_fixture
def loop(request, loop_type):
    old_loop = asyncio.get_event_loop()
    asyncio.set_event_loop(None)
    if loop_type == 'uvloop':
        loop = uvloop.new_event_loop()
    else:
        loop = asyncio.new_event_loop()

    yield loop

    loop.close()
    asyncio.set_event_loop(old_loop)
    gc.collect()


@pytest.mark.tryfirst
def pytest_pycollect_makeitem(collector, name, obj):
    if collector.funcnamefilter(name):
        item = pytest.Function(name, parent=collector)
        if 'run_loop' in item.keywords:
            return list(collector._genfunctions(name, obj))


@pytest.mark.tryfirst
def pytest_pyfunc_call(pyfuncitem):
    """
    Run asyncio marked test functions in an event loop instead of a normal
    function call.
    """
    if 'run_loop' in pyfuncitem.keywords:
        funcargs = pyfuncitem.funcargs
        loop = funcargs['loop']
        testargs = {arg: funcargs[arg]
                    for arg in pyfuncitem._fixtureinfo.argnames}

        if not asyncio.iscoroutinefunction(pyfuncitem.obj):
            func = asyncio.coroutine(pyfuncitem.obj)
        else:
            func = pyfuncitem.obj
        loop.run_until_complete(func(**testargs))
        return True


def pytest_runtest_setup(item):
    if 'run_loop' in item.keywords and 'loop' not in item.fixturenames:
        # inject an event loop fixture for all async tests
        item.fixturenames.append('loop')
