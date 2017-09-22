#!/usr/bin/env python3

import sys

from litex.gen import *
from litex.gen.genlib.resetsync import AsyncResetSynchronizer

from litex.build.generic_platform import *

from litex.soc.interconnect import stream
from litex.soc.cores.uart import UARTWishboneBridge

from litex.soc.integration.soc_core import *
from litex.soc.integration.builder import *

from litesdcard.phy import SDPHY
from litesdcard.core import SDCore
from litesdcard.ram import RAMReader, RAMWriter
from litesdcard.convert import Stream32to8, Stream8to32

from litesdcard.emulator import SDEmulator, _sdemulator_pads

from litex.boards.platforms import arty

from litescope import LiteScopeAnalyzer


_sd_io = [
    ("sdcard", 0,
        Subsignal("data", Pins("V11 T13 U13 U12"), Misc("PULLUP")),
        Subsignal("cmd", Pins("V10"), Misc("PULLUP")),
        Subsignal("clk", Pins("V12")),
        IOStandard("LVCMOS33"), Misc("SLEW=FAST")
    )
]


class _CRG(Module):
    def __init__(self, platform):
        self.clock_domains.cd_sys = ClockDomain()
        self.clock_domains.cd_sd = ClockDomain()
        self.clock_domains.cd_sd_fb = ClockDomain()

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

                     # 25 MHz
                     p_CLKOUT0_DIVIDE=64, p_CLKOUT0_PHASE=0.0,
                     o_CLKOUT0=pll_sys
            ),
            Instance("BUFG", i_I=pll_sys, o_O=self.cd_sys.clk),
            AsyncResetSynchronizer(self.cd_sys, ~pll_locked | rst),
        ]

        # XXX remove
        self.comb += [
            self.cd_sd.clk.eq(ClockSignal()),
            self.cd_sd.rst.eq(ResetSignal())
        ]


class SDSoC(SoCCore):
    csr_map = {
        "sdphy":      20,
        "sdcore":     21,
        "sdemulator": 22,
        "ramreader":  23,
        "ramwriter":  24,
        "analyzer":   30
    }
    csr_map.update(SoCCore.csr_map)

    def __init__(self, with_emulator=False, with_analyzer=True):
        platform = arty.Platform()
        platform.add_extension(_sd_io)
        clk_freq = int(25e6)
        sd_freq = int(25e6)
        SoCCore.__init__(self, platform,
                         clk_freq=clk_freq,
                         cpu_type=None,
                         csr_data_width=32,
                         with_uart=False,
                         with_timer=False,
                         ident="SDCard Test SoC",
                         ident_version=True,
                         integrated_sram_size=1024)

        self.submodules.crg = _CRG(platform)

        self.add_cpu_or_bridge(UARTWishboneBridge(platform.request("serial"), clk_freq, baudrate=115200))
        self.add_wb_master(self.cpu_or_bridge.wishbone)

        if with_emulator:
            sdcard_pads = _sdemulator_pads()
            self.submodules.sdemulator = SDEmulator(platform, sdcard_pads)
        else:
            sdcard_pads = platform.request('sdcard')

        self.submodules.sdphy = SDPHY(sdcard_pads, platform.device)
        self.submodules.sdcore = SDCore(self.sdphy)

        self.submodules.ramreader = RAMReader()
        self.submodules.ramwriter = RAMWriter()
        self.add_wb_master(self.ramreader.bus)
        self.add_wb_master(self.ramwriter.bus)

        self.submodules.stream32to8 = Stream32to8()
        self.submodules.stream8to32 = Stream8to32()

        self.submodules.tx_fifo = ClockDomainsRenamer({"write": "sys", "read": "sd"})(
            stream.AsyncFIFO(self.sdcore.sink.description, 4))
        self.submodules.rx_fifo = ClockDomainsRenamer({"write": "sd", "read": "sys"})(
            stream.AsyncFIFO(self.sdcore.source.description, 4))

        self.comb += [
            self.sdcore.source.connect(self.rx_fifo.sink),
            self.rx_fifo.source.connect(self.stream8to32.sink),
            self.stream8to32.source.connect(self.ramwriter.sink),

            self.ramreader.source.connect(self.stream32to8.sink),
            self.stream32to8.source.connect(self.tx_fifo.sink),
            self.tx_fifo.source.connect(self.sdcore.sink)
        ]

        self.platform.add_period_constraint(self.crg.cd_sys.clk, 1e9/clk_freq)
        self.platform.add_period_constraint(self.crg.cd_sd.clk, 1e9/sd_freq)
        self.platform.add_period_constraint(self.crg.cd_sd_fb.clk, 1e9/sd_freq)

        self.crg.cd_sys.clk.attr.add("keep")
        self.crg.cd_sd.clk.attr.add("keep")
        self.crg.cd_sd_fb.clk.attr.add("keep")
        self.platform.add_false_path_constraints(
            self.crg.cd_sys.clk,
            self.crg.cd_sd.clk,
            self.crg.cd_sd_fb.clk)

        # analyzer
        if with_analyzer:
            phy_group = [
                self.sdphy.sdpads,
                self.sdphy.cmdw.sink,
                self.sdphy.cmdr.sink,
                self.sdphy.cmdr.source,
                self.sdphy.dataw.sink,
                self.sdphy.datar.sink,
                self.sdphy.datar.source
            ]

            dummy_group = [
                Signal(),
                Signal()
            ]

            analyzer_signals = {
                0 : phy_group,
                1 : dummy_group
            }
            self.submodules.analyzer = LiteScopeAnalyzer(analyzer_signals, 256, cd="sd", cd_ratio=4)

    def do_exit(self, vns):
        if hasattr(self, "analyzer"):
            self.analyzer.export_csv(vns, "../test/analyzer.csv")


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == "emulator":
            soc = SDSoC(with_emulator=True)
        else:
            raise ValueError
    else:
        soc = soc = SDSoC()
    builder = Builder(soc, output_dir="build", csr_csv="../test/csr.csv")
    vns = builder.build()
    soc.do_exit(vns)


if __name__ == "__main__":
    main()
