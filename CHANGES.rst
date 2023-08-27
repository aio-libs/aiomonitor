CHANGES
=======

.. towncrier release notes start

0.6.0 (2023-08-27)
------------------

- Add the web-based monitoring user interface to list, inspect, and cancel running/terminated tasks, with refactoring the monitor business logic and presentation layers (`termui` and `webui`)
  (`#84 <https://github.com/aio-libs/aiomonitor/issues/84>`_)

- Replace the default port numbers for the terminal UI, the web UI, and the console access (50101, 50201, 50102 -> 20101, 20102, 20103 respectively)
  (`#374 <https://github.com/aio-libs/aiomonitor/issues/374>`_)

- Adopt towncrier to auto-generate the changelog
  (`#375 <https://github.com/aio-libs/aiomonitor/issues/375>`_)


0.5.0 (2023-07-21)
------------------

* Fix a regression in Python 3.10 due to #10 (`#11 <https://github.com/aio-libs/aiomonitor/issues/11>`_)

* Support Python 3.11 properly by allowing the optional (`name` and `context` kwargs passed to `asyncio.create_task()` in the hooked task factory function `#10 <https://github.com/aio-libs/aiomonitor/issues/10>`_)

* Update development dependencies

* Selective persistent termination logs (`#9 <https://github.com/aio-libs/aiomonitor/issues/9>`_)

* Implement cancellation chain tracker (`#8 <https://github.com/aio-libs/aiomonitor/issues/8>`_)

* Trigger auto-completion only when Tab is pressed

* Support auto-completion of commands and arguments (`#7 <https://github.com/aio-libs/aiomonitor/issues/7>`_)

* Add missing explicit dependency to Click

* Promote `console_locals` as public attr

* Reimplement console command (`#6 <https://github.com/aio-libs/aiomonitor/issues/6>`_)

* Migrate to Click-based command line interface (`#5 <https://github.com/aio-libs/aiomonitor/issues/5>`_)

* Adopt (`prompt_toolkit` and support concurrent clients `#4 <https://github.com/aio-libs/aiomonitor/issues/4>`_)

* Show the total number of tasks when executing (`ps` `#3 <https://github.com/aio-libs/aiomonitor/issues/3>`_)

* Apply black, isort, mypy, flake8 and automate CI workflows using GitHub Actions

* Fix the task creation location in the 'ps' command output

* Remove loop=loop from all asynchronous calls to support newer Python versions (`#329 <https://github.com/aio-libs/aiomonitor/issues/329>`_)

* Added the task creation stack chain display to the 'where' command by setting a custom task factory (`#1 <https://github.com/aio-libs/aiomonitor/issues/1>`_)

These are the backported changes from [aiomonitor-ng](https://github.com/achimnol/aiomonitor-ng).
As the version bumps have gone far away in the fork, all those extra releases are squashed into the v0.5.0 release.


0.4.5 (2019-11-03)
------------------

* Fixed endless loop on EOF (thanks @apatrushev)


0.4.4 (2019-03-23)
------------------

* Simplified python console start end #175

* Added python 3.7 compatibility #176


0.4.3 (2019-02-02)
------------------

* Reworked console server start/close logic #169


0.4.2 (2019-01-13)
------------------

* Fixed issue with type annotations from 0.4.1 release #164


0.4.1 (2019-01-10)
------------------

* Fixed Python 3.5 support #161 (thanks @bmerry)


0.4.0 (2019-01-04)
------------------

* Added support for custom commands #133 (thanks @yggdr)

* Fixed OptLocals being passed as the default value for "locals" #122 (thanks @agronholm)

* Added an API inspired by the standard library's cmd module #135 (thanks @yggdr)

* Correctly report the port running aioconsole #124 (thanks @bmerry)


0.3.1 (2018-07-03)
------------------

* Added the stacktrace command #120 (thanks @agronholm)


0.3.0 (2017-09-08)
------------------

* Added _locals_ parameter for passing environment to python REPL


0.2.1 (2016-01-03)
------------------

* Fixed import in telnet cli in #12 (thanks @hellysmile)


0.2.0 (2016-01-01)
------------------

* Added basic documentation

* Most of methods of Monitor class are not not private api


0.1.0 (2016-12-14)
------------------

* Added missed LICENSE file

* Updated API, added start_monitor() function


0.0.3 (2016-12-11)
------------------

* Fixed README.rst


0.0.2 (2016-12-11)
------------------

* Tests more stable now

* Added simple tutorial to README.rst


0.0.1 (2016-12-10)
------------------

* Initial release.
