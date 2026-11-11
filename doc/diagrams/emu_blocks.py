#
# This file is part of LiteSDCard.
#
# Copyright (c) 2020-2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# SD card emulator (litesdcard/emulator/core.py): the LiteSDCard PHY drives the emulator pads;
# the Verilog sd_phy and sd_link model the card; a block store (one 512-byte buffer by default)
# holds the data and the wrapper acknowledges every block request at once.

from svgdiag import *


def build():
    d = Diagram(CANVAS_WIDTH, 300)
    phy  = d.add(Box(10, 110, 130, 60, label="SDPHY\n(emulator IO)", fill=COLOR_ACCENT_LIGHT))
    emu  = d.add(Container(200, 10, 550, 280, title="SDEmulator", title_pos="br"))
    sphy = d.add(Box(230, 110, 140, 60, label="sd_phy", fill=COLOR_ACCENT))
    link = d.add(Box(560, 110, 140, 60, label="sd_link", fill=COLOR_ACCENT))
    buf  = d.add(Box(230, 210, 140, 46, label="block store"))
    ack  = d.add(Box(560, 30, 140, 46, label="immediate ack"))
    d.add(Arrow((phy, "r"), (sphy, "l"), kind="data", heads="both", label="clk, cmd, dat",
        label_pos=(195, 96), label_anchor="end"))
    d.add(Arrow((sphy, "r"), (link, "l"), heads="both", label="commands, responses",
        label_pos=(465, 128)))
    d.add(Arrow((sphy, "b"), (buf, "t"), kind="data", heads="both", label="block data",
        label_pos=(310, 190), label_anchor="start"))
    d.add(Arrow((link, "b"), (buf, "r"), via=[(630, 233)], label="block address (with size or image)",
        label_pos=(500, 222)))
    d.add(Arrow((link, "t", 0.3), (ack, "b", 0.3), label="act", label_pos=(584, 93),
        label_anchor="end"))
    d.add(Arrow((ack, "b", 0.7), (link, "t", 0.7), kind="feedback", label="go, done",
        label_pos=(668, 93), label_anchor="start"))
    return d
