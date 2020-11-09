#!/usr/bin/env python3

#
# This file is part of LiteSDCard.
#
# Copyright (c) 2020 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import os
import argparse

from migen import *

from litex.build.generic_platform import *

from litex_boards.platforms import genesys2
from litex_boards.targets.genesys2 import BaseSoC

from litex.soc.interconnect import stream
from litex.soc.integration.builder import *



# BenchSoC -----------------------------------------------------------------------------------------

class BenchSoC(BaseSoC):
    def __init__(self, with_analyzer=False, host_ip="192.168.1.100", host_udp_port=2000):
        platform = genesys2.Platform()

        # BenchSoC ---------------------------------------------------------------------------------
        BaseSoC.__init__(self, sys_clk_freq=int(100e6),
            integrated_rom_size = 0x10000,
            integrated_rom_mode = "rw",
        )

        # SDCard ----------------------------------------------------------------------------------
        self.add_sdcard("sdcard")

        if with_analyzer:
            # Etherbone ----------------------------------------------------------------------------
            from liteeth.phy.s7rgmii import LiteEthPHYRGMII
            self.submodules.ethphy = LiteEthPHYRGMII(
                clock_pads         = self.platform.request("eth_clocks"),
                pads               = self.platform.request("eth"),
                with_hw_init_reset = False)
            self.add_csr("ethphy")
            self.add_etherbone(phy=self.ethphy)

        if with_analyzer:
            from litescope import LiteScopeAnalyzer
            analyzer_signals = [
                self.sdblock2mem.sink,
                self.sdblock2mem.bus,
            ]
            self.submodules.analyzer = LiteScopeAnalyzer(analyzer_signals,
                depth        = 2048,
                clock_domain = "sys",
                csr_csv      = "analyzer.csv")
            self.add_csr("analyzer")

# SoC Ctrl -----------------------------------------------------------------------------------------

class SoCCtrl:
    @staticmethod
    def reboot(wb):
        wb.regs.ctrl_reset.write(1)

    @staticmethod
    def load_rom(wb, filename):
        from litex.soc.integration.common import get_mem_data
        rom_data = get_mem_data(filename, "little")
        for i, data in enumerate(rom_data):
            wb.write(wb.mems.rom.base + 4*i, data)

# Build --------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="LiteSDCard Bench on Genesys2")
    parser.add_argument("--with-analyzer", action="store_true", help="Add Analyzer to Bench")
    parser.add_argument("--build",         action="store_true", help="Build bitstream")
    parser.add_argument("--load",          action="store_true", help="Load bitstream")
    parser.add_argument("--load-bios",     action="store_true", help="Load BIOS over Etherbone and reboot SoC")
    args = parser.parse_args()

    bench     = BenchSoC(with_analyzer=args.with_analyzer)
    builder   = Builder(bench, csr_csv="csr.csv")
    builder.build(run=args.build)

    if args.load:
        prog = bench.platform.create_programmer()
        prog.load_bitstream(os.path.join(builder.gateware_dir, bench.build_name + ".bit"))

    if args.load_bios:
        from litex import RemoteClient
        wb = RemoteClient()
        wb.open()
        ctrl = SoCCtrl()
        ctrl.load_rom(wb, os.path.join(builder.software_dir, "bios", "bios.bin"))
        ctrl.reboot(wb)
        wb.close()

if __name__ == "__main__":
    main()
