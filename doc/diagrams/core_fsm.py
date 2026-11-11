#
# This file is part of LiteSDCard.
#
# Copyright (c) 2017-2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# Main state machine of SDCore (litesdcard/core.py): IDLE, CMD-SEND, CMD-RESPONSE, DATA-WRITE,
# DATA-READ.

from svgdiag import *


def state(d, x, y, label, w=150, h=46, fill=COLOR_FILL):
    return d.add(Box(x, y, w, h, label=label, fill=fill))


def build():
    d = Diagram(CANVAS_WIDTH, 330)
    idle = state(d, 20,  140, "IDLE",         fill=COLOR_ACCENT_LIGHT)
    send = state(d, 305, 30,  "CMD-SEND",     fill=COLOR_ACCENT)
    resp = state(d, 590, 140, "CMD-RESPONSE", fill=COLOR_ACCENT)
    dw   = state(d, 305, 140, "DATA-WRITE")
    dr   = state(d, 305, 260, "DATA-READ")
    # IDLE to CMD-SEND on a write of cmd_send.
    d.add(Arrow((idle, "t", 0.3), (send, "l", 0.3), label="cmd_send", label_pos=(150, send.y + 2)))
    # No response expected: back to IDLE once the 6 bytes are sent.
    d.add(Arrow((send, "l", 0.7), (idle, "t", 0.7), label="no response", label_pos=(178, 82),
        label_anchor="start"))
    d.add(Arrow((send, "r"), (resp, "t"), label="response expected", label_pos=(570, send.cy - 12)))
    # From CMD-RESPONSE: to the data states, or back to IDLE.
    d.add(Arrow((resp, "l", 0.3), (dw, "r", 0.3), label="write", label_pos=(522, dw.y + 2)))
    d.add(Arrow((resp, "b"), (dr, "r"), label="read", label_pos=(690, 270), label_anchor="start"))
    d.add(Arrow((resp, "l", 0.8), (idle, "r", 0.8), via=[(560, 177), (560, 230), (190, 230),
        (190, 177)], label="no data, timeout, bad CRC", label_pos=(375, 242), kind="feedback"))
    # Data states back to IDLE.
    d.add(Arrow((dw, "l", 0.3), (idle, "r", 0.3), label="last block", label_pos=(247, dw.y + 2)))
    d.add(Arrow((dr, "l"), (idle, "b"), label="last block, timeout", label_pos=(110, 296),
        label_anchor="middle"))
    return d
