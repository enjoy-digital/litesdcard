#!/usr/bin/env python3

import os

from litex.build.generic_platform import *
from litex.build.xilinx import XilinxPlatform

from migen import *

from litex.build.generic_platform import *

from litex.soc.interconnect import stream
from litex.soc.interconnect import wishbone

from litex.soc.integration.soc_core import *

from litesdcard.common import *
from litesdcard.phy import SDPHY
from litesdcard.core import SDCore
from litesdcard.bist import BISTBlockGenerator, BISTBlockChecker

from litesdcard.emulator import SDEmulator, _sdemulator_pads


emulator_rca    = 0x1337
sram_base       = 0x10000000
sdemulator_base = 0x20000000


class SDTester(Module):
    def __init__(self, core, emulator, bist_generator, bist_checker, bus):
        counter = Signal(32)
        self.sync += counter.eq(counter + 1)
        self.sync += [
            core.command.re.eq(0),
            core.blocksize.re.eq(0),
            bist_generator.reset.re.eq(0),
            bist_generator.start.re.eq(0),
            bist_checker.reset.re.eq(0),
            bist_checker.start.re.eq(0),
            If(counter == 2048*1,
                Display("GO_IDLE_STATE (cmd0)"),
                core.argument.storage.eq(0x00000000),
                core.command.storage.eq((0 << 8) | SDCARD_CTRL_RESPONSE_NONE),
                core.command.re.eq(1)
            ).Elif(counter == 2048*2,
                Display("SEND_EXT_CSD (cmd8)"),
                core.argument.storage.eq(0x000001aa),
                core.command.storage.eq((8 << 8) | SDCARD_CTRL_RESPONSE_SHORT),
                core.command.re.eq(1)
            ).Elif(counter == 2048*3,
                Display("APP_CMD (cmd55)"),
                core.argument.storage.eq(0x00000000),
                core.command.storage.eq((55 << 8) | SDCARD_CTRL_RESPONSE_SHORT),
                core.command.re.eq(1)
            ).Elif(counter == 2048*4,
                Display("APP_SEND_OP_COND (acmd41)"),
                core.argument.storage.eq(0x10ff8000 | 0x60000000),
                core.command.storage.eq((41 << 8) | SDCARD_CTRL_RESPONSE_SHORT),
                core.command.re.eq(1)
            ).Elif(counter == 2048*5,
                Display("ALL_SEND_CID (cmd2)"),
                core.argument.storage.eq(0x00000000),
                core.command.storage.eq((2 << 8) | SDCARD_CTRL_RESPONSE_LONG),
                core.command.re.eq(1)
            ).Elif(counter == 2048*6,
                Display("SET_RELATIVE_CSR (cmd3)"),
                core.argument.storage.eq(0x00000000),
                core.command.storage.eq((3 << 8) | SDCARD_CTRL_RESPONSE_SHORT),
                core.command.re.eq(1)
            ).Elif(counter == 2048*7,
                Display("SET_RELATIVE_CSR (cmd10)"),
                core.argument.storage.eq(emulator_rca << 16),
                core.command.storage.eq((10 << 8) | SDCARD_CTRL_RESPONSE_LONG),
                core.command.re.eq(1)
            ).Elif(counter == 2048*8,
                Display("SET_RELATIVE_CSR (cmd9)"),
                core.argument.storage.eq(emulator_rca << 16),
                core.command.storage.eq((9 << 8) | SDCARD_CTRL_RESPONSE_LONG),
                core.command.re.eq(1)
            ).Elif(counter == 2048*9,
                Display("SELECT_CARD (cmd7)"),
                core.argument.storage.eq(emulator_rca << 16),
                core.command.storage.eq((7 << 8) | SDCARD_CTRL_RESPONSE_SHORT),
                core.command.re.eq(1)
            ).Elif(counter == 2048*10,
                Display("APP_CMD (cmd55)"),
                core.argument.storage.eq(emulator_rca << 16),
                core.command.storage.eq((55 << 8) | SDCARD_CTRL_RESPONSE_SHORT),
                core.command.re.eq(1)
            ).Elif(counter == 2048*11,
                Display("APP_SET_BUS_WIDTH (acmd6)"),
                core.argument.storage.eq(0x00000002),
                core.command.storage.eq((6 << 8) | SDCARD_CTRL_RESPONSE_SHORT),
                core.command.re.eq(1)
            ).Elif(counter == 2048*12,
                Display("APP_CMD (cmd55)"),
                core.argument.storage.eq(emulator_rca << 16),
                core.command.storage.eq((55 << 8) | SDCARD_CTRL_RESPONSE_SHORT),
                core.command.re.eq(1)
            ).Elif(counter == 2048*13,
                Display("APP_SEND_SCR (acmd51)"),
                core.argument.storage.eq(0x00000000),
                core.blocksize.storage.eq(8),
                core.blockcount.storage.eq(1),
                core.command.storage.eq((51 << 8) | SDCARD_CTRL_RESPONSE_SHORT |
                                        (SDCARD_CTRL_DATA_TRANSFER_READ << 5)),
                core.command.re.eq(1)
            ).Elif(counter == 2048*16,
                Display("READ_SINGLE_BLOCK (cmd17)"),
                core.argument.storage.eq(0x00000000),
                core.blocksize.storage.eq(512),
                core.blockcount.storage.eq(1),
                core.command.storage.eq((17 << 8) | SDCARD_CTRL_RESPONSE_SHORT |
                                        (SDCARD_CTRL_DATA_TRANSFER_READ << 5)),
                core.command.re.eq(1),
                bist_checker.start.re.eq(1),
            ).Elif(counter == 2048*17,
                emulator.ev.read.clear.eq(1),
            ).Elif(counter == 2048*18,
                emulator.ev.read.clear.eq(0),
                bist_checker.reset.re.eq(1),
            ).Elif(counter == 2048*20,
                Display("WRITE_SINGLE_BLOCK (cmd24)"),
                core.argument.storage.eq(0x00000000),
                core.blocksize.storage.eq(512),
                core.blockcount.storage.eq(1),
                core.command.storage.eq((24 << 8) | SDCARD_CTRL_RESPONSE_SHORT |
                                        (SDCARD_CTRL_DATA_TRANSFER_WRITE << 5)),
                core.command.re.eq(1),
                bist_generator.start.re.eq(1),
            ).Elif(counter == 2048*24,
                emulator.ev.write.clear.eq(1),
            ).Elif(counter == 2048*25,
                emulator.ev.write.clear.eq(0),
                 bist_generator.reset.re.eq(1),
            ).Elif(counter == 2048*28,
                Display("READ_SINGLE_BLOCK (cmd17)"),
                core.argument.storage.eq(0x00000000),
                core.blocksize.storage.eq(512),
                core.blockcount.storage.eq(1),
                core.command.storage.eq((17 << 8) | SDCARD_CTRL_RESPONSE_SHORT |
                                        (SDCARD_CTRL_DATA_TRANSFER_READ << 5)),
                core.command.re.eq(1),
                bist_checker.start.re.eq(1),
            ).Elif(counter == 2048*29,
                emulator.ev.read.clear.eq(1),
            ).Elif(counter == 2048*30,
                emulator.ev.read.clear.eq(0),
                bist_checker.reset.re.eq(1),
            ).Elif(counter == 2048*32,
                Display("WRITE_SINGLE_BLOCK (cmd24)"),
                core.argument.storage.eq(0x00000000),
                core.blocksize.storage.eq(512),
                core.blockcount.storage.eq(1),
                core.command.storage.eq((24 << 8) | SDCARD_CTRL_RESPONSE_SHORT |
                                        (SDCARD_CTRL_DATA_TRANSFER_WRITE << 5)),
                core.command.re.eq(1),
                bist_generator.start.re.eq(1),
            ).Elif(counter == 2048*36,
                emulator.ev.write.clear.eq(1),
            ).Elif(counter == 2048*37,
                emulator.ev.write.clear.eq(0),
                bist_generator.reset.re.eq(1),
            ).Elif(counter == 2048*64,
                Finish()
            )
        ]


