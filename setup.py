#!/usr/bin/env python3

from setuptools import setup
from setuptools import find_packages


setup(
    name="litesdcard",
	description="Small footprint and configurable SD Card core",
	author="Florent Kermarrec, Pierre-Olivier Vauboin",
	author_email="florent@enjoy-digital.fr, po@lambdaconcept.com",
	url="http://enjoy-digital.fr",
	download_url="https://github.com/enjoy-digital/litesdcard",
	test_suite="test",
    license="BSD",
    python_requires="~=3.6",
    packages=find_packages(exclude=("test*", "sim*", "doc*", "examples*")),
    include_package_data=True,
)
