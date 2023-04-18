import os
from setuptools import setup, find_packages


def read(f):
    return open(os.path.join(os.path.dirname(__file__), f)).read().strip()


install_requires = ['terminaltables',
                    'aioconsole']
extras_require = {}


classifiers = [
    'License :: OSI Approved :: MIT License',
    'Intended Audience :: Developers',
    'Programming Language :: Python :: 3',
    'Programming Language :: Python :: 3.8',
    'Programming Language :: Python :: 3.9',
    'Programming Language :: Python :: 3.10',
    'Programming Language :: Python :: 3.11',
    'Operating System :: POSIX',
    'Development Status :: 3 - Alpha',
    'Framework :: AsyncIO',
]


setup(name='aiomonitor',
      use_scm_version=True,
      setup_requires=['setuptools_scm'],
      description=('aiomonitor adds monitor and python REPL '
                   'capabilities for asyncio application'),
      long_description='\n\n'.join((read('README.rst'), read('CHANGES.txt'))),
      classifiers=classifiers,
      platforms=['POSIX'],
      author='Nikolay Novik',
      author_email='nickolainovik@gmail.com',
      url='https://github.com/aio-libs/aiomonitor',
      download_url='https://pypi.python.org/pypi/aiomonitor',
      license='Apache 2',
      packages=find_packages(),
      install_requires=install_requires,
      extras_require=extras_require,
      include_package_data=True,
      python_requires=">=3.8",
      )
