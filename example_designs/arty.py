#!/usr/bin/env python3

import sys

from migen import *
from migen.genlib.resetsync import AsyncResetSynchronizer

from litex.build.generic_platform import *
from litex.build.xilinx import VivadoProgrammer

from litex.soc.interconnect import stream
from litex.soc.cores.uart import UARTWishboneBridge
from litex.soc.cores.timer import Timer

from litex.soc.interconnect.csr import *
from litex.soc.integration.soc_core import *
from litex.soc.integration.builder import *
from litex.soc.interconnect import wishbone

from litesdcard.phy import SDPHY
from litesdcard.clocker import SDClockerS7
from litesdcard.core import SDCore
from litesdcard.bist import BISTBlockGenerator, BISTBlockChecker

from litesdcard.emulator import SDEmulator, _sdemulator_pads

from litex.boards.platforms import arty

from litescope import LiteScopeAnalyzer


_sd_io = [
    ("sdcard", 0,
        Subsignal("data", Pins("V11 T13 U13 U12"), Misc("PULLUP True")),
        Subsignal("cmd", Pins("V10"), Misc("PULLUP True")),
        Subsignal("clk", Pins("V12")),
        IOStandard("LVCMOS33"), Misc("SLEW=FAST")
    )
]


class _CRG(Module):
    def __init__(self, platform):
        self.clock_domains.cd_sys = ClockDomain()

        # # #

        clk100 = platform.request("clk100")
        rst = ~platform.request("cpu_reset")

        pll_locked = Signal()
        pll_fb = Signal()
        pll_sys = Signal()
        self.specials += [
            Instance("PLLE2_BASE",
                     p_STARTUP_WAIT="FALSE", o_LOCKED=pll_locked,

                     # VCO @ 1600 MHz
                     p_REF_JITTER1=0.01, p_CLKIN1_PERIOD=10.0,
                     p_CLKFBOUT_MULT=16, p_DIVCLK_DIVIDE=1,
                     i_CLKIN1=clk100, i_CLKFBIN=pll_fb, o_CLKFBOUT=pll_fb,

                     # 100 MHz
                     p_CLKOUT0_DIVIDE=16, p_CLKOUT0_PHASE=0.0,
                     o_CLKOUT0=pll_sys
            ),
            Instance("BUFG", i_I=pll_sys, o_O=self.cd_sys.clk),
            AsyncResetSynchronizer(self.cd_sys, ~pll_locked | rst),
        ]


class SDSoC(SoCCore):
    csr_map = {
        "sdclk":          20,
        "sdphy":          21,
        "sdcore":         22,
        "sdtimer":        23,
        "sdemulator":     24,
        "bist_generator": 25,
        "bist_checker":   26,
        "analyzer":       30
    }
    csr_map.update(SoCCore.csr_map)

    def __init__(self, with_cpu, with_emulator, with_analyzer):
        platform = arty.Platform()
        platform.add_extension(_sd_io)
        clk_freq = int(100e6)
        sd_freq = int(100e6)
        SoCCore.__init__(self, platform,
                         clk_freq=clk_freq,
                         cpu_type="lm32" if with_cpu else None,
                         csr_data_width=32,
                         with_uart=with_cpu,
                         with_timer=with_cpu,
                         ident="SDCard Test SoC",
                         ident_version=True,
                         integrated_rom_size=0x8000 if with_cpu else 0,
                         integrated_main_ram_size=0x8000 if with_cpu else 0)

        self.submodules.crg = _CRG(platform)

        # bridge
        if not with_cpu:
            self.add_cpu_or_bridge(UARTWishboneBridge(platform.request("serial"), clk_freq, baudrate=115200))
            self.add_wb_master(self.cpu_or_bridge.wishbone)

        # emulator
        if with_emulator:
            sdcard_pads = _sdemulator_pads()
            self.submodules.sdemulator = SDEmulator(platform, sdcard_pads)
        else:
            sdcard_pads = platform.request('sdcard')

        # sd
        self.submodules.sdclk = SDClockerS7()
        self.submodules.sdphy = SDPHY(sdcard_pads, platform.device)
        self.submodules.sdcore = SDCore(self.sdphy)
        self.submodules.sdtimer = Timer()

        self.submodules.bist_generator = BISTBlockGenerator(random=True)
        self.submodules.bist_checker = BISTBlockChecker(random=True)

        self.comb += [
            self.sdcore.source.connect(self.bist_checker.sink),
            self.bist_generator.source.connect(self.sdcore.sink)
        ]

        self.platform.add_period_constraint(self.crg.cd_sys.clk, 1e9/clk_freq)
        self.platform.add_period_constraint(self.sdclk.cd_sd.clk, 1e9/sd_freq)
        self.platform.add_period_constraint(self.sdclk.cd_sd_fb.clk, 1e9/sd_freq)

        self.crg.cd_sys.clk.attr.add("keep")
        self.sdclk.cd_sd.clk.attr.add("keep")
        self.sdclk.cd_sd_fb.clk.attr.add("keep")
        self.platform.add_false_path_constraints(
            self.crg.cd_sys.clk,
            self.sdclk.cd_sd.clk,
            self.sdclk.cd_sd_fb.clk)

        # led
        led_counter = Signal(32)
        self.sync.sd += led_counter.eq(led_counter + 1)
        self.comb += platform.request("user_led", 0).eq(led_counter[26])

        # analyzer
        if with_analyzer:
            analyzer_signals = [
                self.sdphy.sdpads,
                self.sdphy.cmdw.sink,
                self.sdphy.cmdr.sink,
                self.sdphy.cmdr.source,
                self.sdphy.dataw.sink,
                self.sdphy.datar.sink,
                self.sdphy.datar.source
            ]
            self.submodules.analyzer = LiteScopeAnalyzer(analyzer_signals, 2048, cd="sd")

    def do_exit(self, vns):
        if hasattr(self, "analyzer"):
            self.analyzer.export_csv(vns, "../test/analyzer.csv")


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
        soc = SDSoC(with_cpu, with_emulator, with_analyzer)
        builder = Builder(soc, output_dir="build", csr_csv="../test/csr.csv")
        vns = builder.build()
        soc.do_exit(vns)
    elif load:
        print("[loading]...")
        prog = VivadoProgrammer()
        prog.load_bitstream("build/gateware/top.bit")


if __name__ == "__main__":
    main()
