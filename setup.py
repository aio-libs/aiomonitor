import os
import re
import sys
from typing import Dict

from setuptools import find_packages, setup

PY_VER = sys.version_info

if not PY_VER >= (3, 8):
    raise RuntimeError("aiomonitor doesn't support Python earlier than 3.8")


def read(f):
    return open(os.path.join(os.path.dirname(__file__), f)).read().strip()


install_requires = [
    "terminaltables",
    "prompt_toolkit>=3.0",
    "aioconsole",
]
extras_require: Dict[str, str] = {}


def read_version():
    regexp = re.compile(r'^__version__\W*=\W*"([\d.abrc]+)"')
    init_py = os.path.join(os.path.dirname(__file__), "aiomonitor", "__init__.py")
    with open(init_py) as f:
        for line in f:
            if m := regexp.match(line):
                return m.group(1)
        else:
            msg = "Cannot find version in aiomonitor/__init__.py"
            raise RuntimeError(msg)


classifiers = [
    "License :: OSI Approved :: MIT License",
    "Intended Audience :: Developers",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.8",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Operating System :: POSIX",
    "Development Status :: 3 - Alpha",
    "Framework :: AsyncIO",
]


setup(
    name="aiomonitor-ng",
    version=read_version(),
    description=(
        "aiomonitor-ng adds monitor and python REPL "
        "capabilities for asyncio application"
    ),
    long_description="\n\n".join((read("README.rst"), read("CHANGES.txt"))),
    classifiers=classifiers,
    platforms=["POSIX"],
    author="Nikolay Novik",
    author_email="nickolainovik@gmail.com",
    url="https://github.com/achimnol/aiomonitor-ng",
    download_url="https://pypi.python.org/pypi/aiomonitor-ng",
    license="Apache 2",
    packages=find_packages(),
    install_requires=install_requires,
    extras_require=extras_require,
    include_package_data=True,
)
