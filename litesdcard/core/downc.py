import random

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

def tbramreader(dut):
    random.seed(0)
    yield dut.source.ready.eq(1)
    yield

    yield dut.sink.data.eq(0xabcdef12)
    yield dut.sink.cnt.eq(random.randint(0, 3))
    yield dut.sink.valid.eq(1)
    yield dut.sink.last.eq(random.randint(0, 1))

    for i in range(100):
        if((yield dut.sink.ready)):
            yield dut.sink.data.eq(0x12345678+i)
            yield dut.sink.cnt.eq(random.randint(0, 3))
            yield dut.sink.last.eq(random.randint(0, 1))
        yield dut.source.ready.eq(random.randint(0,1))
        yield

if __name__ == '__main__':

    soc = Stream32to8()
    run_simulation(soc, tbramreader(soc), vcd_name='/tmp/toto.vcd')
