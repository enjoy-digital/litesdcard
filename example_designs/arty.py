#!/usr/bin/env python3

import sys

from litex.gen import *
from litex.gen.genlib.resetsync import AsyncResetSynchronizer

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
from litesdcard.ram import RAMReader, RAMWriter

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


class SDSoC(SoCCore):
    csr_map = {
        "sdclk":      20,
        "sdphy":      21,
        "sdcore":     22,
        "sdtimer":    23,
        "sdemulator": 24,
        "ramreader":  25,
        "ramwriter":  26,
        "analyzer":   30
    }
    csr_map.update(SoCCore.csr_map)

    mem_map = {
        "sdsram": 0x20000000,
    }
    mem_map.update(SoCCore.mem_map)

    def __init__(self, with_cpu, with_emulator, with_analyzer):
        platform = arty.Platform()
        platform.add_extension(_sd_io)
        clk_freq = int(50e6)
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
                         integrated_sram_size=0x1000,
                         integrated_main_ram_size=0x8000 if with_cpu else 0)

        if not with_cpu:
            self.add_cpu_or_bridge(UARTWishboneBridge(platform.request("serial"), clk_freq, baudrate=115200))
            self.add_wb_master(self.cpu_or_bridge.wishbone)

        if with_emulator:
            sdcard_pads = _sdemulator_pads()
            self.submodules.sdemulator = SDEmulator(platform, sdcard_pads)
        else:
            sdcard_pads = platform.request('sdcard')

        self.submodules.sdclk = SDClockerS7(platform)
        self.submodules.sdphy = SDPHY(sdcard_pads, platform.device)
        self.submodules.sdcore = SDCore(self.sdphy)
        self.submodules.sdtimer = Timer()

        self.submodules.sdsram = wishbone.SRAM(2048)
        self.register_mem("sdsram", self.mem_map["sdsram"], self.sdsram.bus, 2048)

        self.submodules.ramreader = RAMReader()
        self.submodules.ramwriter = RAMWriter()
        self.add_wb_master(self.ramreader.bus)
        self.add_wb_master(self.ramwriter.bus)


        self.comb += [
            self.sdcore.source.connect(self.ramwriter.sink),
            self.ramreader.source.connect(self.sdcore.sink)
        ]

        self.platform.add_period_constraint(self.sdclk.cd_sys.clk, 1e9/clk_freq)
        self.platform.add_period_constraint(self.sdclk.cd_sd.clk, 1e9/sd_freq)
        self.platform.add_period_constraint(self.sdclk.cd_sd_fb.clk, 1e9/sd_freq)

        self.sdclk.cd_sys.clk.attr.add("keep")
        self.sdclk.cd_sd.clk.attr.add("keep")
        self.sdclk.cd_sd_fb.clk.attr.add("keep")
        self.platform.add_false_path_constraints(
            self.sdclk.cd_sys.clk,
            self.sdclk.cd_sd.clk,
            self.sdclk.cd_sd_fb.clk)

        led_counter = Signal(32)
        self.sync.sd += led_counter.eq(led_counter + 1)
        self.comb += platform.request("user_led", 0).eq(led_counter[26])

        self.specials += Instance("ODDR2", p_DDR_ALIGNMENT="NONE",
            p_INIT=1, p_SRTYPE="SYNC",
            i_D0=0, i_D1=1, i_S=0, i_R=0, i_CE=1,
            i_C0=ClockSignal("sd"), i_C1=~ClockSignal("sd"),
            o_Q=platform.request("pmoda")[0]
        )

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
