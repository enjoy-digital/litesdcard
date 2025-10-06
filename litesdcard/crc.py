#
# This file is part of LiteSDCard.
#
# Copyright (c) 2017-2023 Florent Kermarrec <florent@enjoy-digital.fr>
# Copyright (c) 2017 Pierre-Olivier Vauboin <po@lambdaconcept.com>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *

from litex.gen import *

# CRC ----------------------------------------------------------------------------------------------

class CRC(LiteXModule):
    def __init__(self, polynom, taps, dw, init=0):
        self.reset  = Signal()
        self.enable = Signal()
        self.din    = Signal(dw)
        self.crc    = Signal(taps)

        # # #

        reg = [Signal(taps, reset=init) for i in range(dw+1)]

        # CRC LFSR
        for i in range(dw):
            inv = self.din[dw-i-1] ^ reg[i][taps-1]
            tmp = [inv]
            for j in range(taps -1):
                if((polynom >> (j + 1)) & 1):
                    tmp.append(reg[i][j] ^ inv)
                else:
                    tmp.append(reg[i][j])
            self.comb += reg[i+1].eq(Cat(*tmp))

        # Control
        self.sync += [
            If(self.reset,
                reg[0].eq(init)
            ).Else(
                If(self.enable,
                    reg[0].eq(reg[dw])
                )
            )
        ]

        # Output
        self.comb += self.crc.eq(reg[0])

# CRC16 -------------------------------------------------------------------------------------

class CRC16(LiteXModule):
    def __init__(self, data_pads, count):

        self.data_pads_out = data_pads_out = Signal(len(data_pads))

        self.enable = Signal()
        self.reset  = Signal()
        self.crc = []

        # # #

        crcs  = [CRC(polynom=0x1021, taps=16, dw=1, init=0) for i in range(len(data_pads))]
        for i in range(len(data_pads)):
            self.submodules += crcs[i]
            self.crc.append(crcs[i].crc)
            self.comb += [
                crcs[i].reset.eq(self.reset),
                crcs[i].enable.eq(self.enable),
                crcs[i].din[0].eq(data_pads[i]),
            ]

        cases = {}
        for i in range(16):
            cases[i] = [
                data_pads_out[n].eq(crcs[n].crc[16-1-i]) for n in range(len(data_pads_out))
            ]

        self.comb += Case(count, cases)
