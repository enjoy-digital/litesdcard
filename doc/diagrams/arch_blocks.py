#
# This file is part of LiteSDCard.
#
# Copyright (c) 2017-2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# Blocks of LiteSDCard as add_sdcard builds them: card, SDPHY (IO, clocker, engines), SDCore,
# block2mem and mem2block DMAs, the DMA bus; registers on the CSR bus.

from svgdiag import *


def build():
    d = Diagram(CANVAS_WIDTH, 350)
    # Registers.
    d.add(Text(15, 40, "CSR bus", size=13, anchor="start"))
    d.add(Bus([(70, 40), (590, 40)]))
    # Card.
    card = d.add(Box(15, 160, 70, 110, label="Card", fill=COLOR_HARDWARE))
    # PHY.
    d.add(Container(115, 80, 255, 255, title="SDPHY", title_pos="br"))
    io   = d.add(Box(135, 160, 60, 110, label="IO", fill=COLOR_ACCENT_LIGHT))
    eng  = d.add(Box(220, 120, 130, 90, label="Init, command\nand data\nengines", fill=COLOR_ACCENT))
    clk  = d.add(Box(220, 235, 130, 46, label="Clocker", fill=COLOR_ACCENT_LIGHT))
    # Core and DMAs.
    core = d.add(Box(400, 160, 100, 110, label="SDCore", fill=COLOR_ACCENT))
    b2m  = d.add(Box(530, 150, 115, 46, label="block2mem", fill=COLOR_ACCENT_LIGHT))
    m2b  = d.add(Box(530, 235, 115, 46, label="mem2block", fill=COLOR_ACCENT_LIGHT))
    bus  = d.add(Box(675, 120, 70, 190, label="DMA\nbus", fill=COLOR_HARDWARE))
    # Pins.
    d.add(Arrow((card, "r"), (io, "l"), kind="data", heads="both"))
    d.add(Arrow((io.x + io.w, 185), (eng.x, 185), kind="data", heads="both"))
    d.add(Arrow((clk, "l"), (io.x + io.w, clk.cy)))
    d.add(Arrow((265, eng.y + eng.h), (265, clk.y), heads="both", label="ce, stop",
        label_pos=(275, 222), label_anchor="start"))
    # Streams.
    d.add(Arrow((core.x, 172), (eng.x + eng.w, 172), kind="data"))
    d.add(Arrow((eng.x + eng.w, 198), (core.x, 198), kind="data"))
    d.add(Arrow((core.x + core.w, b2m.cy), (b2m, "l"), kind="data"))
    d.add(Arrow((m2b, "l"), (core.x + core.w, m2b.cy), kind="data"))
    d.add(Arrow((b2m, "r"), (bus.x, b2m.cy), kind="data"))
    d.add(Arrow((bus.x, m2b.cy), (m2b, "r"), kind="data"))
    # Register access.
    d.add(Arrow((240, 40), (240, 80)))
    d.add(Arrow((450, 40), (core, "t")))
    d.add(Arrow((590, 40), (b2m, "t", 0.52)))
    return d
