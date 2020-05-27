# This file is Copyright (c) 2017-2020 Florent Kermarrec <florent@enjoy-digital.fr>
# This file is Copyright (c) 2020 Antmicro <www.antmicro.com>
# License: BSD

from migen import *

from litex.gen.common import reverse_bytes

from litex.soc.interconnect import stream
from litex.soc.interconnect.csr import *

# Helpers ------------------------------------------------------------------------------------------

def format_bytes(s, endianness):
    return {"big": s, "little": reverse_bytes(s)}[endianness]

# SDDataWriter (Read a 512-bytes Block from Mem and stream it on Source) ---------------------------

@ResetInserter()
class _SDDataWriter(Module):
    def __init__(self, port, endianness):
        assert port.async_read == True
        self.source = source = stream.Endpoint([("data", 32)])
        self.start  = Signal()
        self.done   = Signal()

        # # #

        count = Signal(max=512//4)

        self.submodules.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            If(self.start,
                NextValue(count, 0),
                NextState("RUN")
            )
        )
        self.comb += port.adr.eq(count)
        self.comb += source.data.eq(format_bytes(port.dat_r, endianness))
        fsm.act("RUN",
            port.adr.eq(count),
            source.valid.eq(1),
            source.last.eq(count == (512//4 - 1)),
            If(source.ready,
                NextValue(count, count + 1),
                If(source.last,
                    NextState("DONE")
                )
            )
        )
        fsm.act("DONE",
            self.done.eq(1)
        )


class SDDataWriter(Module, AutoCSR):
    def __init__(self, port, endianness):
        self.source = source = stream.Endpoint([("data", 32)])
        self.reset  = CSR()
        self.start  = CSR()
        self.done   = CSRStatus()

        # # #

        core = _SDDataWriter(port, endianness)
        self.submodules += core

        self.comb += [
            core.source.connect(source),
            core.reset.eq(self.reset.re),
            core.start.eq(self.start.re),
            self.done.status.eq(core.done),
        ]

# SDDataReader (Receive a 512-bytes Block on Sink and write it to Mem) -----------------------------

@ResetInserter()
class _SDDataReader(Module):
    def __init__(self, port, endianness):
        self.sink   = sink = stream.Endpoint([("data", 32)])
        self.start  = Signal()
        self.done   = Signal()

        # # #

        count = Signal(max=512//4)

        self.submodules.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            sink.ready.eq(1),
            self.done.eq(1),
            If(self.start,
                NextValue(count, 0),
                NextState("RUN")
            )
        )
        self.comb += port.adr.eq(count),
        self.comb += port.dat_w.eq(format_bytes(sink.data, endianness))
        fsm.act("RUN",
            sink.ready.eq(1),
            If(sink.valid,
                port.we.eq(1),
                NextValue(count, count + 1),
                If(sink.last | (count == (512//4 - 1)),
                    NextState("DONE")
                )
            )
        )
        fsm.act("DONE",
            self.done.eq(1)
        )


class SDDataReader(Module, AutoCSR):
    def __init__(self, port, endianness):
        self.sink   = sink = stream.Endpoint([("data", 32)])
        self.reset  = CSR()
        self.start  = CSR()
        self.done   = CSRStatus()

        # # #

        core = _SDDataReader(port, endianness)
        self.submodules += core

        self.comb += [
            sink.connect(core.sink),
            core.reset.eq(self.reset.re),
            core.start.eq(self.start.re),
            self.done.status.eq(core.done),
        ]
