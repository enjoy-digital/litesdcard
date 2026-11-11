#
# This file is part of LiteSDCard.
#
# Copyright (c) 2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# The software around LiteSDCard, all in LiteX or upstream Linux: BIOS commands and boot over the
# BIOS driver; the Linux driver configured by the generated device tree; both on the registers.

from svgdiag import *


def build():
    d = Diagram(CANVAS_WIDTH, 380)
    d.add(Container(15, 15, 360, 200, title="LiteX BIOS", title_pos="bl"))
    cmds = d.add(Box(35, 40, 150, 50, label="Commands\nsdcard_*"))
    boot = d.add(Box(205, 40, 150, 50, label="sdcardboot\nFatFs"))
    lib  = d.add(Box(35, 120, 320, 44, label="liblitesdcard", fill=COLOR_ACCENT_LIGHT))
    d.add(Container(395, 15, 350, 200, title="Linux", title_pos="bl"))
    drv  = d.add(Box(415, 40, 140, 50, label="litex_mmc\ndriver", fill=COLOR_ACCENT_LIGHT))
    dt   = d.add(Box(585, 40, 140, 50, label="Device tree\nlitex,mmc"))
    gen  = d.add(Box(585, 140, 140, 44, label="csr.json"))
    regs = d.add(Box(15, 245, 730, 40, label="Registers of the PHY, the core and the DMAs", fill=COLOR_ACCENT))
    hw   = d.add(Box(15, 315, 730, 44, label="LiteSDCard gateware", fill=COLOR_ACCENT))
    d.add(Arrow((cmds, "b"), (cmds.cx, lib.y), kind="control"))
    d.add(Arrow((boot, "b"), (boot.cx, lib.y), kind="control"))
    d.add(Arrow((lib, "b"), (lib.cx, regs.y), kind="control", heads="both"))
    d.add(Arrow((drv, "b"), (drv.cx, regs.y), kind="control", heads="both"))
    d.add(Arrow((dt, "l"), (drv, "r"), kind="control"))
    d.add(Arrow((gen, "t"), (dt, "b"), kind="feedback", label="litex_json2dts_linux",
        label_pos=(647, 115), label_anchor="end"))
    d.add(Arrow((regs, "b"), (hw, "t"), kind="data", heads="both"))
    return d
