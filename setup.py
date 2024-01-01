#!/usr/bin/env python3

from setuptools import setup
from setuptools import find_packages


setup(
    name                 = "litesdcard",
    description          = "Small footprint and configurable SD Card core",
    author               = "Florent Kermarrec, Pierre-Olivier Vauboin",
    author_email         = "florent@enjoy-digital.fr, po@lambdaconcept.com",
    url                  = "http://enjoy-digital.fr",
    download_url         = "https://github.com/enjoy-digital/litesdcard",
    test_suite           = "test",
    license              = "BSD",
    python_requires      = "~=3.7",
    packages             = find_packages(exclude=("test*", "sim*", "doc*", "examples*")),
    include_package_data = True,
    keywords             = "HDL ASIC FPGA hardware design",
    classifiers          = [
        "Topic :: Scientific/Engineering :: Electronic Design Automation (EDA)",
        "Environment :: Console",
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
    ],
    entry_points         = {
        "console_scripts": [
            "litesdcard_gen=litesdcard.gen:main",
        ],
    },
)
