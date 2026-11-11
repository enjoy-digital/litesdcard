#
# This file is part of LiteSDCard.
#
# Copyright (c) 2017-2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# SDPHYCMDR state machine (litesdcard/phy.py): IDLE, WAIT, CMD, CLK8, BUSY, TIMEOUT. The timeout
# counter is loaded in IDLE and counts down in WAIT, CMD and BUSY.

from svgdiag import *


def state(d, x, y, label, fill=COLOR_FILL):
    return d.add(Box(x, y, 120, 46, label=label, fill=fill))


def build():
    d = Diagram(CANVAS_WIDTH, 400)
    idle = state(d, 15,  150, "IDLE", fill=COLOR_ACCENT_LIGHT)
    wait = state(d, 210, 150, "WAIT", fill=COLOR_ACCENT)
    cmd  = state(d, 405, 150, "CMD",  fill=COLOR_ACCENT)
    clk8 = state(d, 600, 150, "CLK8")
    busy = state(d, 600, 290, "BUSY")
    tmo  = state(d, 300, 290, "TIMEOUT")
    d.add(Arrow((idle, "r"), (wait, "l"), label="command\nsent", label_pos=(172, 154)))
    d.add(Arrow((wait, "r"), (cmd, "l"), label="start bit", label_pos=(367, 162)))
    d.add(Arrow((cmd, "r"), (clk8, "l"), label="R1b or\nno data", label_pos=(562, 154)))
    d.add(Arrow((465, cmd.y), (75, idle.y), via=[(465, 100), (75, 100)],
        label="last byte, data follows", label_pos=(270, 90)))
    d.add(Arrow((660, clk8.y), (40, idle.y), via=[(660, 45), (40, 45)],
        label="8 clocks, no busy", label_pos=(350, 35)))
    d.add(Arrow((clk8, "b"), (busy, "t"), label="R1b", label_pos=(668, 243), label_anchor="start"))
    d.add(Arrow((660, busy.y + busy.h), (75, idle.y + idle.h), via=[(660, 370), (75, 370)],
        label="DAT0 high", label_pos=(480, 382)))
    d.add(Arrow((310, wait.y + wait.h), (310, tmo.y)))
    d.add(Arrow((410, cmd.y + cmd.h), (410, tmo.y)))
    d.add(Text(360, 243, "timeout", size=12))
    d.add(Arrow((busy, "l"), (tmo, "r"), label="timeout", label_pos=(510, 301)))
    d.add(Arrow((tmo, "l"), (105, idle.y + idle.h), via=[(105, tmo.cy)],
        label="status TIMEOUT", label_pos=(200, 301)))
    return d
