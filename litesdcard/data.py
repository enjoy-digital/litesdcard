# This file is Copyright (c) 2017-2018 Florent Kermarrec <florent@enjoy-digital.fr>
# This file is Copyright (c) 2020 Mariusz Glebocki Antmicro <www.antmicro.com>
# License: BSD
# Based on litesdcard/bist.py


from functools import reduce
from operator import xor

from migen import *

from litex.soc.interconnect import stream
from litex.soc.interconnect.csr import *

from litex.gen import *

def with_endianness(endianness, src):
    if endianness == "big":
        return src
    else:
        return reverse_bytes(src)


@ResetInserter()
class _SDDataWriter(Module):
    def __init__(self, port, endianness):
        self.source = source = stream.Endpoint([("data", 32)])
        self.start = Signal()
        self.done = Signal()

        self.endianness = endianness
        self.port = port

        datcnt = Signal(7)

        fsm = FSM(reset_state="IDLE")
        self.submodules += fsm
        fsm.act("IDLE",
            If(self.start,
                NextValue(datcnt, 0),
                NextState("RUN")
            )
        )
        fsm.act("RUN",
            self.port.adr.eq(datcnt),
            source.data.eq(with_endianness(self.endianness, self.port.dat_r)),
            source.valid.eq(1),
            source.last.eq(datcnt == (512//4 - 1)),
            If(source.ready,
                If(source.last,
                    NextState("DONE")
                ).Else(
                    NextValue(datcnt, datcnt + 1),
                    NextState("RUN_INC"), # One cycle for memory access
                )
            )
        )
        fsm.act("RUN_INC",
            self.port.adr.eq(datcnt),
            NextState("RUN"))
        fsm.act("DONE",
            self.done.eq(1)
        )


class SDDataWriter(Module, AutoCSR):
    def __init__(self, port, endianness):
        self.source = source = stream.Endpoint([("data", 32)])
        self.reset = CSR()
        self.start = CSR()
        self.done = CSRStatus()

        core = _SDDataWriter(port, endianness)
        self.submodules += core

        self.comb += [
            core.source.connect(source),
            core.reset.eq(self.reset.re),
            core.start.eq(self.start.re),
            self.done.status.eq(core.done),
        ]


@ResetInserter()
class _SDDataReader(Module):
    def __init__(self, port, endianness):
        self.sink = sink = stream.Endpoint([("data", 32)])
        self.start = Signal()
        self.done = Signal()
        self.errors = Signal(32)

        self.endianness = endianness
        self.port = port

        datcnt = Signal(7)

        fsm = FSM(reset_state="IDLE")
        self.submodules += fsm
        fsm.act("IDLE",
            sink.ready.eq(1),
            self.done.eq(1),
            If(self.start,
                NextValue(datcnt, 0),
                NextValue(self.errors, 0),
                NextState("RUN")
            )
        )
        fsm.act("RUN",
            sink.ready.eq(1),
            self.port.adr.eq(datcnt),
            self.port.dat_w.eq(with_endianness(self.endianness, sink.data)),
            If(sink.valid,
                self.port.we.eq(1),
                NextValue(datcnt, datcnt + 1),
                If(sink.last | (datcnt == (512//4 - 1)),
                    NextState("DONE")
                )
            )
        )
        fsm.act("DONE",
            self.done.eq(1)
        )


class SDDataReader(Module, AutoCSR):
    def __init__(self, port, endianness):
        self.sink = sink = stream.Endpoint([("data", 32)])
        self.reset = CSR()
        self.start = CSR()
        self.done = CSRStatus()
        self.errors = CSRStatus(32)

        core = _SDDataReader(port, endianness)
        self.submodules += core

        self.comb += [
            sink.connect(core.sink),
            core.reset.eq(self.reset.re),
            core.start.eq(self.start.re),
            self.done.status.eq(core.done),
            self.errors.status.eq(core.errors)
        ]
