#
# This file is part of LiteSDCard.
#
# Copyright (c) 2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# The SD bus: CLK from the host, CMD and DAT bidirectional, pull-ups on CMD and DAT.

from primer_helpers import *


def build():
    d = Diagram(CANVAS_WIDTH, 300)
    host = d.add(Box(30, 40, 160, 200, label="Host\n(FPGA)", fill=COLOR_ACCENT))
    card = d.add(Box(570, 40, 160, 200, label="Card", fill=COLOR_HARDWARE))
    y_clk, y_cmd, y_dat = 80, 140, 200
    d.add(Arrow((host.x + host.w, y_clk), (card.x, y_clk), kind="control", label="CLK",
        label_pos=(330, y_clk - 12)))
    d.add(Arrow((host.x + host.w, y_cmd), (card.x, y_cmd), kind="control", heads="both",
        label="CMD", label_pos=(330, y_cmd - 12)))
    d.add(Arrow((host.x + host.w, y_dat), (card.x, y_dat), kind="accent", heads="both",
        label="DAT0-3 (DAT0-7 on eMMC)", label_pos=(330, y_dat - 14)))
    pull = d.add(Box(420, 250, 120, 40, label="Pull-ups"))
    d.add(Bus([(480, pull.y), (480, y_cmd)], kind="control"))
    d.add(Mark(480, y_cmd, color=COLOR_STROKE, r=3))
    d.add(Mark(480, y_dat, color=COLOR_STROKE, r=3))
    return d
