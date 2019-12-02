#!/bin/sh -ex

if ! [ -f venv/bin/activate ]; then
  virtualenv --python=$(which python3) venv
fi

. venv/bin/activate

pip install -U pip setuptools twine

python setup.py sdist bdist_wheel

deactivate

if ! [ -f venv2/bin/activate ]; then
  virtualenv --python=$(which python2) venv2
fi

. venv2/bin/activate

pip install -U pip setuptools

python setup.py bdist_wheel

venv/bin/twine upload dist/*
