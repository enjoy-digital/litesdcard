#!/usr/bin/env python3

import sys
from fractions import Fraction

from litex.build.generic_platform import *
from litex.build.xilinx import XilinxPlatform

from litex.gen import *
from litex.gen.genlib.io import CRG
from litex.gen.genlib.resetsync import AsyncResetSynchronizer

from litex.build.generic_platform import *

from litex.soc.interconnect.csr import *
from litex.soc.interconnect import stream
from litex.soc.cores.uart import UARTWishboneBridge

from litex.soc.integration.soc_core import *
from litex.soc.integration.builder import *

from litesdcard.phy import SDPHY
from litesdcard.core import SDCore
from litesdcard.ram import RAMReader, RAMWriter
from litesdcard.convert import Stream32to8, Stream8to32

from litesdcard.emulator import SDEmulator, _sdemulator_pads

from litescope import LiteScopeAnalyzer


_io = [
    ("user_led", 0, Pins("T9"), IOStandard("LVCMOS33")),
    ("user_led", 0, Pins("R9"), IOStandard("LVCMOS33")),

    ("clk50", 0, Pins("A10"), IOStandard("LVCMOS33")),

    ("serial", 0,
        Subsignal("tx", Pins("B14"), IOStandard("LVCMOS33")),
        Subsignal("rx", Pins("A13"), IOStandard("LVCMOS33"))
    ),

    ("sdcard", 0,
        Subsignal("data", Pins("K16 J13 M16 K12"), Misc("PULLUP")),
        Subsignal("cmd", Pins("L14"), Misc("PULLUP")),
        Subsignal("clk", Pins("J12")),
        Subsignal("clkfb", Pins("J16")),
        Subsignal("sel", Pins("H14")),
        IOStandard("LVCMOS18"), Misc("SLEW=FAST"),
    ),

    ("debug", 0, Pins("R12"), IOStandard("LVCMOS18"), Misc("SLEW=FAST")),
]


class Platform(XilinxPlatform):
    default_clk_name = "clk50"
    default_clk_period = 20

    def __init__(self):
        XilinxPlatform.__init__(self, "xc6slx16-ftg256-2", _io)

    def create_programmer(self):
        pass


class SDCRG(Module, AutoCSR):
    def __init__(self, max_sd_clk=100e6):
            self._cmd_data = CSRStorage(10)
            self._send_cmd_data = CSR()
            self._send_go = CSR()
            self._status = CSRStatus(4)
            self._max_sd_clk = CSRConstant(max_sd_clk)

            self.clock_domains.cd_sd = ClockDomain()
            self.clock_domains.cd_sd_fb = ClockDomain()

            # # #

            clk_sd_unbuffered = Signal()
            sd_progdata = Signal()
            sd_progen = Signal()
            sd_progdone = Signal()

            sd_locked = Signal()

            clkfx_md_max = max(2.0/4.0, max_sd_clk/50e6)
            self._clkfx_md_max_1000 = CSRConstant(clkfx_md_max*1000.0)
            self.specials += Instance("DCM_CLKGEN",
                # parameters
                p_SPREAD_SPECTRUM="NONE",
                p_STARTUP_WAIT="FALSE",

                # reset
                i_FREEZEDCM=0,
                i_RST=ResetSignal(),

                # input
                i_CLKIN=ClockSignal(),
                p_CLKIN_PERIOD=20.0,

                # output
                p_CLKFXDV_DIVIDE=2,
                p_CLKFX_MULTIPLY=2,
                p_CLKFX_DIVIDE=4,
                p_CLKFX_MD_MAX=clkfx_md_max,
                o_CLKFX=clk_sd_unbuffered,
                o_LOCKED=sd_locked,

                # programming interface
                i_PROGCLK=ClockSignal(),
                i_PROGDATA=sd_progdata,
                i_PROGEN=sd_progen,
                o_PROGDONE=sd_progdone
            )

            remaining_bits = Signal(max=11)
            transmitting = Signal()
            self.comb += transmitting.eq(remaining_bits != 0)
            sr = Signal(10)
            self.sync += [
                If(self._send_cmd_data.re,
                    remaining_bits.eq(10),
                    sr.eq(self._cmd_data.storage)
                ).Elif(transmitting,
                    remaining_bits.eq(remaining_bits - 1),
                    sr.eq(sr[1:])
                )
            ]
            self.comb += [
                sd_progdata.eq(transmitting & sr[0]),
                sd_progen.eq(transmitting | self._send_go.re)
            ]

            # enforce gap between commands
            busy_counter = Signal(max=14)
            busy = Signal()
            self.comb += busy.eq(busy_counter != 0)
            self.sync += If(self._send_cmd_data.re,
                    busy_counter.eq(13)
                ).Elif(busy,
                    busy_counter.eq(busy_counter - 1)
                )

            self.comb += self._status.status.eq(Cat(busy, sd_progdone, sd_locked))

            self.specials += [
                Instance("BUFG", i_I=clk_sd_unbuffered, o_O=self.cd_sd.clk),
                AsyncResetSynchronizer(self.cd_sd, ~sd_locked)
            ]


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

    def __init__(self, with_emulator=False, with_analyzer=True):
        platform = Platform()
        clk_freq = int(50e6)
        sd_freq = int(100e6)
        SoCCore.__init__(self, platform,
                         clk_freq=clk_freq,
                         cpu_type=None,
                         csr_data_width=32,
                         with_uart=False,
                         with_timer=False,
                         ident="SDCard Test SoC",
                         ident_version=True,
                         integrated_sram_size=1024)

        self.submodules.crg = CRG(platform.request("clk50"))

        self.add_cpu_or_bridge(UARTWishboneBridge(platform.request("serial"), clk_freq, baudrate=115200))
        self.add_wb_master(self.cpu_or_bridge.wishbone)

        if with_emulator:
            sdcard_pads = _sdemulator_pads()
            self.submodules.sdemulator = SDEmulator(platform, sdcard_pads)
        else:
            sdcard_pads = platform.request('sdcard')

        self.submodules.sdcrg = SDCRG()
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

        self.specials += Instance("ODDR2", p_DDR_ALIGNMENT="NONE",
            p_INIT=1, p_SRTYPE="SYNC",
            i_D0=0, i_D1=1, i_S=0, i_R=0, i_CE=1,
            i_C0=ClockSignal("sd"), i_C1=~ClockSignal("sd"),
            o_Q=platform.request("debug")
        )

        self.platform.add_period_constraint(self.crg.cd_sys.clk, 1e9/clk_freq)
        self.platform.add_period_constraint(self.sdcrg.cd_sd.clk, 1e9/sd_freq)
        self.platform.add_period_constraint(self.sdcrg.cd_sd_fb.clk, 1e9/sd_freq)

        self.crg.cd_sys.clk.attr.add("keep")
        self.sdcrg.cd_sd.clk.attr.add("keep")
        self.sdcrg.cd_sd_fb.clk.attr.add("keep")
        self.platform.add_false_path_constraints(
            self.crg.cd_sys.clk,
            self.sdcrg.cd_sd.clk,
            self.sdcrg.cd_sd_fb.clk)

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
