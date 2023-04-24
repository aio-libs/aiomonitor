import os
from typing import Dict

from setuptools import find_packages, setup


def read(f):
    return open(os.path.join(os.path.dirname(__file__), f)).read().strip()


install_requires = [
    "attrs>=20",
    "click>=8",
    "janus>=1.0",
    "terminaltables",
    "typing-extensions>=4.1",
    "prompt_toolkit>=3.0",
    "aioconsole",
]
extras_require: Dict[str, str] = {}


classifiers = [
    "License :: OSI Approved :: MIT License",
    "Intended Audience :: Developers",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.8",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Operating System :: POSIX",
    "Development Status :: 3 - Alpha",
    "Framework :: AsyncIO",
]


setup(
    name="aiomonitor",
    use_scm_version=True,
    setup_requires=["setuptools_scm"],
    description=(
        "aiomonitor adds monitor and python REPL "
        "capabilities for asyncio application"
    ),
    long_description="\n\n".join((read("README.rst"), read("CHANGES.rst"))),
    classifiers=classifiers,
    platforms=["POSIX"],
    author="Nikolay Novik",
    author_email="nickolainovik@gmail.com",
    url="https://github.com/aio-libs/aiomonitor",
    download_url="https://pypi.python.org/pypi/aiomonitor",
    license="Apache 2",
    packages=find_packages(),
    install_requires=install_requires,
    extras_require=extras_require,
    include_package_data=True,
    python_requires=">=3.8",
)
