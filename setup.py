#!/usr/bin/env python

from setuptools import setup
import pathlib

setup(
    name="mp2-validator",
    version=pathlib.Path("version").read_text().strip(),
    packages=[],
    scripts=["main.py"],
)
