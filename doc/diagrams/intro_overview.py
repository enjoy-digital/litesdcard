#
# This file is part of LiteSDCard.
#
# Copyright (c) 2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# LiteSDCard in a LiteX SoC: the CPU and the memory on the system bus, the two DMAs, the core,
# the PHY and the card. Redraws the outdated doc/architecture.png from the current code.

from svgdiag import *


def build():
    d = Diagram(CANVAS_WIDTH, 290)
    cpu = d.add(Box(20, 50, 100, 44, label="CPU"))
    ram = d.add(Box(20, 190, 100, 44, label="Main RAM"))
    bus = d.add(Box(150, 40, 70, 204, label="System\nbus"))
    d.add(Container(245, 20, 375, 255, title="LiteSDCard"))
    b2m = d.add(Box(262, 60, 115, 44, label="block2mem", fill=COLOR_ACCENT_LIGHT))
    m2b = d.add(Box(262, 180, 115, 44, label="mem2block", fill=COLOR_ACCENT_LIGHT))
    core = d.add(Box(400, 120, 85, 44, label="SDCore", fill=COLOR_ACCENT))
    phy = d.add(Box(510, 120, 85, 44, label="SDPHY", fill=COLOR_ACCENT))
    card = d.add(Box(668, 108, 80, 68, label="SD card\nor eMMC", fill=COLOR_HARDWARE))
    d.add(Arrow((cpu, "r"), (bus, "l", 0.157), kind="control", heads="both"))
    d.add(Arrow((ram, "r"), (bus, "l", 0.843), kind="data", heads="both"))
    d.add(Arrow((b2m, "l"), (bus, "r", 0.206), kind="data"))
    d.add(Arrow((bus, "r", 0.794), (m2b, "l"), kind="data"))
    d.add(Arrow((core, "l", 0.3), (b2m, "r"), kind="data"))
    d.add(Arrow((m2b, "r"), (core, "l", 0.7), kind="data"))
    d.add(Arrow((core, "r"), (phy, "l"), kind="data", heads="both"))
    d.add(Arrow((phy, "r"), (card, "l"), kind="accent", heads="both", label="SD bus", label_pos=(644, 130)))
    d.add(Arrow((bus, "r", 0.05), (core, "t"), via=[(core.cx, 50.2)], kind="control",
        label="registers (all blocks)", label_pos=(330, 39)))
    return d
