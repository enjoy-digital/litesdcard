#!/usr/bin/env python3

import sys

from litex.gen import *
from litex.gen.genlib.resetsync import AsyncResetSynchronizer

from litex.build.generic_platform import *
from litex.build.xilinx import VivadoProgrammer

from litex.soc.interconnect import stream
from litex.soc.cores.uart import UARTWishboneBridge

from litex.soc.interconnect.csr import *
from litex.soc.integration.soc_core import *
from litex.soc.integration.builder import *
from litex.soc.interconnect import wishbone

from litesdcard.phy import SDPHY
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


class SDCRG(Module, AutoCSR):
    def __init__(self, platform):
        self.clock_domains.cd_sys = ClockDomain()
        self.clock_domains.cd_sd = ClockDomain()
        self.clock_domains.cd_sd_fb = ClockDomain()

        self._mmcm_reset = CSRStorage()
        self._mmcm_read = CSR()
        self._mmcm_write = CSR()
        self._mmcm_drdy = CSRStatus()
        self._mmcm_adr = CSRStorage(7)
        self._mmcm_dat_w = CSRStorage(16)
        self._mmcm_dat_r = CSRStatus(16)

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

                     # 25 MHz
                     p_CLKOUT0_DIVIDE=64, p_CLKOUT0_PHASE=0.0,
                     o_CLKOUT0=pll_sys
            ),
            Instance("BUFG", i_I=pll_sys, o_O=self.cd_sys.clk),
            AsyncResetSynchronizer(self.cd_sys, ~pll_locked | rst),
        ]

        mmcm_locked = Signal()
        mmcm_fb = Signal()
        mmcm_clk0 = Signal()
        mmcm_drdy = Signal()

        self.specials += [
            Instance("MMCME2_ADV",
                p_BANDWIDTH="OPTIMIZED",
                i_RST=self._mmcm_reset.storage, o_LOCKED=mmcm_locked,

                # VCO
                p_REF_JITTER1=0.01, p_CLKIN1_PERIOD=10.0,
                p_CLKFBOUT_MULT_F=30.0, p_CLKFBOUT_PHASE=0.000, p_DIVCLK_DIVIDE=2,
                i_CLKIN1=clk100, i_CLKFBIN=mmcm_fb, o_CLKFBOUT=mmcm_fb,

                # CLK0
                p_CLKOUT0_DIVIDE_F=10.0, p_CLKOUT0_PHASE=0.000, o_CLKOUT0=mmcm_clk0,

                # DRP
                i_DCLK=ClockSignal(),
                i_DWE=self._mmcm_write.re,
                i_DEN=self._mmcm_read.re | self._mmcm_write.re,
                o_DRDY=mmcm_drdy,
                i_DADDR=self._mmcm_adr.storage,
                i_DI=self._mmcm_dat_w.storage,
                o_DO=self._mmcm_dat_r.status
            ),
            Instance("BUFG", i_I=mmcm_clk0, o_O=self.cd_sd.clk),
        ]
        self.sync += [
            If(self._mmcm_read.re | self._mmcm_write.re,
                self._mmcm_drdy.status.eq(0)
            ).Elif(mmcm_drdy,
                self._mmcm_drdy.status.eq(1)
            )
        ]
        self.comb += self.cd_sd.rst.eq(~mmcm_locked)


class SDSoC(SoCCore):
    csr_map = {
        "sdcrg":      20,
        "sdphy":      21,
        "sdcore":     22,
        "sdemulator": 23,
        "ramreader":  24,
        "ramwriter":  25,
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
        clk_freq = int(25e6)
        sd_freq = int(50e6)
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

        self.submodules.sdcrg = SDCRG(platform)
        self.submodules.sdphy = SDPHY(sdcard_pads, platform.device)
        self.submodules.sdcore = SDCore(self.sdphy)

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

        self.platform.add_period_constraint(self.sdcrg.cd_sys.clk, 1e9/clk_freq)
        self.platform.add_period_constraint(self.sdcrg.cd_sd.clk, 1e9/sd_freq)
        self.platform.add_period_constraint(self.sdcrg.cd_sd_fb.clk, 1e9/sd_freq)

        self.sdcrg.cd_sys.clk.attr.add("keep")
        self.sdcrg.cd_sd.clk.attr.add("keep")
        self.sdcrg.cd_sd_fb.clk.attr.add("keep")
        self.platform.add_false_path_constraints(
            self.sdcrg.cd_sys.clk,
            self.sdcrg.cd_sd.clk,
            self.sdcrg.cd_sd_fb.clk)

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
