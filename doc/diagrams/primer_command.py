#
# This file is part of LiteSDCard.
#
# Copyright (c) 2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# The 48-bit command frame: start, transmission, index, argument, CRC7, end; example CMD17.

from primer_helpers import *


def build():
    d = Diagram(CANVAS_WIDTH, 130)
    x0 = 120
    # (width, label, fill, msb, lsb)
    fields = [
        (40,  "Start",    COLOR_FILL,         47, 47),
        (40,  "Dir",      COLOR_FILL,         46, 46),
        (110, "Index",    COLOR_ACCENT,       45, 40),
        (250, "Argument", COLOR_ACCENT,       39, 8),
        (110, "CRC7",     COLOR_ACCENT_LIGHT, 7,  1),
        (40,  "End",      COLOR_FILL,         0,  0),
    ]
    row_name(d, x0, 50, "Field")
    cells(d, x0, 50, [(w, l, f) for w, l, f, _, _ in fields], h=30)
    x, bits = x0, []
    for w, _, _, msb, lsb in fields:
        bits.append((x, x + w, msb, lsb))
        x += w
    field_bits(d, 0, 22, bits)
    row_name(d, x0, 100, "CMD17")
    cells(d, x0, 100, [
        (40,  "0",             COLOR_FILL),
        (40,  "1",             COLOR_FILL),
        (110, "17",            COLOR_FILL),
        (250, "Data address", COLOR_FILL),
        (110, "CRC7",          COLOR_FILL),
        (40,  "1",             COLOR_FILL),
    ], h=30)
    return d
