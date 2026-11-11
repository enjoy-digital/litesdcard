#
# This file is part of LiteSDCard.
#
# Copyright (c) 2017-2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# Core registers: fields of cmd_command, cmd_event and data_event (litesdcard/core.py).

from svgdiag import *


def row(d, x, y, title, cells, h=40):
    """One register: name on the left, adjoining cells (width, label, fill, msb, lsb), MSB first."""
    d.add(Text(x - 12, y + h/2, title, size=14, anchor="end"))
    for w, label, fill, msb, lsb in cells:
        d.add(Box(x, y, w, h, label=label, radius=0, fill=fill, size=14))
        bits = f"{msb}" if msb == lsb else f"{msb}:{lsb}"
        d.add(Text(x + w/2, y - 9, bits, size=12))
        x += w


def build():
    d = Diagram(CANVAS_WIDTH, 300)
    x0 = 150
    # cmd_command: cmd [13:8], data_type [6:5], crc [2], cmd_type [1:0], bits 31:14 reserved.
    row(d, x0, 30, "cmd_command", [
        (70,  "",          COLOR_SHADE,  31, 14),
        (150, "cmd",       COLOR_ACCENT, 13, 8),
        (30,  "",          COLOR_SHADE,  7,  7),
        (110, "data_type", COLOR_ACCENT, 6,  5),
        (60,  "",          COLOR_SHADE,  4,  3),
        (60,  "crc",       COLOR_ACCENT, 2,  2),
        (110, "cmd_type",  COLOR_ACCENT, 1,  0),
    ])
    # cmd_event: crc and error are never set by the core (shaded).
    row(d, x0, 130, "cmd_event", [
        (150, "crc",       COLOR_ACCENT, 3, 3),
        (150, "timeout",   COLOR_ACCENT, 2, 2),
        (150, "error",     COLOR_ACCENT, 1, 1),
        (140, "done",      COLOR_ACCENT, 0, 0),
    ])
    row(d, x0, 230, "data_event", [
        (150, "crc",       COLOR_ACCENT, 3, 3),
        (150, "timeout",   COLOR_ACCENT, 2, 2),
        (150, "error",     COLOR_ACCENT, 1, 1),
        (140, "done",      COLOR_ACCENT, 0, 0),
    ])
    return d
