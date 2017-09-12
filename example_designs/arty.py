#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from litex.gen import *
from litex.gen.genlib.resetsync import AsyncResetSynchronizer

from litex.build.generic_platform import *

from litex.soc.cores.uart import UARTWishboneBridge

from litex.soc.integration.soc_core import *
from litex.soc.integration.builder import *

from litesdcard.phy import SDPHY
from litesdcard.core import SDCore
from litesdcard.ram import RAMReader, RAMWriter
from litesdcard.convert import Stream32to8, Stream8to32

from litesdcard.emulator import SDEmulator, _sdemulator_pads

from litex.boards.platforms import arty

_sd_io = [
    ("sdcard", 0,
        Subsignal("data", Pins("V11 T13 U13 U12")),
        Subsignal("cmd", Pins("V10"), Misc("PULLUP")),
        Subsignal("clk", Pins("V12")),
        IOStandard("LVCMOS33"), Misc("SLEW=FAST")
    )
]


class _CRG(Module):
    def __init__(self, platform):
        self.clock_domains.cd_sys = ClockDomain()
        self.clock_domains.cd_sd_tx = ClockDomain()
        self.clock_domains.cd_sd_rx = ClockDomain()

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
            self.cd_sd_tx.clk.eq(ClockSignal()),
            self.cd_sd_tx.rst.eq(ResetSignal())
        ]


class SDSoC(SoCCore):
    csr_map = {
        "sdphy":      20,
        "sdcore":     21,
        "sdemulator": 22,
        "ramreader":  23,
        "ramwriter":  24
    }
    csr_map.update(SoCCore.csr_map)

    def __init__(self, with_emulator=True):
        platform = arty.Platform()
        platform.add_extension(_sd_io)
        clk_freq = 25*1000000
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

        self.comb += [
            self.sdcore.source.connect(self.stream8to32.sink),
            self.stream8to32.source.connect(self.ramwriter.sink),

            self.ramreader.source.connect(self.stream32to8.sink),
            self.stream32to8.source.connect(self.sdcore.sink)
        ]


def main():
    soc = SDSoC()
    builder = Builder(soc, output_dir="build", csr_csv="../test/csr.csv")
    builder.build()


if __name__ == "__main__":
    main()
