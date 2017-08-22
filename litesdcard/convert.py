from litex.gen import *
from litex.soc.interconnect.csr import *
from litex.soc.interconnect import stream


class Stream32to8(Module):
    def __init__(self):
        self.sink = stream.Endpoint([("data", 32), ("cnt", 2)])
        self.source = stream.Endpoint([("data",8)])

        mux = Signal(2)
        cnt = Signal(2)
        data = Signal(32)
        cnt = Signal(2)
        last = Signal()
        busy = Signal()
        cases = {}
        for i in range(3):
            cases[i+1] = self.source.data.eq(data[(i+1)*8:(i+2)*8])
        cases[0] = self.source.data.eq(self.sink.data[0:8])

        self.sync += [
            If(~busy & self.sink.valid & (self.sink.cnt > 0),
                data.eq(self.sink.data),
                busy.eq(1),
                last.eq(self.sink.last)
            ).Elif((mux == self.sink.cnt) & self.sink.ready,
                busy.eq(0),
            ),

            If(self.sink.valid & (self.sink.cnt > 0) &  (cnt != self.sink.cnt) & self.source.ready,
                cnt.eq(cnt + 1)
            ),

            If((cnt == self.sink.cnt) & self.source.ready,
               cnt.eq(0)
            )
        ]

        self.comb += [
            Case(mux, cases),

            If(self.sink.valid & (self.sink.cnt==0),
                mux.eq(0),
                self.source.valid.eq(1),
                self.source.last.eq(self.sink.last),
                self.sink.ready.eq(self.source.ready)
            ).Elif(self.sink.valid & (self.sink.cnt > 0) &  (cnt <= self.sink.cnt),
                mux.eq(cnt),
                self.source.valid.eq(1),
                If(cnt == self.sink.cnt,
                    self.source.last.eq(last),
                    self.sink.ready.eq(self.source.ready),
                )
            )
        ]


class Stream8to32(Module):
    def __init__(self):
        self.sink = stream.Endpoint([("data",8)])
        self.submodules.fifo = stream.SyncFIFO([("data", 32), ('cnt', 2)], 4)
        self.source = self.fifo.source

        data = Signal(32)
        mux = Signal(2)

        cases = {}
        sink_cases = {}

        for i in range(4):
            cases[i] = data[(i)*8:(i+1)*8].eq(self.sink.data)

        sink_cases[0] = self.fifo.sink.data.eq(self.sink.data)
        for i in range(3):
            sink_cases[i+1] = self.fifo.sink.data.eq(Cat(data[0:8*(i+1)], self.sink.data))

        self.comb += [
            Case(mux, sink_cases),
            If(self.sink.valid & ((mux == 3) | self.sink.last),
                self.fifo.sink.valid.eq(1)
            ),
            self.fifo.sink.cnt.eq(mux),
            self.fifo.sink.last.eq(self.sink.last),
            self.sink.ready.eq(self.fifo.sink.ready),
        ]

        self.sync += [
            If(self.sink.valid,
                Case(mux, cases),
                If(self.fifo.sink.ready,
                    If(self.sink.last,
                        mux.eq(0)
                    ).Else(
                        mux.eq(mux + 1)
                    )
                )
            )
        ]
