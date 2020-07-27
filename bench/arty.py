#!/usr/bin/env python3

# This file is Copyright (c) 2020 Florent Kermarrec <florent@enjoy-digital.fr>
# License: BSD

import os
import argparse

from migen import *

from litex.build.generic_platform import *

from litex_boards.platforms import arty
from litex_boards.targets.arty import BaseSoC

from litex.soc.integration.builder import *

# BenchSoC -----------------------------------------------------------------------------------------

class BenchSoC(BaseSoC):
    def __init__(self):
        platform = arty.Platform()

        # BenchSoC ---------------------------------------------------------------------------------
        BaseSoC.__init__(self, sys_clk_freq=int(100e6), integrated_rom_size=0x10000)

        # SDCard on PMODD with Digilent's Pmod MicroSD ---------------------------------------------
        self.platform.add_extension(arty._sdcard_pmod_io)
        self.add_sdcard("sdcard")

# BenchPHY -----------------------------------------------------------------------------------------

class BenchPHY(BaseSoC):
    def __init__(self):
        platform = arty.Platform()

        # BenchPHY ---------------------------------------------------------------------------------
        BaseSoC.__init__(self, sys_clk_freq=int(100e6), cpu_type=None, integrated_main_ram_size=0x100)

        # SDCard on PMODD with Digilent's Pmod MicroSD ---------------------------------------------
        self.platform.add_extension(arty._sdcard_pmod_io)
        from litesdcard.phy import SDPHY
        self.submodules.sd_phy = SDPHY(self.platform.request("sdcard"), platform.device, self.clk_freq)
        self.add_csr("sd_phy")

        # Send a command with button to verify timings ---------------------------------------------
        self.comb += [
            If(self.platform.request("user_btn", 0),
                self.sd_phy.cmdw.sink.valid.eq(1),
                self.sd_phy.cmdw.sink.data.eq(0x5a),
            )
        ]

# Build --------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="LiteSDCard Bench on Trellis Board")
    parser.add_argument("--bench", default="soc",       help="Bench: soc (default) or phy")
    parser.add_argument("--build", action="store_true", help="Build bitstream")
    parser.add_argument("--load",  action="store_true", help="Load bitstream")
    args = parser.parse_args()

    bench     = {"soc": BenchSoC, "phy": BenchPHY}[args.bench]()
    builder   = Builder(bench, csr_csv="csr.csv")
    builder.build(run=args.build)

    if args.load:
        prog = bench.platform.create_programmer()
        prog.load_bitstream(os.path.join(builder.gateware_dir, bench.build_name + ".bit"))

if __name__ == "__main__":
    main()
