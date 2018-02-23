from migen import *
from migen.fhdl import verilog

from litex.soc.interconnect import stream
from litex.soc.interconnect.csr import *


class CRC(Module):
    def __init__(self, poly, size, dw, init=0):
        crcreg = [Signal(size, reset=init) for i in range(dw+1)]
        self.val = val = Signal(dw)
        self.crc = crcreg[dw]
        self.clr = Signal()
        self.enable = Signal()

        for i in range(dw):
            inv = val[dw-i-1] ^ crcreg[i][size-1]
            tmp = []
            tmp.append(inv)
            for j in range(size -1):
                if((poly >> (j + 1)) & 1):
                    tmp.append(crcreg[i][j] ^ inv)
                else:
                    tmp.append(crcreg[i][j])
            self.comb += crcreg[i+1].eq(Cat(*tmp))

        self.sync += If(self.clr,
            crcreg[0].eq(init)
        ).Else(
            If(self.enable,
               crcreg[0].eq(crcreg[dw])
            )
        )


class CRCChecker(Module):
    def __init__(self, poly, size, dw, init=0):
        self.submodules.subcrc = CRC(poly, size, dw, init=init)
        self.val = self.subcrc.val
        self.check = Signal(size)
        self.valid = Signal()

        self.comb += [
            self.subcrc.clr.eq(1),
            self.subcrc.enable.eq(1),
            self.valid.eq(self.subcrc.crc == self.check),
        ]


class CRCDownstreamChecker(Module):
    def __init__(self):
        self.sink = sink = stream.Endpoint([("data", 8)])
        self.source = source = stream.Endpoint([("data", 8)])

        # # #

        val = Signal(8)
        cnt = Signal(4)
        tmpcnt = Signal(10)
        crcs = [CRC(poly=0x1021, size=16, dw=2, init=0) for i in range(4)]
        crctmp = [Signal(16) for i in range(4)]
        self.valid = Signal()

        for i in range(4):
            self.submodules += crcs[i]
            self.sync += [
                If(sink.ready & sink.valid,
                    crctmp[i].eq(crcs[i].crc)
                )
            ]

        fifo = [Signal(16) for i in range(4)]
        self.comb += If((fifo[0] == crctmp[0]) &
                        (fifo[1] == crctmp[1]) &
                        (fifo[2] == crctmp[2]) &
                        (fifo[3] == crctmp[3]),
            self.valid.eq(1)
        )

        for i in range(4):
            self.sync += [
                If(sink.valid & sink.ready,
                    fifo[i].eq(Cat(sink.data[3-i], sink.data[7-i], fifo[i][0:14])),
                    val[7-i].eq(fifo[i][13]),
                    val[3-i].eq(fifo[i][12])
                )
            ]
            self.comb += [
                crcs[i].val.eq(Cat(val[3-i], val[7-i])),
                crcs[i].enable.eq(sink.valid & sink.ready),
                If(cnt == 7,
                    crcs[i].clr.eq(1),
                ).Else(
                    crcs[i].clr.eq(0)
                )
            ]

        self.sync += [
            If(sink.valid & sink.ready,
               If(sink.last,
                   cnt.eq(0)
               ).Elif(cnt != 10,
                   cnt.eq(cnt + 1)
               )
            )
        ]

        self.comb += [
            source.data.eq(val),
            If(sink.valid & (cnt > 7),
                source.valid.eq(1)
            ),
            If(cnt < 8,
                sink.ready.eq(1)
            ).Else(
                sink.ready.eq(source.ready)
            ),
            source.last.eq(sink.last)
        ]


class CRCUpstreamInserter(Module):
    def __init__(self):
        self.sink = sink = stream.Endpoint([("data", 8)])
        self.source = source = stream.Endpoint([("data", 8)])

        crc = Signal(8)
        cnt = Signal(3)
        crcs = [CRC(poly=0x1021, size=16, dw=2, init=0) for i in range(4)]

        crctmp = [Signal(16) for i in range(4)]
        for i in range(4):
            self.submodules += crcs[i]
            self.comb += [
                crcs[i].val.eq(Cat(sink.data[i], sink.data[i+4])),
                crcs[i].clr.eq(sink.last & sink.valid & sink.ready),
                crcs[i].enable.eq(sink.valid & sink.ready)
            ]

        cases = {}
        for i in range(8):
            crclist = []
            for j in range(2):
                for k in range(4):
                    crclist.append(crctmp[k][2*(7-i) +j])

            cases[i] = source.data.eq(Cat(*crclist))

        fsm = FSM()
        self.submodules.fsm = fsm
        crctmpsync = [NextValue(crctmp[i], crcs[i].crc) for i in range(4)]

        fsm.act("IDLE",
            source.data.eq(sink.data),
            source.valid.eq(sink.valid),
            sink.ready.eq(source.ready),
            source.last.eq(0),
            *crctmpsync,
            If(sink.valid & sink.last & sink.ready,
                NextState("SENDCRC"),
                NextValue(cnt, 0)
            )
        )

        fsm.act("SENDCRC",
            sink.ready.eq(0),
            source.valid.eq(1),
            If(cnt == 7,
                source.last.eq(1),
            ),
            Case(cnt, cases),
            If(source.ready,
                If(cnt == 7,
                    NextState("IDLE")
                ).Else(
                    NextValue(cnt, cnt+1)
                )
            )
        )
