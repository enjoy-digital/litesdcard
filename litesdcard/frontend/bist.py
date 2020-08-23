#
# This file is part of LiteSDCard.
#
# Copyright (c) 2017-2020 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""Built In Self Test (BIST) modules for testing LiteSDCard functionality."""

from functools import reduce
from operator import xor

from migen import *

from litex.soc.interconnect import stream
from litex.soc.interconnect.csr import *

# LFSR/Counter -------------------------------------------------------------------------------------

@CEInserter()
class LFSR(Module):
    def __init__(self, n_out, n_state=31, taps=[27, 30]):
        self.o = Signal(n_out)

        # # #

        state  = Signal(n_state)
        curval = [state[i] for i in range(n_state)]
        curval += [0]*(n_out - n_state)
        for i in range(n_out):
            nv = ~reduce(xor, [curval[tap] for tap in taps])
            curval.insert(0, nv)
            curval.pop()

        self.sync += [
            state.eq(Cat(*curval[:n_state])),
            self.o.eq(Cat(*curval))
        ]


@CEInserter()
class Counter(Module):
    def __init__(self, n_out):
        self.o = Signal(n_out)

        # # #

        self.sync += self.o.eq(self.o + 1)

# BISTBlockGenerator -------------------------------------------------------------------------------

@ResetInserter()
class _BISTBlockGenerator(Module):
    def __init__(self, random):
        self.source = source = stream.Endpoint([("data", 32)])
        self.start  = Signal()
        self.done   = Signal()
        self.count  = Signal(32)

        # # #

        gen_cls = LFSR if random else Counter
        gen     = gen_cls(32)
        self.submodules += gen

        blkcnt = Signal(32)
        datcnt = Signal(9)

        self.submodules.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            If(self.start,
                NextValue(blkcnt, 0),
                NextValue(datcnt, 0),
                NextState("RUN")
            )
        )
        fsm.act("RUN",
            source.valid.eq(1),
            source.last.eq(datcnt == (512//4 - 1)),
            If(source.ready,
                gen.ce.eq(1),
                If(source.last,
                    If(blkcnt == (self.count - 1),
                        NextState("DONE")
                    ).Else(
                        NextValue(blkcnt, blkcnt + 1),
                        NextValue(datcnt, 0)
                    ),
                ).Else(
                    NextValue(datcnt, datcnt + 1)
                )
            )
        )
        fsm.act("DONE",
            self.done.eq(1)
        )
        self.comb += source.data.eq(gen.o)


class BISTBlockGenerator(Module, AutoCSR):
    def __init__(self, random):
        self.source = source = stream.Endpoint([("data", 32)])
        self.reset  = CSR()
        self.start  = CSR()
        self.done   = CSRStatus()
        self.count  = CSRStorage(32, reset=1)

        # # #

        self.submodules.core = core = _BISTBlockGenerator(random)
        self.comb += [
            core.source.connect(source),
            core.reset.eq(self.reset.re),
            core.start.eq(self.start.re),
            self.done.status.eq(core.done),
            core.count.eq(self.count.storage)
        ]

# BISTBlockChecker ---------------------------------------------------------------------------------

@ResetInserter()
class _BISTBlockChecker(Module):
    def __init__(self, random):
        self.sink   = sink = stream.Endpoint([("data", 32)])
        self.start  = Signal()
        self.done   = Signal()
        self.count  = Signal(32)
        self.errors = Signal(32)

        # # #

        gen_cls = LFSR if random else Counter
        gen     = gen_cls(32)
        self.submodules += gen

        blkcnt = Signal(32)
        datcnt = Signal(9)

        self.submodules.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            sink.ready.eq(1),
            self.done.eq(1),
            If(self.start,
                NextValue(blkcnt, 0),
                NextValue(datcnt, 0),
                NextValue(self.errors, 0),
                NextState("RUN")
            )
        )
        fsm.act("RUN",
            sink.ready.eq(1),
            If(sink.valid,
                gen.ce.eq(1),
                NextValue(datcnt, datcnt + 1),
                If(sink.data != gen.o,
                	If(self.errors != (2**32-1),
                    	NextValue(self.errors, self.errors + 1)
                    )
                ),
                If(sink.last | (datcnt == (512//4 - 1)),
                    If(blkcnt == (self.count - 1),
                        NextState("DONE")
                    ).Else(
                        NextValue(blkcnt, blkcnt + 1),
                        NextValue(datcnt, 0)
                    ),
                )
            )
        )
        fsm.act("DONE",
            self.done.eq(1)
        )


class BISTBlockChecker(Module, AutoCSR):
    def __init__(self, random):
        self.sink   = sink = stream.Endpoint([("data", 32)])
        self.reset  = CSR()
        self.start  = CSR()
        self.done   = CSRStatus()
        self.count  = CSRStorage(32, reset=1)
        self.errors = CSRStatus(32)

        # # #

        self.submodules.core = core = _BISTBlockChecker(random)
        self.comb += [
            sink.connect(core.sink),
            core.reset.eq(self.reset.re),
            core.start.eq(self.start.re),
            self.done.status.eq(core.done),
            core.count.eq(self.count.storage),
            self.errors.status.eq(core.errors)
        ]
