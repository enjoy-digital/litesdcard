#
# This file is part of LiteSDCard.
#
# Copyright (c) 2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# Two ways to end a multiple-block read: CMD18 then CMD12 (open-ended), or CMD23 then CMD18
# (pre-defined count, the card stops by itself).

from primer_helpers import *

HOST, CARD = COLOR_ACCENT, COLOR_HARDWARE


def blocks(d, x, y, n, w=90, gap=10):
    for i in range(n):
        cells(d, x + i*(w + gap), y, [(w, f"block {i}", CARD)], h=28)


def build():
    d = Diagram(CANVAS_WIDTH, 265)
    x0 = 110
    # Open-ended: CMD18 ... CMD12.
    d.add(Text(20, 22, "Open-ended", size=FONT_SIZE, bold=True, anchor="start"))
    row_name(d, x0, 60, "CMD")
    cells(d, x0, 60, [(70, "CMD18", HOST), (10, "", None), (50, "R1", CARD)], h=28)
    cells(d, x0 + 435, 60, [(70, "CMD12", HOST), (6, "", None), (50, "R1b", CARD)], h=28)
    row_name(d, x0, 100, "DAT")
    blocks(d, x0 + 140, 100, 3)
    level(d, x0 + 130, x0 + 435, 60)
    # Pre-defined count: CMD23, CMD18.
    d.add(Text(20, 162, "Pre-defined count", size=FONT_SIZE, bold=True, anchor="start"))
    row_name(d, x0, 200, "CMD")
    cells(d, x0, 200, [(70, "CMD23", HOST), (10, "", None), (50, "R1", CARD), (10, "", None),
                       (70, "CMD18", HOST), (10, "", None), (50, "R1", CARD)], h=28)
    row_name(d, x0, 240, "DAT")
    blocks(d, x0 + 280, 240, 3)
    level(d, x0 + 270, 740, 200)
    return d
