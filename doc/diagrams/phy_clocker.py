#
# This file is part of LiteSDCard.
#
# Copyright (c) 2017-2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# SDPHYClocker (litesdcard/phy.py): the divider register sets the half period of a down-counter
# that toggles clk; ce marks its rising edge for the engines; stop freezes the counter; the
# engines' clock request goes through an enable latch to gate the clock, which leaves through an
# IO register.

from svgdiag import *


def build():
    d = Diagram(CANVAS_WIDTH, 280)
    div   = d.add(Box(15,  60,  120, 46, label="divider\nregister", fill=COLOR_ACCENT_LIGHT))
    cnt   = d.add(Box(185, 60,  140, 46, label="Half-period\ncounter", fill=COLOR_ACCENT))
    edge  = d.add(Box(375, 60,  130, 46, label="Rising edge\ndetect"))
    eng   = d.add(Box(575, 50,  170, 110, label="Init, command\nand data\nengines"))
    latch = d.add(Box(185, 215, 140, 46, label="Enable latch", fill=COLOR_ACCENT))
    gate  = d.add(Box(375, 215, 130, 46, label="Clock gate"))
    ioreg = d.add(Box(575, 215, 110, 46, label="IO register", fill=COLOR_ACCENT_LIGHT))
    d.add(Arrow((div, "r"), (cnt, "l")))
    d.add(Arrow((cnt, "r"), (edge, "l"), label="clk", label_pos=(350, 71)))
    d.add(Arrow((edge, "r"), (eng.x, edge.cy), label="ce", label_pos=(540, 71)))
    d.add(Arrow((660, eng.y), (255, cnt.y), via=[(660, 25), (255, 25)], label="stop",
        label_pos=(457, 14)))
    d.add(Arrow((300, cnt.y + cnt.h), (440, gate.y), via=[(300, 160), (440, 160)], label="clk",
        label_pos=(350, 150)))
    d.add(Arrow((620, eng.y + eng.h), (255, latch.y), via=[(620, 190), (255, 190)],
        label="clock request", label_pos=(530, 180)))
    d.add(Arrow((latch, "r"), (gate, "l"), label="enable", label_pos=(350, 226)))
    d.add(Arrow((gate, "r"), (ioreg, "l")))
    d.add(Arrow((ioreg, "r"), (745, ioreg.cy), label="card\nclock", label_pos=(716, 212)))
    return d
