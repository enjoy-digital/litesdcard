#
# This file is part of LiteSDCard.
#
# Copyright (c) 2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# Card states used by a single-card host: identification mode (idle to stby), data transfer mode
# (tran, data, rcv, prg), with the commands that move the card between them.

from primer_helpers import *


def build():
    d = Diagram(CANVAS_WIDTH, 420)
    d.add(Container(20, 10, 720, 125, title="Identification mode", title_pos="tl"))
    idle  = d.add(Box(40,  65, 120, 44, label="idle"))
    ready = d.add(Box(215, 65, 120, 44, label="ready"))
    ident = d.add(Box(390, 65, 120, 44, label="ident"))
    stby  = d.add(Box(565, 65, 120, 44, label="stby"))
    d.add(Container(20, 165, 720, 245, title="Data transfer mode", title_pos="tl"))
    tran = d.add(Box(565, 205, 120, 160, label="tran", fill=COLOR_ACCENT))
    data = d.add(Box(330, 205, 120, 44, label="data", fill=COLOR_ACCENT_LIGHT))
    rcv  = d.add(Box(330, 310, 120, 44, label="rcv", fill=COLOR_ACCENT_LIGHT))
    prg  = d.add(Box(95,  310, 120, 44, label="prg", fill=COLOR_ACCENT_LIGHT))
    d.add(Arrow((idle, "r"), (ready, "l"), label="ACMD41"))
    d.add(Arrow((ready, "r"), (ident, "l"), label="CMD2"))
    d.add(Arrow((ident, "r"), (stby, "l"), label="CMD3"))
    d.add(Arrow((stby, "b"), (tran, "t"), label="CMD7", label_side="right"))
    d.add(Arrow((tran.x, 216), (data.x + data.w, 216), label="CMD17, CMD18"))
    d.add(Arrow((data.x + data.w, 238), (tran.x, 238), label="end, CMD12", label_side="below"))
    d.add(Arrow((tran.x, 332), (rcv.x + rcv.w, 332), label="CMD24, CMD25"))
    d.add(Arrow((rcv, "l"), (prg, "r"), label="end, CMD12"))
    d.add(Arrow((prg, "b"), (tran.x + 40, tran.y + tran.h), via=[(prg.cx, 388), (tran.x + 40, 388)],
        label="programmed", label_pos=(390, 379)))
    return d
