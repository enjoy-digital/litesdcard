#!/usr/bin/env python3

from setuptools import setup
from setuptools import find_packages


setup(
    name="litesdcard",
    python_requires="~=3.6",
	description="Small footprint and configurable SD Card core",
	author="Pierre-Olivier Vauboin, Florent Kermarrec",
	author_email="po@lambdaconcept.com, florent@enjoy-digital.fr",
	url="http://enjoy-digital.fr",
	download_url="https://github.com/enjoy-digital/litesdcard",
	test_suite="test",
    license="BSD",
    packages=find_packages(exclude=("test*", "sim*", "doc*", "examples*")),
    include_package_data=True,
)
