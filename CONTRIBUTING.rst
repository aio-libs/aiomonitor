Contributing
============

Running Tests
-------------

.. _GitHub: https://github.com/aio-libs/aiomonitor

Thanks for your interest in contributing to ``aiomonitor``, there are multiple
ways and places you can contribute.

Fist of all just clone repository::

    $ git clone git@github.com:aio-libs/aiomonitor.git

Create a virtualenv with Python 3.8 or later.  For example,
using *pyenv* commands could look like::

   $ cd aiomonitor
   $ pyenv virtualenv 3.11 aiomonitor-dev
   $ pyenv local aiomonitor-dev

After that please install the dependencies required for development
and the sources as an editable package::

    $ pip install -r requirements-dev.txt

Congratulations, you are ready to run the test suite::

    $ python -m pytest --cov tests

To run individual tests use the following command::

    $ python -m pytest -sv tests/test_monitor.py -k test_name


Reporting an Issue
------------------

If you have found issue with `aiomonitor` please do
not hesitate to file an issue on the GitHub_ project. When filing your
issue please make sure you can express the issue with a reproducible test
case.

When reporting an issue we also need as much information about your environment
that you can include. We never know what information will be pertinent when
trying narrow down the issue. Please include at least the following
information:

* Version of `aiomonitor` and `python`.
* Version `uvloop` if installed.
* Platform you're running on (OS X, Linux).
