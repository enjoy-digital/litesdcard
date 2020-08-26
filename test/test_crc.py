#
# This file is part of LiteSDCard.
#
# Copyright (c) 2020 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import unittest
import random

from migen import *

from litesdcard.crc import *

def bytes2dats(bytes):
    d = ["" for i in range(4)]
    # bytes -> dat bits
    for b in _bytes:
        for i in range(4):
            d[i] += str((b >> (4*1 + i)) & 0x1)
            d[i] += str((b >> (4*0 + i)) & 0x1)
    # dat bits -> dat value
    for i in range(4):
        d[i] = int(d[i], 2)
    return d

def dats2bytes(dats):
    assert len(dats) == 4
    # dat value -> dat bits
    b = [list("{:b}".format(dats[i])) for i in range(4)]
    if len(b[0]) % 2 != 0:
        for i in range(4):
            b[i].insert(0, 0)
    # dat bits -> bytes
    _b = []
    while len(b[0]):
        v = 0
        for i in range(2):
            v |= (int(b[0].pop(0)) << 4*(1-i) + 0)
            v |= (int(b[1].pop(0)) << 4*(1-i) + 1)
            v |= (int(b[2].pop(0)) << 4*(1-i) + 2)
            v |= (int(b[3].pop(0)) << 4*(1-i) + 3)
        _b.append(v)
    return _b

class TestCRC(unittest.TestCase):
    def crc_inserter_test(self, data, crc,
        valid_random=50,
        ready_random=50):
        def stim_gen(dut):
            prng = random.Random(42)
            for i in range(len(data)):
                while prng.randrange(100) < valid_random:
                    yield
                yield dut.sink.valid.eq(1)
                if (i == len(data) - 1):
                    yield dut.sink.last.eq(1)
                yield dut.sink.data.eq(data[i])
                yield
                while (yield dut.sink.ready) == 0:
                    yield
                yield dut.sink.valid.eq(0)
                yield dut.sink.last.eq(0)
            yield

        def check_gen(dut):
            prng = random.Random(42)
            data_crc = data + dats2bytes(crc)
            for i in range(len(data_crc)):
                yield dut.source.ready.eq(0)
                yield
                while (yield dut.source.valid) == 0:
                    yield
                while prng.randrange(100) < ready_random:
                    yield
                yield dut.source.ready.eq(1)
                #print("{:02x} vs {:02x}".format(data_crc[i], (yield dut.source.data)))
                self.assertEqual(data_crc[i], (yield dut.source.data))
                self.assertEqual((yield dut.source.last), int(i == len(data_crc) - 1))
                yield

        dut = CRC16Inserter()
        run_simulation(dut, [stim_gen(dut), check_gen(dut)], vcd_name="sim.vcd")

    def test_crc_inserter_ones(self):
        self.crc_inserter_test(data=[0xff]*512*4, crc=[0x7fa1, 0x7fa1, 0x7fa1, 0x7fa1])

    def test_crc_inserter_tuning_block(self):
        from litesdcard.common import SDCARD_TUNING_BLOCK
        data = []
        for word in SDCARD_TUNING_BLOCK:
            data += word.to_bytes(4, "big")
        self.crc_inserter_test(data=data, crc=[0xe946, 0x8d06, 0xa2e5, 0xc59f])
