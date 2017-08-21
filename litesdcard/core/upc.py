from litex.gen import *
from litex.soc.interconnect.csr import *
from litex.soc.interconnect import stream

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

def tb(dut):
    #random.seed(0)
    yield dut.source.ready.eq(1)
    yield
    yield dut.sink.valid.eq(1)
    yield dut.sink.data.eq(0x11)
    yield
    yield dut.sink.data.eq(0x22)
    yield
    yield dut.sink.data.eq(0x33)
    yield dut.sink.last.eq(1)
    yield
    for i in range(10):
        yield dut.sink.data.eq(0xaa+i)
        yield dut.sink.valid.eq(1)
        yield
    yield dut.sink.data.eq(0x11)
    yield dut.sink.last.eq(1)
    yield
    yield dut.sink.last.eq(0)
    for i in range(10):
        yield dut.sink.data.eq(0xaa+i)
        yield dut.sink.valid.eq(1)
        yield

    yield dut.sink.valid.eq(0)
    yield

if __name__ == "__main__":
    soc = Stream8to32()
    run_simulation(soc, tb(soc), vcd_name='upc.vcd')
