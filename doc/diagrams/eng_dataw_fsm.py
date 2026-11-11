#
# This file is part of LiteSDCard.
#
# Copyright (c) 2017-2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# SDPHYDATAW state machine (litesdcard/phy.py), one block: CLK2, START, DATA, CRC16, STOP, CRC
# (status token), CLK8 after the last block, BUSY. IDLE is left out: the entry and exit arrows
# stand for it. CRC and BUSY share the write timeout, which leads to TIMEOUT.

from svgdiag import *


def state(d, x, y, label, fill=COLOR_FILL):
    return d.add(Box(x, y, 125, 46, label=label, fill=fill))


def build():
    d = Diagram(CANVAS_WIDTH, 400)
    clk2  = state(d, 30,  80,  "CLK2")
    start = state(d, 215, 80,  "START")
    data  = state(d, 400, 80,  "DATA",   fill=COLOR_ACCENT)
    crc16 = state(d, 585, 80,  "CRC16",  fill=COLOR_ACCENT)
    stop  = state(d, 585, 210, "STOP")
    crc   = state(d, 400, 210, "CRC",    fill=COLOR_ACCENT_LIGHT)
    busy  = state(d, 190, 210, "BUSY",   fill=COLOR_ACCENT_LIGHT)
    clk8  = state(d, 400, 330, "CLK8")
    d.add(Arrow((92.5, 20), (clk2, "t"), label="from IDLE", label_pos=(102, 34), label_anchor="start"))
    d.add(Arrow((clk2, "r"), (start, "l"), label="2 clocks", label_pos=(185, 91)))
    d.add(Arrow((start, "r"), (data, "l"), label="1 clock", label_pos=(370, 91)))
    d.add(Arrow((data, "r"), (crc16, "l"), label="last byte", label_pos=(555, 91)))
    d.add(Arrow((crc16, "b"), (stop, "t"), label="16 clocks", label_pos=(656, 178),
        label_anchor="start"))
    d.add(Arrow((stop, "l"), (crc, "r"), label="1 clock", label_pos=(555, 221)))
    d.add(Arrow((crc, "l"), (busy, "r"), label="more blocks", label_pos=(358, 221)))
    d.add(Arrow((crc, "b"), (clk8, "t"), label="last block", label_pos=(452, 295),
        label_anchor="end"))
    d.add(Arrow((clk8, "l"), (290, busy.y + busy.h), via=[(290, clk8.cy)], label="8 clocks",
        label_pos=(345, clk8.cy - 11)))
    d.add(Arrow((busy, "l"), (60, clk2.y + clk2.h), via=[(60, busy.cy)],
        label="DAT0 high,\nmore blocks", label_pos=(120, 175)))
    d.add(Arrow((215, busy.y + busy.h), (215, 385), via=[], label="DAT0 high,\nlast block",
        label_pos=(205, 365), label_anchor="end"))
    tmo   = state(d, 600, 330, "TIMEOUT")
    d.add(Arrow((crc, "b", 0.9), (tmo, "t"), via=[(512.5, 296), (662.5, 296)], kind="feedback",
        label="write timeout (CRC, BUSY)", label_pos=(600, 286)))
    d.add(Arrow((tmo, "b"), (662.5, 395), label="to IDLE", label_pos=(672, 390), label_anchor="start"))
    return d
