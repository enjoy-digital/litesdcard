#!/usr/bin/env python3

# This file is Copyright (c) 2020 Florent Kermarrec <florent@enjoy-digital.fr>
# License: BSD

import os
import argparse

from migen import *

from litex.build.generic_platform import *

from litex_boards.platforms import arty
from litex_boards.targets.arty import BaseSoC

from litex.soc.interconnect import stream
from litex.soc.integration.builder import *

from sampler import Sampler

# BenchSoC -----------------------------------------------------------------------------------------

class BenchSoC(BaseSoC):
    def __init__(self, with_sampler=False, with_analyzer=False, host_ip="192.168.1.100", host_udp_port=2000):
        platform = arty.Platform()

        # BenchSoC ---------------------------------------------------------------------------------
        BaseSoC.__init__(self, sys_clk_freq=int(100e6), integrated_rom_size=0x10000)

        # SDCard on PMODD with Digilent's Pmod MicroSD ---------------------------------------------
        self.platform.add_extension(arty._sdcard_pmod_io)
        self.add_sdcard("sdcard")
        self.add_constant("SDCARD_CLK_FREQ", 25000000)

        if with_sampler or with_analyzer:
            # Etherbone ----------------------------------------------------------------------------
            from liteeth.phy.mii import LiteEthPHYMII
            self.submodules.ethphy = LiteEthPHYMII(
                clock_pads         = self.platform.request("eth_clocks"),
                pads               = self.platform.request("eth"))
            self.add_csr("ethphy")
            self.add_etherbone(phy=self.ethphy)

        if with_sampler:
            # PMODB Sampler (connected to PmodTPH2 with Pmode Cable Kit) ---------------------------
            _la_pmod_ios = [
                ("la_pmod", 0, Pins(
                    "pmoda:0 pmoda:1 pmoda:2 pmoda:3",
                    "pmoda:4 pmoda:5 pmoda:6 pmoda:7"),
                     IOStandard("LVCMOS33")
                )
            ]
            self.platform.add_extension(_la_pmod_ios)
            self.submodules.sampler = Sampler(self.platform.request("la_pmod"))
            self.add_csr("sampler")

            # DRAMFIFO -----------------------------------------------------------------------------
            from litedram.frontend.fifo import LiteDRAMFIFO
            self.submodules.fifo = LiteDRAMFIFO(
                data_width = 8,
                base       = 0x00000000,
                depth      = 0x01000000, # 16MB
                write_port = self.sdram.crossbar.get_port(mode="write", data_width=8),
                read_port  = self.sdram.crossbar.get_port(mode="read",  data_width=8),
            )

            # UDPStreamer --------------------------------------------------------------------------
            from liteeth.common import convert_ip
            from liteeth.frontend.stream import LiteEthStream2UDPTX
            udp_port       = self.ethcore.udp.crossbar.get_port(host_udp_port, dw=8)
            udp_streamer   = LiteEthStream2UDPTX(
                ip_address = convert_ip(host_ip),
                udp_port   = host_udp_port,
                fifo_depth = 1024
            )
            udp_streamer   = ClockDomainsRenamer("eth_tx")(udp_streamer)
            self.submodules += udp_streamer
            udp_cdc = stream.ClockDomainCrossing([("data", 8)], "sys", "eth_tx")
            self.submodules += udp_cdc

            # Sampler/FIFO/UDPStreamer flow -------------------------------------------------------------
            self.comb += self.sampler.source.connect(self.fifo.sink)
            self.comb += self.fifo.source.connect(udp_cdc.sink)
            self.comb += udp_cdc.source.connect(udp_streamer.sink)
            self.comb += udp_streamer.source.connect(udp_port.sink)

        if with_analyzer:
            from litescope import LiteScopeAnalyzer
            analyzer_signals = []
            for m in ["init", "cmdw", "cmdr", "dataw", "datar"]:
                analyzer_signals.append(getattr(self.sdphy, m).pads_in)
                analyzer_signals.append(getattr(self.sdphy, m).pads_out)
            self.submodules.analyzer = LiteScopeAnalyzer(analyzer_signals,
                depth        = 1024,
                clock_domain = "sys",
                csr_csv      = "analyzer.csv")
            self.add_csr("analyzer")

# BenchPHY -----------------------------------------------------------------------------------------

class BenchPHY(BaseSoC):
    def __init__(self, **kwargs):
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
    parser.add_argument("--bench",         default="soc",       help="Bench: soc (default) or phy")
    parser.add_argument("--with-sampler",  action="store_true", help="Add Sampler to Bench")
    parser.add_argument("--with-analyzer", action="store_true", help="Add Analyzer to Bench")
    parser.add_argument("--build",         action="store_true", help="Build bitstream")
    parser.add_argument("--load",          action="store_true", help="Load bitstream")
    args = parser.parse_args()

    bench     = {"soc": BenchSoC, "phy": BenchPHY}[args.bench](
        with_sampler  = args.with_sampler,
        with_analyzer = args.with_analyzer,
    )
    builder   = Builder(bench, csr_csv="csr.csv")
    builder.build(run=args.build)

    if args.load:
        prog = bench.platform.create_programmer()
        prog.load_bitstream(os.path.join(builder.gateware_dir, bench.build_name + ".bit"))

if __name__ == "__main__":
    main()
