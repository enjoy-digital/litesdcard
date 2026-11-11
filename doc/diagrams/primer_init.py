#
# This file is part of LiteSDCard.
#
# Copyright (c) 2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# Initialization of an SD card by the BIOS driver (sdcard_init() of liblitesdcard): commands on
# the host lane, responses on the card lane, card state after each step on the right.

from primer_helpers import *

# (command label, response label or None, state after the step or None, note on the left or None)
STEPS = [
    ("80 clocks, CMD0",   None,               "idle",  "card clock 400 kHz"),
    ("CMD8 0x1aa",        "R7 echo",          "idle",  None),
    ("CMD55, ACMD41 (repeat)", "R3 OCR",      "ready", None),
    ("CMD2",              "R2 CID",           "ident", None),
    ("CMD3",              "R6 RCA",           "stby",  None),
    ("CMD10, CMD9",       "R2 CID, CSD",      "stby",  "card clock 25 MHz"),
    ("CMD7 RCA",          "R1b",              "tran",  None),
    ("CMD6 high speed",   "R1, status block", "tran",  None),
    ("CMD55, ACMD51",     "R1, SCR",          "tran",  None),
    ("CMD55, ACMD6",      "R1",               "tran",  "4-bit bus"),
    ("CMD16 512",         "R1",               "tran",  None),
]


def build():
    xh, xc, y0, dy = 230, 530, 50, 46
    d = Diagram(CANVAS_WIDTH, y0 + len(STEPS)*dy + 20)
    lanes(d, [xh, xc], y0, y0 + len(STEPS)*dy + 5, ["Host", "Card"])
    for i, (cmd, rsp, state, note) in enumerate(STEPS):
        y = y0 + 18 + i*dy
        d.add(Arrow((xh, y), (xc, y), kind="control", label=cmd))
        if rsp:
            d.add(Arrow((xc, y + 18), (xh, y + 18), kind="feedback", label=rsp, label_side="below",
                label_pos=((xh + xc)/2, y + 18 - 7)))
        if state:
            d.add(Text(xc + 20, y + 9, state, size=13, anchor="start", italic=True))
        if note:
            d.add(Text(xh - 20, y + 9, note, size=13, anchor="end"))
    return d
