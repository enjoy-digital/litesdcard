#
# This file is part of LiteSDCard.
#
# Copyright (c) 2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# Response layouts: R1 (index, card status, CRC7), R3 (OCR, ones instead of index and CRC), R2
# (136 bits, CID or CSD with its own CRC7).

from primer_helpers import *


def build():
    d = Diagram(CANVAS_WIDTH, 200)
    x0 = 110
    d.add(Text(x0 + 20, 22, "Start", size=12))
    d.add(Text(x0 + 60, 22, "Dir", size=12))
    row_name(d, x0, 55, "R1")
    cells(d, x0, 55, [
        (40, "0", COLOR_FILL), (40, "0", COLOR_FILL), (100, "Index", COLOR_ACCENT),
        (270, "Card status (32 bits)", COLOR_ACCENT), (100, "CRC7", COLOR_ACCENT_LIGHT),
        (40, "1", COLOR_FILL),
    ], h=30)
    row_name(d, x0, 115, "R3")
    cells(d, x0, 115, [
        (40, "0", COLOR_FILL), (40, "0", COLOR_FILL), (100, "111111", COLOR_SHADE),
        (270, "OCR (32 bits)", COLOR_ACCENT), (100, "1111111", COLOR_SHADE),
        (40, "1", COLOR_FILL),
    ], h=30)
    row_name(d, x0, 175, "R2")
    cells(d, x0, 175, [
        (40, "0", COLOR_FILL), (40, "0", COLOR_FILL), (100, "111111", COLOR_SHADE),
        (310, "CID or CSD, bits 127 to 8", COLOR_ACCENT), (100, "CRC7", COLOR_ACCENT_LIGHT),
        (40, "1", COLOR_FILL),
    ], h=30)
    return d
