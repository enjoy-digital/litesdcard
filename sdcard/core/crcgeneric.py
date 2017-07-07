from litex.gen import *
from litex.gen.fhdl import verilog
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

def tbcheck(dut):
    yield dut.val.eq(0x4000000000)
    yield
    yield dut.check.eq(0x1d)
    yield
    yield dut.check.eq(0x4a) # Good
    yield
    yield dut.check.eq(0xff)
    yield

def tb(dut):
    yield dut.val.eq(0x00000000ff)
    yield dut.clr.eq(1)
    yield
    print(hex((yield dut.crc)))
    yield
    print(hex((yield dut.crc)))
    yield dut.clr.eq(0)
    yield
    print(hex((yield dut.crc)))
    yield
    print(hex((yield dut.crc)))

def main():
    dut = CRC(poly=9, size=7, dw=120)
    # dut = CRCChecker(poly=9, size=7, dw=40)
    run_simulation(dut, tb(dut), vcd_name='crc.vcd')
    #print(verilog.convert(dut, ios={dut.val, dut.crcout}))

if __name__ == "__main__":
    main()
