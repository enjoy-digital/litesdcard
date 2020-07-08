# This file is Copyright (c) 2020 Florent Kermarrec <florent@enjoy-digital.fr>
# License: BSD

import unittest

from migen import *

from litesdcard.phy import *

def c2bool(c):
    return {"-": 1, "_": 0}[c]


class TestPHY(unittest.TestCase):
    def test_clocker_div2(self):
        def gen(dut):
            yield dut.divider.storage.eq(2)
            clk   = "__--__--__--__--"
            clk2x = "_-_-_-_-_-_-_-_-"
            ce    = "___-___-___-___-"
            for i in range(len(clk)):
                self.assertEqual(c2bool(clk[i]),   (yield dut.clk))
                self.assertEqual(c2bool(clk2x[i]), (yield dut.clk2x))
                self.assertEqual(c2bool(ce[i]),    (yield dut.ce))
                yield
        dut = SDPHYClocker()
        run_simulation(dut, gen(dut))

    def test_clocker_div4(self):
        def gen(dut):
            yield dut.divider.storage.eq(4)
            clk   = "____----____----____----____----"
            clk2x = "__--__--__--__--__--__--__--__--"
            ce    = "_____-_______-_______-_______-__"
            for i in range(len(clk)):
                self.assertEqual(c2bool(clk[i]),   (yield dut.clk))
                self.assertEqual(c2bool(clk2x[i]), (yield dut.clk2x))
                self.assertEqual(c2bool(ce[i]),    (yield dut.ce))
                yield
        dut = SDPHYClocker()
        run_simulation(dut, gen(dut))

    def test_clocker_div8(self):
        def gen(dut):
            yield dut.divider.storage.eq(8)
            clk   = "________--------________--------"
            clk2x = "____----____----____----____----"
            ce    = "_________-_______________-______"
            for i in range(len(clk)):
                self.assertEqual(c2bool(clk[i]),   (yield dut.clk))
                self.assertEqual(c2bool(clk2x[i]), (yield dut.clk2x))
                self.assertEqual(c2bool(ce[i]),    (yield dut.ce))
                yield
        dut = SDPHYClocker()
        run_simulation(dut, gen(dut))

    def test_phyr_cmd(self):
        def stim_gen(dut):
            yield dut.pads_in.valid.eq(1)
            #      ---s+0x55--0x00----0xff----0x00----
            cmd = "---_-_-_-_-________--------________"
            for i in range(len(cmd)):
                yield dut.pads_in.cmd.i.eq(c2bool(cmd[i]))
                yield
        def check_gen(dut):
            data = [0x55, 0x00, 0xff]
            yield dut.source.ready.eq(1)
            for i in range(len(data)):
                while (yield dut.source.valid) == 0:
                    yield
                self.assertEqual(data[i], (yield dut.source.data))
                yield
        dut = SDPHYR(cmd=True)
        run_simulation(dut, [stim_gen(dut), check_gen(dut)])

    def test_phyr_data(self):
        def stim_gen(dut):
            data = [0xf, 0xf, 0x0, 0x5, 0xa, 0x5, 0x1, 0x2, 0x3]
            yield dut.pads_in.valid.eq(1)
            for i in range(len(data)):
                yield dut.pads_in.data.i.eq(data[i])
                yield
        def check_gen(dut):
            data = [0x5a, 0x51, 0x23]
            yield dut.source.ready.eq(1)
            for i in range(len(data)):
                while (yield dut.source.valid) == 0:
                    yield
                self.assertEqual(data[i], (yield dut.source.data))
                yield
        dut = SDPHYR(data=True, data_width=4, skip_start_bit=True)
        run_simulation(dut, [stim_gen(dut), check_gen(dut)])

    def test_phyinit(self):
        def gen(dut):
            for n in range(4):
                yield dut.initialize.re.eq(1)
                yield
                yield dut.initialize.re.eq(0)
                yield dut.pads_out.ready.eq(1)
                clk   = "_" + "-"*80 + "__"
                for i in range(len(clk)):
                    self.assertEqual(c2bool(clk[i]), (yield dut.pads_out.clk))
                    yield
        dut = SDPHYInit()
        run_simulation(dut, [gen(dut)])

    def test_phycmdw(self):
        def stim_gen(dut):
            data = [0x55, 0x00, 0xff]
            yield dut.sink.valid.eq(1)
            for i in range(len(data)):
                yield dut.sink.data.eq(data[i])
                while (yield dut.sink.ready) == 0:
                    yield
                yield
        def check_gen(dut):
            yield dut.pads_out.ready.eq(1)
            #        ---0x55----0x00------0xff----
            cmd_o  = "___-_-_-_-__________--------"
            cmd_oe = "__--------_--------_--------"
            for i in range(len(cmd_o)):
                self.assertEqual(c2bool(cmd_o[i]),  (yield dut.pads_out.cmd.o))
                self.assertEqual(c2bool(cmd_oe[i]), (yield dut.pads_out.cmd.oe))
                yield
        dut = SDPHYCMDW()
        run_simulation(dut, [stim_gen(dut), check_gen(dut)])

    def test_phycmdr(self):
        pass

    def test_phycrc(self):
        pass

    def test_phydataw(self):
        pass

    def test_phydatar(self):
        pass
