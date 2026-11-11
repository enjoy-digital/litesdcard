#
# This file is part of LiteSDCard.
#
# Copyright (c) 2020-2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# DMA frontends (litesdcard/frontend/dma.py): block2mem (core source to memory) and mem2block
# (memory to core sink), each a 512-byte FIFO, a width converter and a LiteX Wishbone DMA.

from svgdiag import *


def build():
    d = Diagram(CANVAS_WIDTH, 300)
    core = d.add(Box(10, 40, 100, 220, label="SDCore", fill=COLOR_ACCENT_LIGHT))
    mem  = d.add(Box(650, 40, 100, 220, label="Memory\n(bus)", fill=COLOR_HARDWARE))

    # block2mem: core source -> FIFO -> converter -> Wishbone DMA writer.
    rd = d.add(Container(130, 15, 500, 120, title="SDBlock2MemDMA", title_pos="tl"))
    f1 = d.add(Box(150, 70, 120, 46, label="FIFO 512 B"))
    c1 = d.add(Box(320, 70, 120, 46, label="8 to bus"))
    w1 = d.add(Box(490, 70, 120, 46, label="DMA writer", fill=COLOR_ACCENT))
    d.add(Arrow((core, "r", 53/220), (f1, "l"), kind="data"))
    d.add(Arrow((f1, "r"), (c1, "l"), kind="data"))
    d.add(Arrow((c1, "r"), (w1, "l"), kind="data"))
    d.add(Arrow((w1, "r"), (mem, "l", 53/220), kind="data"))

    # mem2block: Wishbone DMA reader -> converter -> FIFO -> core sink.
    wr = d.add(Container(130, 160, 500, 120, title="SDMem2BlockDMA", title_pos="bl"))
    w2 = d.add(Box(490, 180, 120, 46, label="DMA reader", fill=COLOR_ACCENT))
    c2 = d.add(Box(320, 180, 120, 46, label="bus to 8"))
    f2 = d.add(Box(150, 180, 120, 46, label="FIFO 512 B"))
    d.add(Arrow((mem, "l", 163/220), (w2, "r"), kind="data"))
    d.add(Arrow((w2, "l"), (c2, "r"), kind="data"))
    d.add(Arrow((c2, "l"), (f2, "r"), kind="data"))
    d.add(Arrow((f2, "l"), (core, "r", 163/220), kind="data"))
    return d
