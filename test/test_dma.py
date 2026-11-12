#
# This file is part of LiteSDCard.
#
# Copyright (c) 2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import unittest

from migen import *

from litex.soc.interconnect import wishbone

from litesdcard.frontend.dma import SDBlock2MemDMA, SDMem2BlockDMA


class _DUTMem2Block(Module):
    def __init__(self, init):
        bus = wishbone.Interface(data_width=32, adr_width=30)
        self.submodules.dma = SDMem2BlockDMA(bus, endianness="little")
        self.submodules.sram = wishbone.SRAM(64, init=init, bus=bus)


class _DUTBlock2Mem(Module):
    def __init__(self):
        bus = wishbone.Interface(data_width=32, adr_width=30)
        self.submodules.dma = SDBlock2MemDMA(bus, endianness="little")
        self.submodules.sram = wishbone.SRAM(64, bus=bus)


def _words(data):
    return [int.from_bytes(bytes(data[i:i+4]), "little") for i in range(0, len(data), 4)]


class TestDMA(unittest.TestCase):
    def test_mem2block_disable_flushes(self):
        data = list(range(16)) + list(range(0x80, 0x90))
        dut  = _DUTMem2Block(_words(data))
        out  = []

        def gen():
            dma = dut.dma.dma
            # First transfer: 16 bytes, only 8 consumed before the DMA is disabled.
            yield dma._base.storage.eq(0)
            yield dma._length.storage.eq(16)
            yield dma._enable.storage.eq(1)
            for _ in range(64):
                yield
            yield dut.dma.source.ready.eq(1)
            n = 0
            for _ in range(64):
                if (yield dut.dma.source.valid):
                    n += 1
                yield
                if n == 8:
                    break
            yield dut.dma.source.ready.eq(0)
            yield dma._enable.storage.eq(0)
            for _ in range(8):
                yield
            # Second transfer: 16 bytes from the second buffer.
            yield dma._base.storage.eq(16)
            yield dma._length.storage.eq(16)
            yield dma._enable.storage.eq(1)
            for _ in range(64):
                yield
            yield dut.dma.source.ready.eq(1)
            yield
            for _ in range(64):
                if (yield dut.dma.source.valid):
                    out.append((yield dut.dma.source.data))
                yield
                if len(out) == 16:
                    break

        run_simulation(dut, gen())
        self.assertEqual(out, data[16:])

    def test_block2mem_disable_flushes(self):
        dut = _DUTBlock2Mem()

        def send(data):
            for i, d in enumerate(data):
                yield dut.dma.sink.valid.eq(1)
                yield dut.dma.sink.first.eq(i == 0)
                yield dut.dma.sink.data.eq(d)
                yield
                for _ in range(64):
                    if (yield dut.dma.sink.ready):
                        break
                    yield
            yield dut.dma.sink.valid.eq(0)

        def gen():
            dma = dut.dma.dma
            # First transfer: 3 bytes (partial word left in the converter), then disabled.
            yield dma._base.storage.eq(0)
            yield dma._length.storage.eq(16)
            yield dma._enable.storage.eq(1)
            yield
            yield from send([0xaa, 0xbb, 0xcc])
            for _ in range(16):
                yield
            yield dma._enable.storage.eq(0)
            for _ in range(8):
                yield
            # Second transfer: 8 bytes at address 0x20.
            yield dma._base.storage.eq(0x20)
            yield dma._length.storage.eq(8)
            yield dma._enable.storage.eq(1)
            yield
            yield from send(list(range(8)))
            for _ in range(64):
                if (yield dma._done.status):
                    break
                yield
            mem = []
            for i in range(2):
                mem.append((yield dut.sram.mem[8 + i]))
            self.assertEqual(mem, _words(list(range(8))))

        run_simulation(dut, gen())


if __name__ == "__main__":
    unittest.main()
