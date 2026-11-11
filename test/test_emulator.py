#
# This file is part of LiteSDCard.
#
# Copyright (c) 2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import os
import tempfile
import unittest

from migen import *
from migen.fhdl.specials import Instance

from litesdcard.emulator import SDEmulator


class _DummyPlatform:
    def add_verilog_include_path(self, path):
        pass

    def add_sources(self, path, *filenames):
        pass


def _sd_link_params(dut):
    for special in dut.get_fragment().specials:
        if isinstance(special, Instance) and special.of == "sd_link":
            return {item.name: item.value for item in special.items if isinstance(item, Instance.Parameter)}


class TestEmulator(unittest.TestCase):
    def test_default_single_block_buffer(self):
        dut = SDEmulator(_DummyPlatform())
        self.assertEqual(dut.nblocks, 1)
        self.assertEqual(dut.buffer.depth, 512//4)
        self.assertEqual(dut.buffer.init, list(range(512//4)))
        self.assertEqual(_sd_link_params(dut), {})

    def test_block_store_size(self):
        size = 1024*1024
        dut  = SDEmulator(_DummyPlatform(), size=size)
        self.assertEqual(dut.nblocks, size//512)
        self.assertEqual(dut.buffer.depth, size//4)
        self.assertEqual(set(dut.buffer.init), {0})
        self.assertEqual(_sd_link_params(dut), {"CSD_C_SIZE": 1}) # (1 + 1) * 512KB.

    def test_block_store_image(self):
        data = bytes(range(256))*4 + b"\x12\x34\x56\x78"
        with tempfile.TemporaryDirectory() as d:
            image = os.path.join(d, "sdcard.img")
            with open(image, "wb") as f:
                f.write(data)
            dut = SDEmulator(_DummyPlatform(), image=image)
        self.assertEqual(dut.nblocks, 512*1024//512) # Rounded up to 512KB.
        self.assertEqual(dut.buffer.init[0], 0x00010203)
        self.assertEqual(dut.buffer.init[256], 0x12345678)
        self.assertEqual(dut.buffer.init[257], 0)
        self.assertEqual(_sd_link_params(dut), {"CSD_C_SIZE": 0})

    def test_block_store_addressing(self):
        # Word address from the PHY, block address from the Link.
        dut = SDEmulator(_DummyPlatform(), size=512*1024)
        def gen():
            yield dut.block_read_addr.eq(5)
            yield dut.block_write_addr.eq(9)
            yield
            self.assertEqual((yield dut.internal_rd_port.adr) >> 7, 5)
            self.assertEqual((yield dut.internal_wr_port.adr) >> 7, 9)
        # Only simulate the Block Store addressing (drop the Verilog instances and the store).
        dut._fragment.specials = set()
        run_simulation(dut, gen())

    def test_block_store_invalid_size(self):
        with self.assertRaises(ValueError):
            SDEmulator(_DummyPlatform(), size=1000)


if __name__ == "__main__":
    unittest.main()
