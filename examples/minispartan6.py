#!/usr/bin/env python3

import sys
from fractions import Fraction

from migen import *
from migen.genlib.resetsync import AsyncResetSynchronizer

from litex.build.generic_platform import *
from litex.build.openocd import OpenOCD

from litex.soc.interconnect import stream
from litex.soc.cores.uart import UARTWishboneBridge
from litex.soc.cores.timer import Timer

from litex.soc.interconnect.csr import *
from litex.soc.integration.soc_core import *
from litex.soc.integration.builder import *
from litex.soc.interconnect import wishbone

from litesdcard.phy import SDPHY
from litesdcard.clocker import SDClockerS6
from litesdcard.core import SDCore
from litesdcard.bist import BISTBlockGenerator, BISTBlockChecker

from litesdcard.emulator import SDEmulator, _sdemulator_pads

from litex.boards.platforms import minispartan6

from litescope import LiteScopeAnalyzer


_sd_io = [
    ("sdcard", 0,
        Subsignal("data", Pins("M10 L10 J11 K12"), Misc("PULLUP")),
        Subsignal("cmd", Pins("K11"), Misc("PULLUP")),
        Subsignal("clk", Pins("L12")),
        IOStandard("LVCMOS33"), Misc("SLEW=FAST")
    )
]


class _CRG(Module):
    def __init__(self, platform, clk_freq):
        self.clock_domains.cd_sys = ClockDomain()

        f0 = 32*1000000
        clk32 = platform.request("clk32")
        clk32a = Signal()
        self.specials += Instance("IBUFG", i_I=clk32, o_O=clk32a)
        clk32b = Signal()
        self.specials += Instance("BUFIO2", p_DIVIDE=1,
                                  p_DIVIDE_BYPASS="TRUE", p_I_INVERT="FALSE",
                                  i_I=clk32a, o_DIVCLK=clk32b)
        f = Fraction(int(clk_freq), int(f0))
        n, m, p = f.denominator, f.numerator, 16
        assert f0/n*m == clk_freq
        pll_lckd = Signal()
        pll_fb = Signal()
        pll = Signal(6)
        self.specials.pll = Instance("PLL_ADV", p_SIM_DEVICE="SPARTAN6",
                                     p_BANDWIDTH="OPTIMIZED", p_COMPENSATION="INTERNAL",
                                     p_REF_JITTER=.01, p_CLK_FEEDBACK="CLKFBOUT",
                                     i_DADDR=0, i_DCLK=0, i_DEN=0, i_DI=0, i_DWE=0, i_RST=0, i_REL=0,
                                     p_DIVCLK_DIVIDE=1, p_CLKFBOUT_MULT=m*p//n, p_CLKFBOUT_PHASE=0.,
                                     i_CLKIN1=clk32b, i_CLKIN2=0, i_CLKINSEL=1,
                                     p_CLKIN1_PERIOD=1000000000/f0, p_CLKIN2_PERIOD=0.,
                                     i_CLKFBIN=pll_fb, o_CLKFBOUT=pll_fb, o_LOCKED=pll_lckd,
                                     o_CLKOUT0=pll[0], p_CLKOUT0_DUTY_CYCLE=.5,
                                     o_CLKOUT1=pll[1], p_CLKOUT1_DUTY_CYCLE=.5,
                                     o_CLKOUT2=pll[2], p_CLKOUT2_DUTY_CYCLE=.5,
                                     o_CLKOUT3=pll[3], p_CLKOUT3_DUTY_CYCLE=.5,
                                     o_CLKOUT4=pll[4], p_CLKOUT4_DUTY_CYCLE=.5,
                                     o_CLKOUT5=pll[5], p_CLKOUT5_DUTY_CYCLE=.5,
                                     p_CLKOUT0_PHASE=0., p_CLKOUT0_DIVIDE=p//1, # sys
                                     p_CLKOUT1_PHASE=0., p_CLKOUT1_DIVIDE=p//1,
                                     p_CLKOUT2_PHASE=0., p_CLKOUT2_DIVIDE=p//1,
                                     p_CLKOUT3_PHASE=0., p_CLKOUT3_DIVIDE=p//1,
                                     p_CLKOUT4_PHASE=0., p_CLKOUT4_DIVIDE=p//1,
                                     p_CLKOUT5_PHASE=0., p_CLKOUT5_DIVIDE=p//1,
        )
        self.specials += Instance("BUFG", i_I=pll[0], o_O=self.cd_sys.clk)
        self.specials += AsyncResetSynchronizer(self.cd_sys, ~pll_lckd)


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
        platform = minispartan6.Platform(device="xc6slx25")
        platform.add_extension(_sd_io)
        clk_freq = int(50e6)
        sd_freq = int(140e6)
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

        self.submodules.crg = _CRG(platform, clk_freq)

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
        self.submodules.sdclk = SDClockerS6()
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

        self.crg.cd_sys.clk.attr.add("keep")
        self.sdclk.cd_sd.clk.attr.add("keep")
        self.platform.add_false_path_constraints(
            self.crg.cd_sys.clk,
            self.sdclk.cd_sd.clk)

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
        prog = OpenOCD("board/minispartan6.cfg")
        prog.load_bitstream("build/gateware/top.bit")


if __name__ == "__main__":
    main()
