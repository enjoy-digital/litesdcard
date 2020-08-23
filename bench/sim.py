#!/usr/bin/env python3

#
# This file is part of LiteSDCard.
#
# Copyright (c) 2020 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import argparse

from migen import *

from litex.tools.litex_sim import *

from sampler import Sampler

# BenchSim -----------------------------------------------------------------------------------------

class BenchSim(SimSoC):
    def __init__(self, host_ip="192.168.1.100", host_udp_port=2000):
        SimSoC.__init__(self,
            cpu_type              = "vexriscv",
            integrated_rom_size   = 0x10000,
            uart_name             = "sim",
            with_sdram            = True,
            with_etherbone        = True,
            etherbone_mac_address = 0x10e2d5000001,
            etherbone_ip_address  = "192.168.1.50",
            sdram_module          = "MT48LC16M16",
            sdram_data_width      = 8,
            with_sdcard           = True,
        )

        # Sampler --------------------------------------------------------------------------------
        data = Signal(8)
        self.sync += data.eq(data + 1)
        self.submodules.sampler = Sampler(data)
        self.add_csr("sampler")

        # DRAMFIFO ---------------------------------------------------------------------------------
        from litedram.frontend.fifo import LiteDRAMFIFO
        self.submodules.fifo = LiteDRAMFIFO(
            data_width = 8,
            base       = 0x00000000,
            depth      = 0x01000000, # 16MB
            write_port = self.sdram.crossbar.get_port(mode="write", data_width=8),
            read_port  = self.sdram.crossbar.get_port(mode="read",  data_width=8),
        )

        # UDPStreamer ------------------------------------------------------------------------------
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

        # Sampler/FIFO/UDPStreamer flow ------------------------------------------------------------
        self.comb += self.sampler.source.connect(self.fifo.sink)
        self.comb += self.fifo.source.connect(udp_cdc.sink)
        self.comb += udp_cdc.source.connect(udp_streamer.sink)
        self.comb += udp_streamer.source.connect(udp_port.sink)

# Build --------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="LiteSDCard Bench Simulation")
    parser.add_argument("--trace",       action="store_true",     help="Enable Tracing")
    parser.add_argument("--trace-fst",   action="store_true",     help="Enable FST tracing (default=VCD)")
    parser.add_argument("--trace-start", default=0,               help="Cycle to start tracing")
    parser.add_argument("--trace-end",   default=-1,              help="Cycle to end tracing")
    args = parser.parse_args()

    sim_config = SimConfig(default_clk="sys_clk")
    sim_config.add_module("serial2console", "serial")
    sim_config.add_module("ethernet", "eth", args={"interface": "tap0", "ip": "192.168.1.100"})

    # SoC ------------------------------------------------------------------------------------------
    soc = BenchSim()

    # Build/Run ------------------------------------------------------------------------------------
    builder = Builder(soc, csr_csv="csr.csv")
    builder.build(sim_config=sim_config,
        trace       = args.trace,
        trace_fst   = args.trace,
        trace_start = int(args.trace_start),
        trace_end   = int(args.trace_end)
    )

if __name__ == "__main__":
    main()
