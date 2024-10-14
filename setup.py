#!/usr/bin/env python

from setuptools import setup
import pathlib

setup(
    name="mp2-validator",
    version=pathlib.Path("version").read_text().strip(),
    packages=["repro_validator"],
    entry_points={
        "console_scripts": [
            "repro-validator = repro_validator.main:app",
        ],
    },
)
