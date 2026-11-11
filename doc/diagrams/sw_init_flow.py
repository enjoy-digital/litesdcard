#
# This file is part of LiteSDCard.
#
# Copyright (c) 2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# sdcard_init() of the LiteX BIOS driver: CMD8 tells an SD card (left) from an eMMC that answers
# CMD1 (right); both paths end with 512-byte blocks.

from svgdiag import *


def build():
    d = Diagram(CANVAS_WIDTH, 470)
    start = d.add(Box(240, 20, 280, 50, label="1-bit bus, 400 kHz\n80 clocks, CMD0, CMD8"))
    dec   = d.add(Box(290, 105, 180, 44, label="CMD8 answered?", fill=COLOR_ACCENT))
    sd1   = d.add(Box(30, 175, 240, 50, label="25 MHz, CMD55 + ACMD41\nuntil ready", fill=COLOR_ACCENT_LIGHT))
    sd2   = d.add(Box(30, 250, 240, 50, label="CMD2, CMD3, CMD10,\nCMD9, CMD7", fill=COLOR_ACCENT_LIGHT))
    sd3   = d.add(Box(30, 325, 240, 50, label="CMD6 high speed, ACMD51,\nACMD6 4-bit if SCR", fill=COLOR_ACCENT_LIGHT))
    mmc1  = d.add(Box(490, 175, 240, 50, label="CMD1 until ready, CMD2,\nCMD3, CMD9, CMD7"))
    mmc2  = d.add(Box(490, 250, 240, 50, label="EXT_CSD: 8-bit or 4-bit,\nhigh speed at 50 MHz"))
    end   = d.add(Box(260, 405, 240, 44, label="CMD16: 512-byte blocks"))
    d.add(Arrow((start, "b"), (dec, "t"), kind="control"))
    d.add(Arrow((dec, "l"), (sd1, "t"), kind="control", label="yes: SD card", label_pos=(205, 117)))
    d.add(Arrow((dec, "r"), (mmc1, "t"), kind="control", label="no, CMD1: eMMC", label_pos=(560, 117)))
    d.add(Arrow((sd1, "b"), (sd2, "t"), kind="control"))
    d.add(Arrow((sd2, "b"), (sd3, "t"), kind="control"))
    d.add(Arrow((sd3, "b"), (end, "l"), kind="control"))
    d.add(Arrow((mmc1, "b"), (mmc2, "t"), kind="control"))
    d.add(Arrow((mmc2, "b"), (end, "r"), kind="control"))
    return d
