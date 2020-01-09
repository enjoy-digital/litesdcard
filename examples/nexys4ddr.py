#!/usr/bin/env python3

# This file is Copyright (c) 2017-2020 Florent Kermarrec <florent@enjoy-digital.fr>
# This file is Copyright (c) 2019 Kees Jongenburger <kees.jongenburger@gmail.com>
# This file is Copyright (c) 2018 Rohit Kumar Singh <rohit91.2008@gmail.com>
# License: BSD

import sys

from migen import *
from migen.genlib.resetsync import AsyncResetSynchronizer

from litex.boards.platforms import nexys4ddr

from litex.build.generic_platform import *

from litex.soc.cores.clock import *
from litex.soc.interconnect import stream
from litex.soc.cores.uart import UARTWishboneBridge
from litex.soc.cores.timer import Timer

from litex.soc.interconnect.csr import *
from litex.soc.integration.soc_core import *
from litex.soc.integration.builder import *

from litesdcard.phy import SDPHY
from litesdcard.clocker import SDClockerS7
from litesdcard.core import SDCore
from litesdcard.bist import BISTBlockGenerator, BISTBlockChecker

# CRG ----------------------------------------------------------------------------------------------

class _CRG(Module):
    def __init__(self, platform, sys_clk_freq):
        self.clock_domains.cd_sys = ClockDomain()

        # # #

        clk100 = platform.request("clk100")
        platform.add_period_constraint(clk100, 1e9/100e6)

        self.submodules.pll = pll = S7PLL(speedgrade=-1)
        self.comb += pll.reset.eq(~platform.request("cpu_reset"))
        pll.register_clkin(clk100, 100e6)
        pll.create_clkout(self.cd_sys, sys_clk_freq)

# SDCardSoC ----------------------------------------------------------------------------------------

class SDCardSoC(SoCCore):
    def __init__(self, with_cpu, with_emulator, with_analyzer):
        platform = nexys4ddr.Platform()
        sys_clk_freq = int(100e6)
        sd_clk_freq  = int(100e6)

        # SoCCore ----------------------------------------------------------------------------------
        SoCCore.__init__(self, platform,
            clk_freq                 = sys_clk_freq,
            cpu_type                 = "lm32" if with_cpu else None,
            csr_data_width           = 32,
            with_uart                = with_cpu,
            with_timer               = with_cpu,
            ident                    = "SDCard Test SoC",
            ident_version            = True,
            integrated_rom_size      = 0x8000 if with_cpu else 0,
            integrated_main_ram_size = 0x8000 if with_cpu else 0
        )

        # CRG --------------------------------------------------------------------------------------
        self.submodules.crg = _CRG(platform, sys_clk_freq)

        # Serial bridge (optional) -----------------------------------------------------------------
        if not with_cpu:
            self.submodules.bridge = UARTWishboneBridge(platform.request("serial"), sys_clk_freq)
            self.add_wb_master(self.bridge.wishbone)

        # SDCard Emulator (optional) ---------------------------------------------------------------
        if with_emulator:
            from litesdcard.emulator import SDEmulator, _sdemulator_pads
            sdcard_pads = _sdemulator_pads()
            self.submodules.sdemulator = SDEmulator(platform, sdcard_pads)
            self.add_csr("sdemulator")
        else:
            sdcard_pads = platform.request('sdcard')

        # SDCard -----------------------------------------------------------------------------------
        self.comb += sdcard_pads.rst.eq(0)
        self.submodules.sdclk   = SDClockerS7()
        self.submodules.sdphy   = SDPHY(sdcard_pads, platform.device)
        self.submodules.sdcore  = SDCore(self.sdphy)
        self.submodules.sdtimer = Timer()
        self.add_csr("sdclk")
        self.add_csr("sdphy")
        self.add_csr("sdcore")
        self.add_csr("sdtimer")

        self.submodules.bist_generator = BISTBlockGenerator(random=True)
        self.submodules.bist_checker = BISTBlockChecker(random=True)
        self.add_csr("bist_generator")
        self.add_csr("bist_checker")
        self.comb += [
            self.sdcore.source.connect(self.bist_checker.sink),
            self.bist_generator.source.connect(self.sdcore.sink)
        ]
        self.platform.add_period_constraint(self.sdclk.cd_sd.clk, 1e9/sd_clk_freq)
        self.platform.add_period_constraint(self.sdclk.cd_sd_fb.clk, 1e9/sd_clk_freq)
        self.platform.add_false_path_constraints(
            self.crg.cd_sys.clk,
            self.sdclk.cd_sd.clk,
            self.sdclk.cd_sd_fb.clk)

        # Led --------------------------------------------------------------------------------------
        led_counter = Signal(32)
        self.sync.sd += led_counter.eq(led_counter + 1)
        self.comb += platform.request("user_led", 0).eq(led_counter[26])

        # Analyzer (optional) ----------------------------------------------------------------------
        if with_analyzer:
            from litescope import LiteScopeAnalyzer
            analyzer_signals = [
                self.sdphy.sdpads,
                self.sdphy.cmdw.sink,
                self.sdphy.cmdr.sink,
                self.sdphy.cmdr.source,
                self.sdphy.dataw.sink,
                self.sdphy.datar.sink,
                self.sdphy.datar.source
            ]
            self.submodules.analyzer = LiteScopeAnalyzer(analyzer_signals, 2048, clock_domain="sd",
                csr_csv="../test/analyzer.csv")
            self.add_csr("analyzer")

# Build --------------------------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    load = "load" in args
    build = not "load" in args

    if build:
        with_cpu = "cpu" in args
        with_emulator = "emulator" in args
        with_analyzer = "analyzer" in args
        print("[building]... cpu: {}, emulator: {}, analyzer: {}".format(
            with_cpu, with_emulator, with_analyzer))
        soc = SDCardSoC(with_cpu, with_emulator, with_analyzer)
        builder = Builder(soc, output_dir="build", csr_csv="../test/csr.csv")
        vns = builder.build()
    elif load:
        from litex.build.xilinx import VivadoProgrammer
        print("[loading]...")
        prog = VivadoProgrammer()
        prog.load_bitstream("build/gateware/top.bit")


if __name__ == "__main__":
    main()
