#!/usr/bin/env python3

import os

from litex.build.generic_platform import *
from litex.build.xilinx import XilinxPlatform

from litex.gen import *

from litex.build.generic_platform import *

from litex.soc.interconnect import wishbone

from litex.soc.integration.soc_core import *

from litesdcard.phy import SDPHY
from litesdcard.core import SDCore
from litesdcard.ram import RAMReader, RAMWriter
from litesdcard.convert import Stream32to8, Stream8to32

from litesdcard.emulator import SDEmulator, _sdemulator_pads


_io = [("clk50", 0, Pins("X"))]


class Platform(XilinxPlatform):
    def __init__(self):
        XilinxPlatform.__init__(self, "", _io)


class _CRG(Module):
    def __init__(self, platform, clk_freq):
        self.clock_domains.cd_sys = ClockDomain()
        self.clock_domains.cd_sd_tx = ClockDomain()
        self.clock_domains.cd_sd_rx = ClockDomain()

        self.comb += [
            self.cd_sys.clk.eq(platform.request("clk50")),
            self.cd_sd_tx.clk.eq(ClockSignal()),
            self.cd_sd_tx.rst.eq(ResetSignal())
        ]


class SDTester(Module):
    def __init__(self, core):
        counter = Signal(32)
        self.sync += [
            counter.eq(counter + 1),
            If(counter[:16] == 0,
                Display("here")
            )
        ]

        self.sync += [
            core.command.re.eq(0),
            If(counter == 256,
                core.command.re.eq(1),
                Display("send command")
            )
        ]


class SDSim(Module):
    def __init__(self, platform):
        clk_freq = int(50*1000000)

        self.submodules.crg = _CRG(platform, clk_freq)

        sdcard_pads = _sdemulator_pads()
        self.submodules.sdemulator = SDEmulator(platform, sdcard_pads)
        self.submodules.sdphy = SDPHY(sdcard_pads, platform.device)
        self.submodules.sdcore = SDCore(self.sdphy)

        self.submodules.ramreader = RAMReader()
        self.submodules.ramwriter = RAMWriter()
        #self.add_wb_master(self.ramreader.bus) # FIXME
        #self.add_wb_master(self.ramwriter.bus) # FIXME

        self.submodules.stream32to8 = Stream32to8()
        self.submodules.stream8to32 = Stream8to32()

        self.comb += [
            self.sdcore.source.connect(self.stream8to32.sink),
            self.stream8to32.source.connect(self.ramwriter.sink),

            self.ramreader.source.connect(self.stream32to8.sink),
            self.stream32to8.source.connect(self.sdcore.sink)
        ]

        self.submodules.sdtester = SDTester(self.sdcore)


def clean():
    os.system("rm -f top")
    os.system("rm -f *.v *.xst *.prj *.vcd *.ucf")

def generate_top():
    platform = Platform()
    soc = SDSim(platform)
    platform.build(soc, build_dir="./", run=False)


def generate_top_tb():
    f = open("top_tb.v", "w")
    f.write("""
`timescale 1ns/1ps

module top_tb();

reg clk50;
initial clk50 = 1'b1;
always #10 clk50 = ~clk50;

top dut (
    .clk50(clk50)
);

initial begin
    $dumpfile("top.vcd");
    $dumpvars();
end

endmodule""")
    f.close()


def run_sim():
    os.system("iverilog -o top "
        "top.v "
        "top_tb.v "
        "../litesdcard/emulator/verilog/sd_common.v "
        "../litesdcard/emulator/verilog/sd_link.v "
        "../litesdcard/emulator/verilog/sd_phy.v "
        "-I ../litesdcard/emulator/verilog/ "
    )
    os.system("vvp top")

if __name__ == "__main__":
    clean()
    generate_top()
    generate_top_tb()
    run_sim()
