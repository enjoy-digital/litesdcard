from litex.gen import *
from litex.soc.interconnect import stream, wishbone
from litex.soc.interconnect.csr import *


class RAMReader(Module, AutoCSR):
    def __init__(self, data_width=32):
        self.bus = bus = wishbone.Interface(data_width)
        self.source = stream.Endpoint([('data', data_width), ('cnt', 2)])

        self.address = CSRStorage(32)
        self.length = CSRStorage(32)
        self.done = CSRStatus(reset=1)

        # # #

        word_counter = Signal(32)
        to_count = Signal(32)
        fifo = stream.SyncFIFO(self.source.description, 4)
        self.submodules += fifo

        self.comb += [
            self.bus.we.eq(0),
            self.bus.sel.eq(2**len(self.bus.sel) - 1),
            self.bus.adr.eq(self.address.storage + word_counter),

            If(self.length.storage & 0x3,
               to_count.eq((self.length.storage >> 2) +1)
            ).Else(
                to_count.eq(self.length.storage >> 2)
            ),

            fifo.sink.data.eq(self.bus.dat_r),
            fifo.sink.valid.eq(self.bus.ack),

            If(word_counter == to_count -1,
               fifo.sink.last.eq(1),
               fifo.sink.cnt.eq((self.length.storage & 0x3) - 1),
            ).Else(
                fifo.sink.cnt.eq(3),
            ),
            fifo.source.connect(self.source),

            If(~self.done.status & fifo.sink.ready & (word_counter < to_count),
               self.bus.cyc.eq(1),
               self.bus.stb.eq(1),
            )

        ]

        self.sync += [
            If(self.length.re & (self.length.storage > 0),
               word_counter.eq(0),
               self.done.status.eq(0)
            ).Elif(word_counter == to_count,
               self.done.status.eq(1),
               word_counter.eq(0),
            ).Elif(self.bus.ack,
               word_counter.eq(word_counter + 1)
            )
        ]


class RAMWriter(Module, AutoCSR):
    def __init__(self, data_width=32):
        self.sink = sink = stream.Endpoint([('data', 32), ('cnt', 2)])
        self.bus = bus = wishbone.Interface(data_width)

        self.address = CSRStorage(32)

        # # #

        counter = Signal(32)

        self.sync += [
            If(self.address.re,
                counter.eq(0),
            ).Elif(sink.valid & sink.ready,
                counter.eq(counter + 1),
            )
        ]

        self.comb += [
            self.bus.sel.eq(2**len(self.bus.sel) - 1),
            self.sink.ready.eq(self.bus.ack),
            If(self.sink.valid,
                self.bus.we.eq(1),
                self.bus.stb.eq(1),
                self.bus.cyc.eq(1),
                self.bus.dat_w.eq(self.sink.data),
                self.bus.adr.eq(self.address.storage + counter),
            ).Else(
                self.bus.stb.eq(0),
                self.bus.cyc.eq(0),
            ),
        ]
