#
# This file is part of LiteSDCard.
#
# Copyright (c) 2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# What add_sdcard builds in a LiteX SoC: the PHY on the platform pads (or the emulator), the core,
# the two DMAs as bus masters on the DMA bus (or the main bus) and the event manager with its IRQ
# (sources: card detect of the PHY, done of the core, done of each DMA).

from svgdiag import *


def build():
    d = Diagram(CANVAS_WIDTH, 345)
    cpu  = d.add(Box(15, 132.5, 90, 50, label="CPU"))
    bus  = d.add(Box(135, 30, 85, 255, label="Main or\nDMA bus"))
    d.add(Container(245, 15, 395, 300, title="add_sdcard"))
    b2m  = d.add(Box(262, 40, 110, 44, label="block2mem", fill=COLOR_ACCENT_LIGHT))
    m2b  = d.add(Box(262, 125, 110, 44, label="mem2block", fill=COLOR_ACCENT_LIGHT))
    ev   = d.add(Box(262, 215, 110, 44, label="Events (ev)"))
    core = d.add(Box(400, 82, 90, 44, label="SDCore", fill=COLOR_ACCENT))
    phy  = d.add(Box(520, 82, 90, 44, label="SDPHY", fill=COLOR_ACCENT))
    pads = d.add(Box(668, 70, 82, 68, label="sdcard\npads", fill=COLOR_HARDWARE))
    d.add(Arrow((cpu, "r"), (bus, "l", 0.5), kind="control", heads="both"))
    d.add(Arrow((b2m, "l"), (bus, "r", 0.163), kind="data"))
    d.add(Arrow((bus, "r", 0.496), (m2b, "l"), kind="data"))
    d.add(Arrow((core, "l", 0.3), (b2m, "r"), via=[(386, 95.2), (386, 62)], kind="data"))
    d.add(Arrow((m2b, "r"), (core, "l", 0.7), via=[(386, 147), (386, 112.8)], kind="data"))
    d.add(Arrow((core, "r"), (phy, "l"), kind="data", heads="both"))
    d.add(Arrow((phy, "r"), (pads, "l", 0.5), kind="accent", heads="both"))
    d.add(Arrow((core, "b"), (ev, "r", 0.3), kind="control"))
    d.add(Arrow((m2b, "b"), (ev, "t"), kind="control", label="done", label_pos=(340, 194)))
    d.add(Arrow((b2m, "l", 0.85), (ev, "l", 0.5), via=[(251, 77.4), (251, 237)], kind="control"))
    d.add(Arrow((phy, "b"), (ev, "r", 0.75), kind="control", label="card detect",
        label_pos=(565, 237)))
    d.add(Arrow((ev, "b"), (cpu, "b"), via=[(317, 325), (60, 325)], kind="control", label="IRQ",
        label_pos=(190, 315)))
    return d
