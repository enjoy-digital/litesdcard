#
# This file is part of LiteSDCard.
#
# Copyright (c) 2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# A single-block write: CMD24 and R1 on CMD, the block on DAT, then the CRC status token and the
# busy of the card on DAT0 (SDPHYDATAW states DATA, CRC16, STOP, CRC, BUSY).

from primer_helpers import *

HOST, CARD = COLOR_ACCENT, COLOR_HARDWARE


def build():
    d = Diagram(CANVAS_WIDTH, 180)
    x0, y_cmd, y_dat = 90, 50, 110
    row_name(d, x0, y_cmd, "CMD")
    cells(d, x0, y_cmd, [(100, "CMD24", HOST), (20, "", None), (100, "R1", CARD)], h=30)
    row_name(d, x0, y_dat, "DAT0")
    xd = x0 + 230
    cells(d, xd, y_dat, [
        (24, "0", HOST), (110, "data", HOST), (64, "CRC16", HOST), (24, "1", HOST),
        (16, "", None), (76, "token 010", CARD), (96, "busy", CARD),
    ], h=30)
    level(d, x0, xd, y_dat)
    level(d, xd + 410, 750, y_dat)
    level(d, xd + 222, xd + 238, y_dat)
    level(d, x0 + 100, x0 + 120, y_cmd)
    level(d, x0 + 220, 740, y_cmd)
    d.add(Box(x0, 150, 20, 16, radius=0, fill=HOST))
    d.add(Text(x0 + 28, 158, "host drives", size=12, anchor="start"))
    d.add(Box(x0 + 140, 150, 20, 16, radius=0, fill=CARD))
    d.add(Text(x0 + 168, 158, "card drives", size=12, anchor="start"))
    return d
