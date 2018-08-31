Examples of aiomonitor usage
============================

Below is a list of examples from `aiomonitor/examples
<https://github.com/jettify/aiomonitor/tree/master/examples>`_

Every example is a correct tiny python program.

.. _aiomonitor-examples-simple:

Basic Usage
-----------

Basic example, starts monitor around ``loop.run_forever()`` function:

.. literalinclude:: ../examples/simple_loop.py

aiohttp Example
---------------

Full feature example with aiohttp application:

.. literalinclude:: ../examples/simple_aiohttp_srv.py

Any above examples compatible with uvloop_, in fact aiomonitor test suite
executed against asyncio and uvloop.

.. _uvloop: https://github.com/MagicStack/uvloop

aiohttp Example with additional command
---------------------------------------

Same as above, but showing a custom command:

.. literalinclude:: ../examples/web_srv_custom_monitor.py
