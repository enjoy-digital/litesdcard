#
# This file is part of LiteSDCard.
#
# Copyright (c) 2020 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import unittest

from migen import *

from litesdcard.crc import *

class TestCRC(unittest.TestCase):
    def test_crc_upstream_inserter(self):
        def stim_gen(dut):
            yield
            data = [0xff]*512*4
            yield dut.sink.valid.eq(1)
            for i in range(len(data)):
                if (i == len(data) - 1):
                    yield dut.sink.last.eq(1)
                yield dut.sink.data.eq(data[i])
                yield
            yield dut.sink.valid.eq(0)
            yield dut.sink.last.eq(0)
            yield
        def check_gen(dut):
            data = [0xff]*512*4 + [0x0f, 0xff, 0xff, 0xff, 0xf0, 0xf0, 0x00, 0x0f] # 0x7fa1
            yield dut.source.ready.eq(1)
            for i in range(len(data)):
                while (yield dut.source.valid) == 0:
                    yield
                #print("{:02x} vs {:02x}".format(data[i], (yield dut.source.data)))
                self.assertEqual(data[i], (yield dut.source.data))
                yield
        dut = CRCUpstreamInserter()
        run_simulation(dut, [stim_gen(dut), check_gen(dut)], vcd_name="sim.vcd")
