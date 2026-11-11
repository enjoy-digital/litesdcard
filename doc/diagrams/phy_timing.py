#
# This file is part of LiteSDCard.
#
# Copyright (c) 2017-2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# Card clock, CMD output and input sampling at the pins, divider 4 (card clock = sys clock / 4).
# Levels are those of a Migen simulation of SDPHY sending one command byte (SDPHYCMDW), with the
# IO registers of SDROutput/SDRTristate: the card clock rises one sys cycle after ce, CMD changes
# one sys cycle after the card clock rising edge, and the input register samples CMD/DAT at the
# sys clock edge that drives the card clock high (data_i_ce marks that cycle).

from svgdiag import *

X0, P = 160, 32         # Left edge of cycle 0, width of one sys clock cycle.
N     = 18              # Cycles shown.
H     = 22              # Wave height.


def x(n):
    return X0 + n*P


def wave(d, y, levels):
    """Square wave, one level per sys cycle (1 = high), top at y."""
    pts = []
    for n, v in enumerate(levels):
        yy = y if v else y + H
        if pts and pts[-1][1] != yy:
            pts.append((x(n), yy))
        elif not pts:
            pts.append((x(n), yy))
        pts.append((x(n + 1), yy))
    d.add(Bus(pts, kind="data"))


def pulses(d, y, cycles):
    wave(d, y, [1 if n in cycles else 0 for n in range(N)])


def name(d, y, label):
    d.add(Text(X0 - 14, y + H/2, label, size=13, anchor="end"))


def build():
    d = Diagram(CANVAS_WIDTH, 330)
    rows = {"sys": 40, "ce": 85, "clk": 130, "cmd": 175, "ice": 225}
    # sys clock: two half cycles per cycle.
    pts = []
    for n in range(N):
        pts += [(x(n), rows["sys"] + H), (x(n), rows["sys"]), (x(n) + P/2, rows["sys"]),
                (x(n) + P/2, rows["sys"] + H)]
    pts.append((x(N), rows["sys"] + H))
    d.add(Bus(pts, kind="data"))
    name(d, rows["sys"], "sys clock")
    name(d, rows["ce"],  "ce")
    pulses(d, rows["ce"], {3, 7, 11, 15})
    name(d, rows["clk"], "card clock")
    wave(d, rows["clk"], [1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1])
    name(d, rows["cmd"], "CMD out")
    d.add(Box(x(0), rows["cmd"], P, H, radius=0, fill=COLOR_SHADE))
    for i, b in enumerate(("bit 7", "bit 6", "bit 5", "bit 4")):
        d.add(Box(x(1 + 4*i), rows["cmd"], 4*P, H, label=b, radius=0, size=13,
            fill=COLOR_ACCENT if i % 2 == 0 else COLOR_ACCENT_LIGHT))
    d.add(Box(x(17), rows["cmd"], P, H, radius=0, fill=COLOR_ACCENT))
    name(d, rows["ice"], "data_i_ce")
    pulses(d, rows["ice"], {4, 8, 12, 16})
    # Card clock rising edges: the input register samples there, CMD changes one cycle later.
    for n in (4, 8, 12, 16):
        d.add(Bus([(x(n), rows["clk"] - 8), (x(n), rows["ice"] + H + 12)], dash="1,3",
            color=COLOR_CYAN))
    d.add(Text(x(4), rows["ice"] + H + 26, "sample", size=12))
    d.add(Text(x(8), rows["ice"] + H + 26, "sample", size=12))
    d.add(Arrow((x(4), 300), (x(5), 300), heads="both"))
    d.add(Text(x(5) + 8, 300, "1 sys cycle: CMD changes", size=12, anchor="start"))
    return d
