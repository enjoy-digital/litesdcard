#
# This file is part of LiteSDCard.
#
# Copyright (c) 2017-2020 Florent Kermarrec <florent@enjoy-digital.fr>
# Copyright (c) 2017 Pierre-Olivier Vauboin <po@lambdaconcept.com>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *
from migen.fhdl import verilog

from litex.soc.interconnect import stream
from litex.soc.interconnect.csr import *

# CRC ----------------------------------------------------------------------------------------------

class CRC(Module):
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
        self.comb += [
            If(self.enable,
                self.crc.eq(reg[dw])
            ).Else(
                self.crc.eq(reg[0])
            )
        ]

# CRC16Checker -------------------------------------------------------------------------------------

class CRC16Inserter(Module):
    def __init__(self):
        self.sink   = sink   = stream.Endpoint([("data", 8)])
        self.source = source = stream.Endpoint([("data", 8)])

        # # #

        count = Signal(3)

        crcs  = [CRC(polynom=0x1021, taps=16, dw=2, init=0) for i in range(4)]
        for i in range(4):
            self.submodules += crcs[i]
            self.comb += [
                crcs[i].reset.eq(source.valid & source.ready & source.last),
                crcs[i].enable.eq(sink.valid & sink.ready),
                crcs[i].din[0].eq(sink.data[4*0 + i]),
                crcs[i].din[1].eq(sink.data[4*1 + i]),
            ]

        self.submodules.fsm = fsm = FSM(reset_state="DATA")
        fsm.act("DATA",
            NextValue(count, 0),
            sink.connect(source, omit={"last"}),
            source.last.eq(0),
            If(sink.valid & sink.ready,
                If(sink.last,
                    NextState("CRC"),
                )
            )
        )
        cases = {}
        for i in range(8):
            cases[i] = [
                source.data[0].eq(crcs[0].crc[2*(8-1-i) + 0]),
                source.data[1].eq(crcs[1].crc[2*(8-1-i) + 0]),
                source.data[2].eq(crcs[2].crc[2*(8-1-i) + 0]),
                source.data[3].eq(crcs[3].crc[2*(8-1-i) + 0]),
                source.data[4].eq(crcs[0].crc[2*(8-1-i) + 1]),
                source.data[5].eq(crcs[1].crc[2*(8-1-i) + 1]),
                source.data[6].eq(crcs[2].crc[2*(8-1-i) + 1]),
                source.data[7].eq(crcs[3].crc[2*(8-1-i) + 1]),
            ]
        fsm.act("CRC",
            source.valid.eq(1),
            source.last.eq(count == (8-1)),
            Case(count, cases),
            If(source.valid & source.ready,
                NextValue(count, count + 1),
                If(source.last,
                    NextState("DATA")
                )
            )
        )

# CRC16Checker -------------------------------------------------------------------------------------

class CRC16Checker(Module):
    # TODO: currently only removing CRC block, add check using CRC16Inserter
    def __init__(self):
        self.sink   = sink   = stream.Endpoint([("data", 8)])
        self.source = source = stream.Endpoint([("data", 8)])

        # # #

        fifo = stream.SyncFIFO([("data", 8)], 16)
        fifo = ResetInserter()(fifo)
        self.submodules += fifo
        self.comb += [
            sink.connect(fifo.sink),
            fifo.source.connect(source, omit={"valid", "ready"}),
            source.valid.eq(fifo.level >= 8),
            fifo.source.ready.eq(source.valid & source.ready),
            fifo.reset.eq(sink.valid & sink.ready & sink.last),
        ]
