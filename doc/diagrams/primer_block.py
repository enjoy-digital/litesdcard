#
# This file is part of LiteSDCard.
#
# Copyright (c) 2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# A 512-byte block on the 4-bit bus: start bit, two clocks per byte (high nibble first, DAT3 =
# bit 7), one CRC16 per line, end bit (SDPHYDATAW SD_PHY_SPEED_4X order).

from primer_helpers import *


def build():
    d = Diagram(CANVAS_WIDTH, 250)
    x0, y0, dy = 90, 70, 38
    widths = [36, 40, 40, 40, 40, 200, 150, 36]
    xs = [x0 + sum(widths[:i]) for i in range(len(widths) + 1)]
    heads = [(0, 1, "Start"), (1, 3, "Byte 0"), (3, 5, "Byte 1"), (5, 6, "Bytes 2 to 511"),
             (6, 7, "CRC16 of the line"), (7, 8, "End")]
    for a, b, label in heads:
        d.add(Text((xs[a] + xs[b])/2, y0 - 32, label, size=12))
    for i, (line, hi, lo) in enumerate([("DAT3", 7, 3), ("DAT2", 6, 2), ("DAT1", 5, 1), ("DAT0", 4, 0)]):
        y = y0 + i*dy
        row_name(d, x0, y, line)
        cells(d, x0, y, [
            (widths[0], "0",            COLOR_FILL),
            (widths[1], str(hi),        COLOR_ACCENT),
            (widths[2], str(lo),        COLOR_ACCENT),
            (widths[3], str(hi),        COLOR_ACCENT),
            (widths[4], str(lo),        COLOR_ACCENT),
            (widths[5], f"bits {hi} and {lo}", COLOR_ACCENT),
            (widths[6], "CRC16",        COLOR_ACCENT_LIGHT),
            (widths[7], "1",            COLOR_FILL),
        ], h=30)
    yb = y0 + 3*dy + 45
    span(d, xs[1], xs[6], yb, "1024 clocks", side="below")
    span(d, xs[6], xs[7], yb, "16 clocks", side="below")
    return d