_io = [("clk50", 0, Pins("X"))]


class Platform(XilinxPlatform):
    def __init__(self):
        XilinxPlatform.__init__(self, "", _io)


class _CRG(Module):
    def __init__(self, platform, clk_freq):
        self.clock_domains.cd_sys = ClockDomain()
        self.clock_domains.cd_por = ClockDomain(reset_less=True)
        self.clock_domains.cd_sd = ClockDomain()
        self.clock_domains.cd_sd_fb = ClockDomain()

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

        # sd_clk = sys_clk/4
        div_counter = Signal(2)
        self.sync.por += [
            div_counter.eq(div_counter + 1)
        ]
        self.comb += [
            self.cd_sd.clk.eq(div_counter[1]),
            self.cd_sd.rst.eq(ResetSignal())
        ]


class SDSim(Module):
    def __init__(self, platform):
        self.submodules.crg = _CRG(platform, int(50e6))

        # SRAM
        self.submodules.sram = wishbone.SRAM(1024)

        # SD Emulator
        sdcard_pads = _sdemulator_pads()
        self.submodules.sdemulator = ClockDomainsRenamer("sd")(
            SDEmulator(platform, sdcard_pads))

        # SD Core
        self.submodules.sdphy = SDPHY(sdcard_pads, platform.device)
        self.submodules.sdcore = SDCore(self.sdphy)

        self.submodules.bist_generator = BISTBlockGenerator(random=False)
        self.submodules.bist_checker = BISTBlockChecker(random=False)

        self.comb += [
            self.sdcore.source.connect(self.bist_checker.sink),
            self.bist_generator.source.connect(self.sdcore.sink)
        ]

        # Wishbone
        self.bus = wishbone.Interface()
        wb_masters = [
            self.bus
        ]
        wb_slaves = [
            (mem_decoder(sram_base), self.sram.bus),
            (mem_decoder(sdemulator_base), self.sdemulator.bus)
        ]
        self.submodules.wb_decoder = wishbone.InterconnectShared(wb_masters, wb_slaves, register=True)

        # Tester
        self.submodules.sdtester = SDTester(self.sdcore, self.sdemulator, self.bist_generator, self.bist_checker, self.bus)


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
