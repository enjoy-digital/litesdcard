#!/usr/bin/env python3

# This file is Copyright (c) 2020 Florent Kermarrec <florent@enjoy-digital.fr>
# License: BSD

import os
import argparse

from migen import *

from litex.build.generic_platform import *

from litex_boards.platforms import trellisboard
from litex_boards.targets.trellisboard import BaseSoC

from litex.soc.interconnect import stream
from litex.soc.integration.builder import *

from sampler import Sampler

# BenchSoC -----------------------------------------------------------------------------------------

class BenchSoC(BaseSoC):
    def __init__(self, with_sampler=False, host_ip="192.168.1.100", host_udp_port=2000):
        platform = trellisboard.Platform()

        # BenchSoC ---------------------------------------------------------------------------------
        BaseSoC.__init__(self, sys_clk_freq=int(75e6), integrated_rom_size=0x10000)

        # SDCard on PMODA with Digilent's Pmod TPH2 +  Pmod MicroSD --------------------------------
        _sdcard_pmod_ios = [
            ("sdcard_pmoda", 0,
                Subsignal("clk",  Pins("pmoda:3")),
                Subsignal("cmd",  Pins("pmoda:1"), Misc("PULLMODE=UP")),
                Subsignal("data", Pins("pmoda:2 pmoda:4 pmoda:5 pmoda:0"), Misc("PULLMODE=UP")),
                Misc("SLEWRATE=FAST"),
                IOStandard("LVCMOS33"),
            )
        ]
        self.platform.add_extension(_sdcard_pmod_ios)
        self.add_sdcard("sdcard_pmoda")

        if with_sampler:
            # Etherbone ----------------------------------------------------------------------------
            from liteeth.phy.ecp5rgmii import LiteEthPHYRGMII
            self.submodules.ethphy = LiteEthPHYRGMII(
                clock_pads         = self.platform.request("eth_clocks"),
                pads               = self.platform.request("eth"))
            self.add_csr("ethphy")
            self.add_etherbone(phy=self.ethphy)

            # PMODB Sampler (connected to PmodTPH2 with Pmode Cable Kit) ---------------------------
            _la_pmod_ios = [
                ("la_pmod", 0, Pins(
                    "pmodb:0 pmodb:1 pmodb:2 pmodb:3",
                    "pmodb:4 pmodb:5 pmodb:6 pmodb:7"),
                     IOStandard("LVCMOS33")
                )
            ]
            self.platform.add_extension(_la_pmod_ios)
            self.submodules.sampler = Sampler(self.platform.request("la_pmod"))
            self.add_csr("sampler")

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

            # Sampler/UDPStreamer flow -------------------------------------------------------------
            self.comb += self.sampler.source.connect(udp_cdc.sink)
            self.comb += udp_cdc.source.connect(udp_streamer.sink)
            self.comb += udp_streamer.source.connect(udp_port.sink)

# BenchPHY -----------------------------------------------------------------------------------------

class BenchPHY(BaseSoC):
    def __init__(self):
        platform = trellisboard.Platform()

        # BenchPHY ---------------------------------------------------------------------------------
        BaseSoC.__init__(self, sys_clk_freq=int(100e6), cpu_type=None, integrated_main_ram_size=0x100)

        # SDCard on PMODA with Digilent's Pmod TPH2 +  Pmod MicroSD --------------------------------
        _sdcard_pmod_ios = [
            ("sdcard_pmoda", 0,
                Subsignal("clk",  Pins("pmoda:3")),
                Subsignal("cmd",  Pins("pmoda:1"), Misc("PULLMODE=UP")),
                Subsignal("data", Pins("pmoda:2 pmoda:4 pmoda:5 pmoda:0"), Misc("PULLMODE=UP")),
                Misc("SLEWRATE=FAST"),
                IOStandard("LVCMOS33"),
            )
        ]
        self.platform.add_extension(_sdcard_pmod_ios)
        from litesdcard.phy import SDPHY
        self.submodules.sd_phy = SDPHY(self.platform.request("sdcard_pmoda"), platform.device, self.clk_freq)
        self.add_csr("sd_phy")

        # Send a command with button to verify timings ---------------------------------------------
        self.comb += [
            If(self.platform.request("user_btn", 3),
                self.sd_phy.cmdw.sink.valid.eq(1),
                self.sd_phy.cmdw.sink.data.eq(0x5a),
            )
        ]

# Build --------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="LiteSDCard Bench on Trellis Board")
    parser.add_argument("--bench",        default="soc",       help="Bench: soc (default) or phy")
    parser.add_argument("--with-sampler", action="store_true", help="Add Sampler to Bench")
    parser.add_argument("--build",        action="store_true", help="Build bitstream")
    parser.add_argument("--load",         action="store_true", help="Load bitstream")
    args = parser.parse_args()

    bench     = {"soc": BenchSoC, "phy": BenchPHY}[args.bench](with_sampler=args.with_sampler)
    builder   = Builder(bench, csr_csv="csr.csv")
    builder.build(run=args.build)

    if args.load:
        prog = bench.platform.create_programmer()
        prog.load_bitstream(os.path.join(builder.gateware_dir, bench.build_name + ".svf"))

if __name__ == "__main__":
    main()
