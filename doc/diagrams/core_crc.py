#
# This file is part of LiteSDCard.
#
# Copyright (c) 2017-2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# CRC generators (litesdcard/crc.py): CRC7 over command bytes in SDCore, one bit-serial CRC16 per
# DAT line in the PHY data engines, read out MSB first by the count of the CRC16 state.

from svgdiag import *


def build():
    d = Diagram(CANVAS_WIDTH, 360)
    # Core: CRC7 on the command path.
    core = d.add(Container(10, 10, 740, 120, title="SDCore"))
    b0   = d.add(Box(30,  45, 160, 46, label="command bytes 0-4\nresponse bytes"))
    c7   = d.add(Box(290, 45, 160, 46, label="CRC7, 0x09", fill=COLOR_ACCENT))
    b5   = d.add(Box(550, 45, 160, 46, label="byte 5 / compare"))
    d.add(Arrow((b0, "r"), (c7, "l"), kind="data", label="8 bits/cycle", label_pos=(240, 56)))
    d.add(Arrow((c7, "r"), (b5, "l"), kind="data", label="crc[6:0]", label_pos=(500, 56)))

    # PHY: one CRC16 per DAT line.
    phy  = d.add(Container(10, 150, 740, 200, title="PHY data engines", title_pos="bl"))
    dat  = d.add(Box(30,  200, 160, 46, label="DAT0 to DAT7", stack=3))
    c16  = d.add(Box(290, 200, 160, 46, label="CRC16, 0x1021", stack=3, fill=COLOR_ACCENT))
    ser  = d.add(Box(550, 200, 160, 46, label="bit 15 first"))
    out  = d.add(Box(550, 290, 160, 40, label="DAT out / compare", fill=COLOR_ACCENT_LIGHT))
    d.add(Arrow((dat, "r"), (c16, "l"), label="1 bit/line", label_pos=(240, 211)))
    d.add(Arrow((c16, "r"), (ser, "l"), label="16 bits", label_pos=(500, 211)))
    d.add(Arrow((ser, "b"), (out, "t"), label="16 clocks", label_pos=(640, 268), label_anchor="start"))
    return d
