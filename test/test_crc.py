#
# This file is part of LiteSDCard.
#
# Copyright (c) 2020 Florent Kermarrec <florent@enjoy-digital.fr>
# Copyright (c) 2025 Fin Maaß <f.maass@vogl-electronic.com>
# SPDX-License-Identifier: BSD-2-Clause

import unittest

from migen import *

from litesdcard.crc import *

class TestCRC(unittest.TestCase):
    def crc_inserter_test(self, data, crc, data_pads_width=4):
        data_pads = Signal(data_pads_width)
        count = Signal(8)
        data = Constant(int.from_bytes(data, "big"), len(data)*8)
        data_crc = Constant(crc, 16)
        def gen(dut):
            yield dut.reset.eq(1)
            yield
            yield dut.reset.eq(0)
            yield
            for i in range(len(data)):
                yield dut.enable.eq(1)
                yield data_pads.eq(Replicate(data[i], len(data_pads)))
                yield
                yield dut.enable.eq(0)
                yield
            # Check CRC calculation
            yield
            for i in range(len(data_pads)):
                # print("data_{} crc: {:04x}".format(i, (yield dut.crc[i])))
                self.assertEqual(crc, (yield dut.crc[i]))
            for i in range(16):
                yield count.eq(i)
                yield
                data_crc_n = (yield Replicate(data_crc[16-1-i], len(data_pads)))
                data_pads_out_n = (yield dut.data_pads_out)
                # print("{:02x} vs {:02x}".format(data_crc_n, data_pads_out_n))
                self.assertEqual(data_crc_n, data_pads_out_n)
                yield

        dut = CRC16(data_pads, count)
        run_simulation(dut, gen(dut))

    def test_crc_inserter_ones(self):
        self.crc_inserter_test(data=[0xff]*512, crc=0x7fa1, data_pads_width=1)
        self.crc_inserter_test(data=[0xff]*512, crc=0x7fa1, data_pads_width=4)
        self.crc_inserter_test(data=[0xff]*512, crc=0x7fa1, data_pads_width=8)

    def test_crc_inserter_tuning_block(self):
        # 4-bit tuning block, split on the lines as SDPHYDATAW does (high nibble first, MSB on
        # DAT3): each line has its own CRC16.
        from litesdcard.common import SDCARD_TUNING_BLOCK
        data = []
        for word in SDCARD_TUNING_BLOCK:
            data += word.to_bytes(4, "big")
        nibbles = []
        for byte in data:
            nibbles += [byte >> 4, byte & 0xf]
        crcs = {3: 0xc59f, 2: 0xa2e5, 1: 0x8d06, 0: 0xe946}

        data_pads = Signal(4)
        count     = Signal(8)
        def gen(dut):
            yield dut.reset.eq(1)
            yield
            yield dut.reset.eq(0)
            yield
            for nibble in nibbles:
                yield dut.enable.eq(1)
                yield data_pads.eq(nibble)
                yield
            yield dut.enable.eq(0)
            yield
            for i in range(4):
                self.assertEqual((yield dut.crc[i]), crcs[i])
            # CRC bits on the lines, MSB first.
            for i in range(16):
                yield count.eq(i)
                yield
                expected = sum(((crcs[l] >> (15 - i)) & 1) << l for l in range(4))
                self.assertEqual((yield dut.data_pads_out), expected)

        dut = CRC16(data_pads, count)
        run_simulation(dut, gen(dut))

if __name__ == '__main__':
        unittest.main()
