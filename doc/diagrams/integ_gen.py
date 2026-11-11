#
# This file is part of LiteSDCard.
#
# Copyright (c) 2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# Ports of the standalone core made by litesdcard_gen: a Wishbone slave for the registers, a
# Wishbone master for the DMAs, an interrupt output and the SD card pads.

from svgdiag import *


def build():
    d = Diagram(CANVAS_WIDTH, 270)
    cpu  = d.add(Box(15, 30, 130, 50, label="Host CPU"))
    mem  = d.add(Box(15, 110, 130, 50, label="Memory"))
    irqc = d.add(Box(15, 190, 130, 50, label="Interrupt\ncontroller"))
    d.add(Container(240, 15, 300, 240, title="litesdcard_core.v"))
    core = d.add(Box(290, 95, 200, 80, label="LiteSDCard\n(add_sdcard)", fill=COLOR_ACCENT))
    card = d.add(Box(640, 101, 105, 68, label="SD card", fill=COLOR_HARDWARE))
    d.add(Arrow((cpu, "r"), (core, "l", 0.15), via=[(260, 55), (260, 107)], kind="control",
        label="wb_ctrl", label_pos=(195, 45)))
    d.add(Arrow((core, "l", 0.5), (mem, "r"), kind="data",
        label="wb_dma", label_pos=(195, 125)))
    d.add(Arrow((core, "l", 0.85), (irqc, "r"), via=[(260, 163), (260, 215)], kind="control",
        label="irq", label_pos=(195, 205)))
    d.add(Arrow((core, "r"), (card, "l"), kind="accent", heads="both", label="sdcard_*",
        label_pos=(590, 125)))
    return d
