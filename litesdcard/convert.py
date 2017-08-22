from litex.gen import *
from litex.soc.interconnect.csr import *
from litex.soc.interconnect import stream


class Stream32to8(Module):
    def __init__(self):
        self.sink = sink = stream.Endpoint([("data", 32), ("cnt", 2)])
        self.source = source = stream.Endpoint([("data", 8)])

        mux = Signal(2)
        cnt = Signal(2)
        data = Signal(32)
        cnt = Signal(2)
        last = Signal()
        busy = Signal()
        cases = {}
        for i in range(3):
            cases[i+1] = source.data.eq(data[(i+1)*8:(i+2)*8])
        cases[0] = source.data.eq(sink.data[0:8])

        self.sync += [
            If(~busy & sink.valid & (sink.cnt > 0),
                data.eq(sink.data),
                busy.eq(1),
                last.eq(sink.last)
            ).Elif((mux == sink.cnt) & sink.ready,
                busy.eq(0),
            ),

            If(sink.valid & (sink.cnt > 0) &  (cnt != sink.cnt) & source.ready,
                cnt.eq(cnt + 1)
            ),

            If((cnt == sink.cnt) & source.ready,
               cnt.eq(0)
            )
        ]

        self.comb += [
            Case(mux, cases),

            If(sink.valid & (sink.cnt == 0),
                mux.eq(0),
                source.valid.eq(1),
                source.last.eq(sink.last),
                sink.ready.eq(source.ready)
            ).Elif(sink.valid & (sink.cnt > 0) &  (cnt <= sink.cnt),
                mux.eq(cnt),
                source.valid.eq(1),
                If(cnt == sink.cnt,
                    source.last.eq(last),
                    sink.ready.eq(source.ready),
                )
            )
        ]


class Stream8to32(Module):
    def __init__(self):
        self.sink = sink = stream.Endpoint([("data", 8)])
        self.source = source = stream.Endpoint([("data", 32), ('cnt', 2)])

        # # #

        fifo = stream.SyncFIFO(source.description, 4)
        self.submodules += fifo

        data = Signal(32)
        mux = Signal(2)

        cases = {}
        sink_cases = {}

        for i in range(4):
            cases[i] = data[(i)*8:(i+1)*8].eq(sink.data)

        sink_cases[0] = fifo.sink.data.eq(sink.data)
        for i in range(3):
            sink_cases[i+1] = fifo.sink.data.eq(Cat(data[0:8*(i+1)], sink.data))

        self.comb += [
            Case(mux, sink_cases),
            If(sink.valid & ((mux == 3) | sink.last),
                fifo.sink.valid.eq(1)
            ),
            fifo.sink.cnt.eq(mux),
            fifo.sink.last.eq(sink.last),
            sink.ready.eq(fifo.sink.ready),

            fifo.source.connect(source)
        ]

        self.sync += [
            If(sink.valid,
                Case(mux, cases),
                If(fifo.sink.ready,
                    If(sink.last,
                        mux.eq(0)
                    ).Else(
                        mux.eq(mux + 1)
                    )
                )
            )
        ]
