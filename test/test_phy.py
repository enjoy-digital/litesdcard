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

    def test_phyr_1b(self):
        pass

    def test_phyr_4b(self):
        pass

    def test_phyinit(self):
        pass

    def test_phycmdw(self):
        pass

    def test_phycmdr(self):
        pass

    def test_phycrc(self):
        pass

    def test_phydataw(self):
        pass

    def test_phydatar(self):
        pass
