#
# This file is part of LiteSDCard.
#
# Copyright (c) 2017-2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# SDPHYIOGen (litesdcard/phy.py) for CMD and DAT: the ORed engine outputs go through SDRTristate
# (output, output-enable and input registers in the sys domain around a tristate buffer, as LiteX
# lowers it per family); the optional direction pins of a level shifter are registered copies of
# the output enables.

from svgdiag import *


def build():
    d = Diagram(CANVAS_WIDTH, 345)
    eng  = d.add(Box(15, 50, 125, 210, label="Init block and\nengines, ORed", fill=COLOR_ACCENT_LIGHT))
    d.add(Container(180, 25, 345, 255, title="SDRTristate", title_pos="br"))
    oreg = d.add(Box(200, 60, 120, 44, label="Output reg"))
    ereg = d.add(Box(200, 130, 120, 44, label="Enable reg"))
    ireg = d.add(Box(200, 200, 120, 44, label="Input reg"))
    buf  = d.add(Box(380, 60, 120, 184, label="Tristate\nbuffer", fill=COLOR_ACCENT))
    card = d.add(Box(600, 60, 145, 184, label="Card or\nlevel shifter", fill=COLOR_HARDWARE))
    dreg = d.add(Box(380, 290, 120, 40, label="Direction reg"))
    d.add(Arrow((eng.x + eng.w, oreg.cy), (oreg, "l"), label="o", label_pos=(160, oreg.cy - 10)))
    d.add(Arrow((eng.x + eng.w, ereg.cy), (ereg, "l"), label="oe", label_pos=(160, ereg.cy - 10)))
    d.add(Arrow((ireg, "l"), (eng.x + eng.w, ireg.cy), label="i", label_pos=(160, ireg.cy - 10)))
    d.add(Arrow((oreg, "r"), (buf.x, oreg.cy)))
    d.add(Arrow((ereg, "r"), (buf.x, ereg.cy)))
    d.add(Arrow((buf.x, ireg.cy), (ireg, "r")))
    d.add(Arrow((buf.x + buf.w, 152), (card.x, 152), kind="data", heads="both", label="CMD, DAT",
        label_pos=(557, 140)))
    d.add(Arrow((70, eng.y + eng.h), (dreg, "l"), via=[(70, dreg.cy)], label="oe",
        label_pos=(90, dreg.cy - 10)))
    d.add(Arrow((dreg, "r"), (667, card.y + card.h), via=[(667, dreg.cy)], label="direction pins",
        label_pos=(580, dreg.cy - 10)))
    return d
