#
# This file is part of LiteSDCard.
#
# Copyright (c) 2017-2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# A single block read (CMD17) end to end, as the BIOS driver runs it: register writes, the command
# and its response, the data block, the done events. Lanes: software, block2mem, SDCore, SDPHY, card.

from svgdiag import *

LANES = [("Software", 70, COLOR_FILL), ("block2mem", 220, COLOR_ACCENT_LIGHT),
         ("SDCore", 370, COLOR_ACCENT), ("SDPHY", 520, COLOR_ACCENT_LIGHT),
         ("Card", 670, COLOR_HARDWARE)]

MSGS = [
    (0, 1, "base, length, enable",   "control"),
    (0, 2, "block length and count", "control"),
    (0, 2, "argument and command",   "control"),
    (0, 2, "cmd_send",               "control"),
    (2, 3, "6 command bytes",        "data"),
    (3, 4, "CMD17 on CMD",           "data"),
    (4, 3, "R1 on CMD",              "data"),
    (3, 2, "6 response bytes",       "data"),
    (2, 0, "cmd_event done",         "control"),
    (4, 3, "block on DAT",           "accent"),
    (3, 2, "512 bytes + CRC (drop)", "accent"),
    (2, 1, "512 bytes",              "accent"),
    (2, 0, "data_event done",        "control"),
    (1, 0, "DMA done",               "control"),
]


def build():
    top, row, bw = 15, 38, 120
    y0     = top + 46 + 30
    bottom = y0 + row*(len(MSGS) - 1) + 20
    d = Diagram(CANVAS_WIDTH, bottom + 10)
    for name, x, fill in LANES:
        d.add(Box(x - bw/2, top, bw, 46, label=name, fill=fill))
        d.add(Bus([(x, top + 46), (x, bottom)], dash="4,3"))
    for n, (a, b, label, kind) in enumerate(MSGS):
        y  = y0 + n*row
        xa, xb = LANES[a][1], LANES[b][1]
        # Labels of arrows spanning several lanes sit between the lanes nearest the destination.
        xl = (xb + LANES[b + (1 if a > b else -1)][1])/2
        d.add(Arrow((xa, y), (xb, y), kind=kind, label=label, label_pos=(xl, y - 12),
            label_size=13))
    return d
