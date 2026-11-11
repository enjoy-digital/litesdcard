#
# This file is part of LiteSDCard.
#
# Copyright (c) 2017-2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# SDPHYDATAR state machine (litesdcard/phy.py): IDLE, WAIT, DATA, CLK8, TIMEOUT, one pass per
# block. The timeout counter is loaded in IDLE for each block and counts down in WAIT and DATA.

from svgdiag import *


def state(d, x, y, label, fill=COLOR_FILL):
    return d.add(Box(x, y, 125, 46, label=label, fill=fill))


def build():
    d = Diagram(CANVAS_WIDTH, 340)
    idle = state(d, 15,  140, "IDLE", fill=COLOR_ACCENT_LIGHT)
    wait = state(d, 215, 140, "WAIT", fill=COLOR_ACCENT)
    data = state(d, 415, 140, "DATA", fill=COLOR_ACCENT)
    clk8 = state(d, 615, 140, "CLK8")
    tmo  = state(d, 315, 270, "TIMEOUT")
    d.add(Arrow((idle, "r"), (wait, "l"), label="block\nrequested", label_pos=(177, 144)))
    d.add(Arrow((wait, "r"), (data, "l"), label="start bit", label_pos=(377, 151)))
    d.add(Arrow((data, "r"), (clk8, "l"), label="last block", label_pos=(577, 151)))
    d.add(Arrow((477, data.y), (85, idle.y), via=[(477, 90), (85, 90)],
        label="block and CRC done, more blocks", label_pos=(280, 80)))
    d.add(Arrow((677, clk8.y), (45, idle.y), via=[(677, 35), (45, 35)], label="8 clocks",
        label_pos=(360, 25)))
    d.add(Arrow((330, wait.y + wait.h), (330, tmo.y)))
    d.add(Arrow((430, data.y + data.h), (430, tmo.y)))
    d.add(Text(380, 233, "timeout", size=12))
    d.add(Arrow((tmo, "l"), (77, idle.y + idle.h), via=[(77, tmo.cy)], label="status TIMEOUT",
        label_pos=(195, tmo.cy - 11)))
    return d
