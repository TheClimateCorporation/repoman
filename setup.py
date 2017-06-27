#!/usr/bin/env python

from setuptools import setup, find_packages

__name__ = 'apt-repoman'
__version__ = '1.0.2'

setup(
    name=__name__,
    packages=find_packages(),
    version=__version__,
    description='A high performance Debian APT repository based on Amazon Web Services',
    author='Nathan J. Mehl',
    author_email='n@climate.com',
    url='https://github.com/theclimatecorporation/repoman',
    download_url='https://github.com/theclimatecorporation/repoman/tarball/%s' % __version__,
    keywords=['apt', 'debian', 'dpkg', 'packaging'],
    package_data={'': ['*.json']},
    install_requires=[
        'PGPy==0.4.1',
        'ansicolors==1.1.8',
        'boto3==1.4.4',
        'configargparse==0.12.0',
        'pydpkg==1.3.1',
        'pysectools==0.4.2',
        'tabulate==0.7.7'
    ],
    extras_require={
        'test': ['mock==2.0.0', 'pep8==1.7.0', 'pytest==3.1.1', 'pylint==1.7.1']
    },
    #scripts=[
    #    'scripts/repoman'
    #],
    entry_points = {
        'console_scripts': ['repoman-cli=apt_repoman.cli:main'],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3.3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: Implementation :: CPython",
        "Topic :: System :: Archiving :: Packaging",
        ]
)
