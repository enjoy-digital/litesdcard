#!/usr/bin/env python3

import os

from litex.build.generic_platform import *
from litex.build.xilinx import XilinxPlatform

from litex.gen import *

from litex.build.generic_platform import *

from litex.soc.interconnect import wishbone

from litex.soc.integration.soc_core import *

from litesdcard.common import *
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
        self.clock_domains.cd_por = ClockDomain(reset_less=True)
        self.clock_domains.cd_sd_tx = ClockDomain()
        self.clock_domains.cd_sd_rx = ClockDomain()

        clk50 = platform.request("clk50")
        rst_done = Signal()
        rst_counter = Signal(16)
        self.comb += rst_done.eq(rst_counter == 15)
        self.sync.por += If(~rst_done, rst_counter.eq(rst_counter + 1))
        self.comb += [
            self.cd_sys.clk.eq(clk50),
            self.cd_por.clk.eq(clk50),
            self.cd_sys.rst.eq(~rst_done)
        ]
        self.comb += [
            self.cd_sd_tx.clk.eq(ClockSignal()),
            self.cd_sd_tx.rst.eq(ResetSignal())
        ]

emulator_rca    = 0x1337
sram_base       = 0x10000000
sdemulator_base = 0x20000000

class SDTester(Module):
    def __init__(self, core, ramwriter, ramreader, bus):
        counter = Signal(32)
        self.sync += counter.eq(counter + 1)
        self.sync += [
            core.command.re.eq(0),
            If(counter == 512*1,
                # cmd0
                Display("cmd0 | MMC_CMD_GO_IDLE_STATE"),
                core.argument.storage.eq(0x00000000),
                core.command.storage.eq((0 << 8) | SDCARD_CTRL_RESPONSE_NONE),
                core.command.re.eq(1)
            ).Elif(counter == 512*2,
                # cmd8
                Display("cmd8 | MMC_CMD_SEND_EXT_CSD"),
                core.argument.storage.eq(0x000001aa),
                core.command.storage.eq((8 << 8) | SDCARD_CTRL_RESPONSE_SHORT),
                core.command.re.eq(1)
            ).Elif(counter == 512*4,
                # cmd55
                Display("cmd55 | MMC_CMD_APP_CMD"),
                core.argument.storage.eq(0x00000000),
                core.command.storage.eq((55 << 8) | SDCARD_CTRL_RESPONSE_SHORT),
                core.command.re.eq(1)
            ).Elif(counter == 512*5,
                # acmd41
                Display("acmd41 | SD_CMD_APP_SEND_OP_COND"),
                core.argument.storage.eq(0x10ff8000 | 0x60000000),
                core.command.storage.eq((41 << 8) | SDCARD_CTRL_RESPONSE_SHORT),
                core.command.re.eq(1)
            ).Elif(counter == 512*6,
                # cmd2
                Display("cmd2 | MMC_CMD_ALL_SEND_CID"),
                core.argument.storage.eq(0x00000000),
                core.command.storage.eq((2 << 8) | SDCARD_CTRL_RESPONSE_LONG),
                core.command.re.eq(1)
            ).Elif(counter == 512*7,
                # cmd3
                Display("cmd3 | MMC_CMD_SET_RELATIVE_CSR"),
                core.argument.storage.eq(0x00000000),
                core.command.storage.eq((3 << 8) | SDCARD_CTRL_RESPONSE_SHORT),
                core.command.re.eq(1)
            ).Elif(counter == 512*8,
                # cmd10
                Display("cmd10 | MMC_CMD_SET_RELATIVE_CSR"),
                core.argument.storage.eq(emulator_rca << 16),
                core.command.storage.eq((10 << 8) | SDCARD_CTRL_RESPONSE_LONG),
                core.command.re.eq(1)
            ).Elif(counter == 512*9,
                # cmd9
                Display("cmd9 | MMC_CMD_SET_RELATIVE_CSR"),
                core.argument.storage.eq(emulator_rca << 16),
                core.command.storage.eq((9 << 8) | SDCARD_CTRL_RESPONSE_LONG),
                core.command.re.eq(1)
            ).Elif(counter == 512*10,
                # cmd7
                Display("cmd7 | MMC_CMD_SELECT_CARD"),
                core.argument.storage.eq(emulator_rca << 16),
                core.command.storage.eq((7 << 8) | SDCARD_CTRL_RESPONSE_SHORT),
                core.command.re.eq(1)
            ).Elif(counter == 512*11,
                # cmd55
                Display("cmd55 | MMC_CMD_APP_CMD"),
                core.argument.storage.eq(emulator_rca << 16),
                core.command.storage.eq((55 << 8) | SDCARD_CTRL_RESPONSE_SHORT),
                core.command.re.eq(1)
            ).Elif(counter == 512*12, 
                # acmd6
                Display("acmd6 | SD_CMD_APP_SET_BUS_WIDTH"),
                core.argument.storage.eq(0x00000002),
                core.command.storage.eq((6 << 8) | SDCARD_CTRL_RESPONSE_SHORT),
                core.command.re.eq(1)
            ).Elif(counter == 512*13, 
                # cmd55
                Display("cmd55 | MMC_CMD_APP_CMD"),
                core.argument.storage.eq(emulator_rca << 16),
                core.command.storage.eq((55 << 8) | SDCARD_CTRL_RESPONSE_SHORT),
                core.command.re.eq(1)
            ).Elif(counter == 512*14, 
                # acmd51
                Display("acmd51 | SD_CMD_APP_SEND_SCR"),
                core.argument.storage.eq(0x00000000),
                core.blocksize.storage.eq(8-1),
                core.blockcount.storage.eq(0),
                ramwriter.address.storage.eq(sram_base//4),
                core.command.storage.eq((51 << 8) | SDCARD_CTRL_RESPONSE_SHORT |
                	                    (SDCARD_CTRL_DATA_TRANSFER_READ << 5)),
                core.command.re.eq(1)
            ).Elif(counter == 512*16,
                Finish()
            )
        ]


class SDSim(Module):
    def __init__(self, platform):
        self.submodules.crg = _CRG(platform, int(50e6))

        # SRAM
        self.submodules.sram = wishbone.SRAM(1024)

        # SD Emulator
        sdcard_pads = _sdemulator_pads()
        self.submodules.sdemulator = SDEmulator(platform, sdcard_pads)
        
        # SD Core
        self.submodules.sdphy = SDPHY(sdcard_pads, platform.device)
        self.submodules.sdcore = SDCore(self.sdphy)
        self.submodules.ramreader = RAMReader()
        self.submodules.ramwriter = RAMWriter()
        self.submodules.stream32to8 = Stream32to8()
        self.submodules.stream8to32 = Stream8to32()
        self.comb += [
            self.sdcore.source.connect(self.stream8to32.sink),
            self.stream8to32.source.connect(self.ramwriter.sink),

            self.ramreader.source.connect(self.stream32to8.sink),
            self.stream32to8.source.connect(self.sdcore.sink)
        ]

        # Wishbone
        self.bus = wishbone.Interface()
        wb_masters = [
        	self.bus,
        	self.ramreader.bus,
        	self.ramwriter.bus
        ]
        wb_slaves = [
            (mem_decoder(sram_base), self.sram.bus),
            (mem_decoder(sdemulator_base), self.sdemulator.bus)
        ]
        self.submodules.wb_decoder = wishbone.InterconnectShared(wb_masters, wb_slaves, register=True)

        # Tester
        self.submodules.sdtester = SDTester(self.sdcore, self.ramreader, self.ramwriter, self.bus)


def clean():
    os.system("rm -f top")
    os.system("rm -f *.v *.xst *.prj *.vcd *.ucf")

def generate_top():
    platform = Platform()
    soc = SDSim(platform)
    platform.build(soc, build_dir="./", run=False, regular_comb=False)


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
