from litex.gen import *
from litex.gen.fhdl import verilog
from litex.soc.interconnect import stream
from litex.soc.interconnect.csr import *

from litesdcard.core.crcgeneric import CRC

class DOWNCRCChecker(Module):
    def __init__(self):
        self.sink = stream.Endpoint([("data", 8)])
        self.source = stream.Endpoint([("data", 8)])

        val = Signal(8)
        cnt = Signal(4)
        tmpcnt = Signal(10)
        crcs = [CRC(poly=0x1021, size=16, dw=2, init=0) for i in range(4)]
        crctmp = [Signal(16) for i in range(4)]
        self.valid = Signal()

        for i in range(4):
            self.submodules += crcs[i]
            self.sync += [
                If(self.sink.ready & self.sink.valid,
                    crctmp[i].eq(crcs[i].crc)
                )
            ]

        fifo = [Signal(16) for i in range(4)]
        self.comb += If((fifo[0] == crctmp[0]) & (fifo[1] == crctmp[1]) & (fifo[2] == crctmp[2]) & (fifo[3] == crctmp[3]),
            self.valid.eq(1)
        )

        for i in range(4):
            self.sync += [
                If(self.sink.valid & self.sink.ready,
                    fifo[i].eq(Cat(self.sink.data[3-i], self.sink.data[7-i], fifo[i][0:14])),
                    val[7-i].eq(fifo[i][13]),
                    val[3-i].eq(fifo[i][12])
                )
            ]
            self.comb += [
                crcs[i].val.eq(Cat(val[3-i], val[7-i])),
                crcs[i].enable.eq(self.sink.valid & self.sink.ready),
                If(cnt == 7,
                    crcs[i].clr.eq(1),
                ).Else(
                    crcs[i].clr.eq(0)
                )
            ]

        self.sync += [
            If(self.sink.valid & self.sink.ready,
               If(self.sink.last,
                   cnt.eq(0)
               ).Elif(cnt != 10,
                   cnt.eq(cnt + 1)
               )
            )
        ]

        self.comb += [
            self.source.data.eq(val),
            If(self.sink.valid & (cnt > 7),
                self.source.valid.eq(1)
            ),
            If(cnt < 8,
                self.sink.ready.eq(1)
            ).Else(
                self.sink.ready.eq(self.source.ready)
            ),
            self.source.last.eq(self.sink.last)
        ]

class UPCRCAdd(Module):
    def __init__(self):
        self.sink = stream.Endpoint([("data", 8)])
        self.source = stream.Endpoint([("data", 8)])

        crc = Signal(8)
        cnt = Signal(3)
        crcs = [CRC(poly=0x1021, size=16, dw=2, init=0) for i in range(4)]

        crctmp = [Signal(16) for i in range(4)]
        for i in range(4):
            self.submodules += crcs[i]
            self.comb += [
                crcs[i].val.eq(Cat(self.sink.data[i], self.sink.data[i+4])),
                crcs[i].clr.eq(self.sink.last & self.sink.valid & self.sink.ready),
                crcs[i].enable.eq(self.sink.valid & self.sink.ready)
            ]

        cases = {}
        for i in range(8):
            crclist = []
            for j in range(2):
                for k in range(4):
                    crclist.append(crctmp[k][2*(7-i) +j])

            cases[i] = self.source.data.eq(Cat(*crclist))

        fsm = FSM()
        self.submodules.fsm = fsm
        crctmpsync = [NextValue(crctmp[i], crcs[i].crc) for i in range(4)]

        fsm.act("IDLE",
            self.source.data.eq(self.sink.data),
            self.source.valid.eq(self.sink.valid),
            self.sink.ready.eq(self.source.ready),
            self.source.last.eq(0),
            *crctmpsync,
            If(self.sink.valid & self.sink.last & self.sink.ready,
                NextState("SENDCRC"),
                NextValue(cnt, 0)
            )
        )

        fsm.act("SENDCRC",
            self.sink.ready.eq(0),
            self.source.valid.eq(1),
            If(cnt==7,
                self.source.last.eq(1),
            ),
            Case(cnt, cases),
            If(self.source.ready,
                If(cnt == 7,
                    NextState("IDLE")
                ).Else(
                    NextValue(cnt, cnt+1)
                )
            )
        )

class TOP(Module):
    def __init__(self):
        adder = UPCRCAdd()
        self.submodules += adder
        checker = DOWNCRCChecker()
        self.submodules += checker

        self.comb += adder.source.connect(checker.sink)
        self.source = checker.source
        self.sink = adder.sink

def tbcrcadd(dut):
    yield from _tbcrcadd(dut)
    yield from _tbcrcadd(dut)

def _tbcrcadd(dut):

    yield dut.sink.valid.eq(1)
    i = 0
    d = [0xef, 0xbe, 0xad, 0xde]
    while i < 512-1:
        yield dut.sink.data.eq(d[i%4])
        if (yield dut.sink.ready):
            i += 1
        if (yield dut.source.valid):
            yield dut.source.ready.eq(not (yield dut.source.ready))
        yield
    yield dut.sink.data.eq(d[i%4])
    yield dut.sink.last.eq(1)
    if (yield dut.source.valid):
        yield dut.source.ready.eq(not (yield dut.source.ready))
    yield
    yield dut.sink.valid.eq(0)
    yield dut.sink.last.eq(0)
    for i in range(20):
        if (yield dut.source.valid):
            yield dut.source.ready.eq(not (yield dut.source.ready))
        yield

def tb(dut):

    yield dut.source.ready.eq(1)
    yield dut.sink.valid.eq(1)
    for i in range (511):
        yield dut.sink.data.eq(i%256)
        yield
    yield dut.sink.data.eq(0xff)
    yield dut.sink.last.eq(1)
    yield

    yield dut.sink.last.eq(0)
    for i in range (100):
        yield dut.sink.data.eq(0x00)
        yield

    yield dut.sink.data.eq(0x0f)
    yield
    yield dut.sink.data.eq(0xff)
    yield
    yield dut.sink.data.eq(0xff)
    yield
    yield dut.sink.data.eq(0xff)
    yield
    yield dut.sink.data.eq(0xf0)
    yield
    yield dut.sink.data.eq(0xf0)
    yield
    yield dut.sink.data.eq(0x00)
    yield
    yield dut.sink.data.eq(0x0f)
    yield dut.sink.last.eq(1)
    yield
    yield dut.sink.last.eq(0)
    yield dut.sink.data.eq(32)
    yield
    yield dut.sink.last.eq(0)
    for i in range(20):
        yield

def main():
    dut = TOP()
    crcadd = UPCRCAdd()
    # run_simulation(dut, tb(dut), vcd_name='crc.vcd')
    run_simulation(crcadd, tbcrcadd(crcadd), vcd_name='crc.vcd')
    #print(verilog.convert(dut, ios={dut.sink.data, dut.sink.valid, dut.sink.last, dut.sink.ready, dut.source.data, dut.source.valid, dut.source.ready, dut.source.last}))

if __name__ == "__main__":
    main()
