#
# This file is part of LiteSDCard.
#
# Copyright (c) 2020 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import unittest

from migen import *

from litesdcard.phy import *
from litesdcard.phy import _sdpads_layout

def c2bool(c):
    return {"-": 1, "_": 0}[c]


class TestPHY(unittest.TestCase):
    def test_clocker_div0(self):
        # Effective Div = 2.
        def gen(dut):
            clk   = "__-_-_-_-_-_-_-_"
            ce    = "_-_-_-_-_-_-_-_-"
            for i in range(len(clk)):
                self.assertEqual(c2bool(clk[i]),   (yield dut.clk))
                self.assertEqual(c2bool(ce[i]),    (yield dut.ce))
                yield
        dut = SDPHYClocker()
        dut.divider.storage.reset = 0
        run_simulation(dut, gen(dut))

    def test_clocker_div1(self):
        # Effective Div = 2.
        def gen(dut):
            clk   = "__-_-_-_-_-_-_-_"
            ce    = "_-_-_-_-_-_-_-_-"
            for i in range(len(clk)):
                self.assertEqual(c2bool(clk[i]),   (yield dut.clk))
                self.assertEqual(c2bool(ce[i]),    (yield dut.ce))
                yield
        dut = SDPHYClocker()
        dut.divider.storage.reset = 1
        run_simulation(dut, gen(dut))

    def test_clocker_div2(self):
        # Effective Div = 2.
        def gen(dut):
            clk   = "__-_-_-_-_-_-_-_"
            ce    = "_-_-_-_-_-_-_-_-"
            for i in range(len(clk)):
                self.assertEqual(c2bool(clk[i]),   (yield dut.clk))
                self.assertEqual(c2bool(ce[i]),    (yield dut.ce))
                yield
        dut = SDPHYClocker()
        dut.divider.storage.reset = 2
        run_simulation(dut, gen(dut))

    def test_clocker_div3(self):
        # Effective Div = 4.
        def gen(dut):
            clk   = "___--__--__--__--"
            ce    = "_-___-___-___-___"
            for i in range(len(clk)):
                self.assertEqual(c2bool(clk[i]),   (yield dut.clk))
                self.assertEqual(c2bool(ce[i]),    (yield dut.ce))
                yield
        dut = SDPHYClocker()
        dut.divider.storage.reset = 3
        run_simulation(dut, gen(dut))

    def test_clocker_div4(self):
        # Effective Div = 4.
        def gen(dut):
            clk   = "___--__--__--__--"
            ce    = "_-___-___-___-___"
            for i in range(len(clk)):
                self.assertEqual(c2bool(clk[i]),   (yield dut.clk))
                self.assertEqual(c2bool(ce[i]),    (yield dut.ce))
                yield
        dut = SDPHYClocker()
        dut.divider.storage.reset = 4
        run_simulation(dut, gen(dut))

    def test_clocker_div5(self):
        # Effective Div = 6.
        def gen(dut):
            clk   = "____---___---___---_"
            ce    = "_-_____-_____-_____-"
            for i in range(len(clk)):
                self.assertEqual(c2bool(clk[i]),   (yield dut.clk))
                self.assertEqual(c2bool(ce[i]),    (yield dut.ce))
                yield
        dut = SDPHYClocker()
        dut.divider.storage.reset = 5
        run_simulation(dut, gen(dut))

    def test_clocker_div8(self):
        # Effective Div = 8.
        def gen(dut):
            yield dut.divider.storage.eq(8)
            clk   = "_____----____----___"
            ce    = "_-_______-_______-__"
            for i in range(len(clk)):
                self.assertEqual(c2bool(clk[i]),   (yield dut.clk))
                self.assertEqual(c2bool(ce[i]),    (yield dut.ce))
                yield
        dut = SDPHYClocker()
        dut.divider.storage.reset = 8
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
        dut = SDPHYR(_sdpads_layout(4), cmd=True)
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
        dut = SDPHYR(_sdpads_layout(4), data=True, data_width=4, skip_start_bit=True)
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
        dut = SDPHYInit(_sdpads_layout(4))
        run_simulation(dut, [gen(dut)])

    def test_phycmdw(self):
        def stim_gen(dut):
            data = [0x55, 0x00, 0xff]
            yield dut.sink.valid.eq(1)
            for i in range(len(data)):
                yield dut.sink.data.eq(data[i])
                yield dut.sink.last.eq(i == len(data) - 1)
                yield
                while (yield dut.sink.ready) == 0:
                    yield
        def check_gen(dut):
            yield dut.pads_out.ready.eq(1)
            #        ---0x55----0x00----0xff----
            cmd_o  = "___-_-_-_-________--------"
            cmd_oe = "__------------------------"
            for i in range(len(cmd_o)):
                self.assertEqual(c2bool(cmd_o[i]),  (yield dut.pads_out.cmd.o))
                self.assertEqual(c2bool(cmd_oe[i]), (yield dut.pads_out.cmd.oe))
                yield
        dut = SDPHYCMDW(_sdpads_layout(4))
        run_simulation(dut, [stim_gen(dut), check_gen(dut)])

    def test_phycmdr(self):
        def stim_gen(dut):
            yield dut.pads_in.valid.eq(1)
            #      ---s+0x55--0x00----0xff----0x00----
            cmd = "---_-_-_-_-________--------________"
            for i in range(len(cmd)):
                yield dut.pads_in.cmd.i.eq(c2bool(cmd[i]))
                yield
        def check_gen(dut):
            yield dut.pads_out.ready.eq(1)
            yield dut.sink.valid.eq(1)
            yield dut.sink.length.eq(3)
            yield dut.source.ready.eq(1)
            data = [0x55, 0x00, 0xff]
            last = [0b0,  0b0,  0b1]
            yield dut.source.ready.eq(1)
            for i in range(len(data)):
                while (yield dut.source.valid) == 0:
                    yield
                self.assertEqual(data[i], (yield dut.source.data))
                self.assertEqual(last[i], (yield dut.source.last))
                yield
        cmdw = Module()
        cmdw.done = 1
        dut  = SDPHYCMDR(_sdpads_layout(4), 1e6, 5e-3, cmdw)
        run_simulation(dut, [stim_gen(dut), check_gen(dut)])

    def test_phycrc(self):
        pass

    def test_phydataw(self):
        pass

    def test_phydatar(self):
        pass

if __name__ == '__main__':
        unittest.main()
