#
# This file is part of LiteSDCard.
#
# Copyright (c) 2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# Shared helpers of the primer figures (no build(): not a figure).
#
# Timing rows: one horizontal row per signal (a name on the left, adjoining cells on a common time
# axis); bit fields: adjoining square cells with their bit positions; lanes: one vertical line
# per side of an exchange, with horizontal arrows between them.

from svgdiag import *


def row_name(d, x, y, name, size=13):
    """Signal name, right-aligned, left of a row whose cells start at x and are centred on y."""
    d.add(Text(x - 10, y, name, size=size, anchor="end"))


def cells(d, x, y, items, h=26, size=13):
    """Row of adjoining square cells: items is a list of (width, label, fill); fill None = gap."""
    out = []
    for w, label, fill in items:
        if fill is not None:
            out.append(d.add(Box(x, y - h/2, w, h, label=label, radius=0, fill=fill, size=size)))
        x += w
    return out


def level(d, x0, x1, y, high=True, h=16):
    """Idle line level (high or low) between x0 and x1 on a row centred on y."""
    yy = y - h/2 if high else y + h/2
    d.add(Bus([(x0, yy), (x1, yy)], kind="control"))


def field_bits(d, x, y, items, size=11):
    """Bit numbers above a bit field: items is a list of (x_left, x_right, msb, lsb)."""
    for x0, x1, msb, lsb in items:
        if msb == lsb:
            d.add(Text((x0 + x1)/2, y, str(msb), size=size))
        else:
            d.add(Text(x0 + 3, y, str(msb), size=size, anchor="start"))
            d.add(Text(x1 - 3, y, str(lsb), size=size, anchor="end"))


def span(d, x0, x1, y, label, kind="control", side="above"):
    """Double-headed horizontal arrow from x0 to x1 at y, with its label above or below."""
    d.add(Arrow((x0, y), (x1, y), kind=kind, heads="both", label=label, label_side=side))


def lanes(d, xs, y0, y1, names, size=FONT_SIZE):
    """Vertical lifelines at xs from y0 to y1, each with its name above."""
    for x, name in zip(xs, names):
        d.add(Text(x, y0 - 14, name, size=size, bold=True))
        d.add(Bus([(x, y0), (x, y1)], dash="4,3", color="#9a9a9a"))
