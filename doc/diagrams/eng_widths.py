#
# This file is part of LiteSDCard.
#
# Copyright (c) 2017-2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# Bit order of one byte on the DAT lines (SDPHYDATAW cases, SDPHYR converter with reverse=True):
# 1-bit: bit 7 first on DAT0; 4-bit: bits 7..4 on DAT3..DAT0, then bits 3..0; 8-bit: bit n on
# DATn in one clock.

from svgdiag import *

CW, CH = 52, 26


def grid(d, x0, y0, title, lines, columns):
    """columns: list of lists of bit numbers, one list per clock, DAT lines from top (highest)."""
    d.add(Text(x0, y0 - 22, title, size=15, italic=True, anchor="start"))
    for r, line in enumerate(lines):
        d.add(Text(x0 - 10, y0 + r*CH + CH/2, line, size=13, anchor="end"))
    for c, bits in enumerate(columns):
        for r, b in enumerate(bits):
            fill = COLOR_ACCENT if b >= 4 else COLOR_ACCENT_LIGHT
            d.add(Box(x0 + c*CW, y0 + r*CH, CW, CH, label=f"b{b}", radius=0, size=13, fill=fill))
        d.add(Text(x0 + c*CW + CW/2, y0 + len(bits)*CH + 14, f"{c + 1}", size=12))


def build():
    d = Diagram(CANVAS_WIDTH, 395)
    grid(d, 120, 50, "1-bit", ["DAT0"], [[7 - i] for i in range(8)])
    d.add(Text(120 + 8*CW + 12, 50 + CH + 14, "clock", size=12, anchor="start"))
    grid(d, 120, 150, "4-bit", ["DAT3", "DAT2", "DAT1", "DAT0"], [[7, 6, 5, 4], [3, 2, 1, 0]])
    d.add(Text(120 + 2*CW + 12, 150 + 4*CH + 14, "clock", size=12, anchor="start"))
    grid(d, 470, 150, "8-bit", [f"DAT{7 - i}" for i in range(8)], [[7 - i for i in range(8)]])
    d.add(Text(470 + CW + 12, 150 + 8*CH + 14, "clock", size=12, anchor="start"))
    return d
