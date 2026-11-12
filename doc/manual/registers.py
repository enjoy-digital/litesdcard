#
# This file is part of LiteSDCard project.
#
# Copyright (c) 2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause
#
# Register appendix of the manual: which designs tools/csr_doc.py elaborates and which register banks
# it documents (the engine is generic, part of the manual kit).

import json
import os
import sys
import tempfile

# Configurations: name -> parameters of the design. Both are the standalone core of `litesdcard_gen`
# (`LiteSDCardCore` of litesdcard/gen.py: `add_sdcard` with the two DMAs and the events) on a Lattice
# platform, elaborated without a toolchain: with the 4 data lines of the generator, then with the
# `data` subsignal of the generator resource widened to 8 lines (8-bit PHY). The strings of the
# appendix table are derived from these values (_display), so they cannot drift from the design.
PARAMS = {
    "gen_4bit" : {"vendor": "lattice", "clk_freq": 100e6, "dma_data_width": 32, "data_lines": 4},
    "gen_8bit" : {"vendor": "lattice", "clk_freq": 100e6, "dma_data_width": 32, "data_lines": 8},
}

def _display(p):
    """Appendix table cells of a configuration: the generator options, then the data lines."""
    return [f"--vendor {p['vendor']}", f"--clk-freq {p['clk_freq']/1e6:g}e6",
        f"--dma-data-width {p['dma_data_width']}",
        f"{p['data_lines']} data lines" + (" (data subsignal widened)" if p["data_lines"] != 4 else "")]

CONFIGS = {name: _display(p) for name, p in PARAMS.items()}

# A LiteX SoC puts every register of LiteSDCard in one bank named after the module (`sdcard`).
# elaborate() splits that bank by sub-module (the prefix of the register names) so that the
# appendix has one section per block; the offsets stay those of the `sdcard` bank.
SPLIT = ["phy", "core", "block2mem", "mem2block", "ev"]

# Banks documented in the appendix (prefix match on the bank name), in order, with their title and
# the Python class that defines them.
BANKS = [
    ("sdcard_phy",       "PHY",                  "SDPHY",          "litesdcard/phy.py"),
    ("sdcard_core",      "Core",                 "SDCore",         "litesdcard/core.py"),
    ("sdcard_block2mem", "Block2mem DMA",        "SDBlock2MemDMA", "litesdcard/frontend/dma.py"),
    ("sdcard_mem2block", "Mem2block DMA",        "SDMem2BlockDMA", "litesdcard/frontend/dma.py"),
    ("sdcard_ev",        "Events and interrupt", "add_sdcard",     "litex/soc/integration/soc.py"),
]

# Descriptions of the PHY registers. The PHY declares them without `description` (CSRStorage,
# CSRStatus, CSR), so they are given here and attached to the elaborated registers before the dump;
# a description declared in the gateware takes precedence. Keys: (bank, register).
DESCRIPTIONS = {
    ("sdcard_phy", "card_detect")     : "Level of the card detect pad `cd` (0 when the pads have none). The BIOS reads 1 as no card.",
    ("sdcard_phy", "clocker_divider") : "Card clock divider: the card clock is the system clock divided by `divider` rounded up to even, and by 2 at least.",
    ("sdcard_phy", "init_initialize") : "Write: send the power-up clocks, 80 card clocks with CMD and DAT high; when the pads have `rst`, they follow a card reset as long as 4096 card clock periods, with the clock stopped.",
    ("sdcard_phy", "cmdr_timeout")    : "Response timeout in system clock cycles: wait for the start bit, the response bytes and the busy of an R1b.",
    ("sdcard_phy", "dataw_status")    : "CRC status tokens of the last write. See the fields below.",
    ("sdcard_phy", "dataw_timeout")   : "Write timeout in system clock cycles, for each block of a write: wait for the CRC status token and the end of the busy.",
    ("sdcard_phy", "datar_timeout")   : "Read timeout in system clock cycles, for each block of a read; it does not count while the PHY stops the card clock for back-pressure.",
}

# Descriptions of the fields declared without one in the gateware. Keys: (bank, register, field).
FIELD_DESCRIPTIONS = {
    ("sdcard_phy", "dataw_status", "accepted")    : "1: the card accepted a block (token `010`).",
    ("sdcard_phy", "dataw_status", "crc_error")   : "1: the card reported a CRC error on a block (token `101`).",
    ("sdcard_phy", "dataw_status", "write_error") : "1: the card reported a write error on a block (token `110`).",
    ("sdcard_phy", "settings", "data_width")      : "Bus width of the data transfers: `0b00` 1-bit, `0b01` 4-bit, `0b10` 8-bit.",
}

# Notes printed after the title of a bank family: what the register descriptions do not say.
NOTES = {
    "sdcard_phy": [
        "The three timeouts count system clock cycles. `add_sdcard` builds the PHY with 1 s for the",
        "response and read timeouts (`cmd_timeout=10e-1`, `data_timeout=10e-1`), so their reset",
        "value is the system clock frequency, `0x5f5e100` at 100 MHz; their class defaults are",
        "10 ms. It leaves the write timeout at its class default, 500 ms (`write_timeout=500e-3`),",
        "`0x2faf080` at 100 MHz. A write timeout ends the block and sets `data_event.timeout`.",
        "",
        "The bits of `dataw_status` are cleared when a write",
        "starts and set by the token of each block, so they sum up the whole last write.",
        "",
        "`settings` resets to 4-bit (1-bit with fewer than 4 data lines); the BIOS writes 1-bit before",
        "the initialization and widens the bus once the card supports it. The PHY adds the constant",
        "`sdcard_phy_support_4x` (1) to `csr.csv` with 4 data lines or more, and",
        "`sdcard_phy_support_8x` (1) with 8 data lines, which `soc.h` exports as",
        "`SDCARD_PHY_SUPPORT_4X` and `SDCARD_PHY_SUPPORT_8X`; the 8-bit design has the same",
        "registers ([PHY: clocking and IO](#phy)).",
    ],
    "sdcard_core": [
        "`cmd_command` takes the response type in `cmd_type` (0 none, 1 short, 2 long, 3 short with",
        "busy), the data direction in `data_type` (0 none, 1 read, 2 write) and the command index in",
        "`cmd`. Writing `cmd_send` starts the command and its data transfer, and clears both event",
        "registers; their `done` bits read 1 again when the core is idle.",
        "",
        "`cmd_response` holds the",
        "response right-aligned: for a short response, the first five bytes (the 32-bit payload in",
        "bits 31:0, without the CRC byte); for a long one, the 16 bytes after the first.",
        "",
        "In `cmd_event`, a response timeout sets `timeout` and `error`, and a CRC7 mismatch, when",
        "`cmd_command.crc` is 1, sets `crc` and `error`; for a data command, both also set",
        "`data_event.error`, since the data phase is skipped. In `data_event`, `timeout` reports a",
        "read or write timeout, `crc` a CRC16 error on a read or a `101` token on a write, and",
        "`error` the other rejected tokens of a write ([Core: commands, responses, CRC](#core)).",
    ],
    "sdcard_block2mem": [
        "The registers come from the LiteX `WishboneDMAWriter`, which the descriptions call the DMA",
        "Writer: it writes the blocks read from the card into memory. `base` and `length` are in",
        "bytes and must be multiples of the bus width in bytes, else the DMA stops at once with",
        "`error`; `offset` counts bus words.",
        "",
        "Writing 0 to `enable` resets the DMA, `done` and `error`",
        "included. The DMA takes the data of a read only when `enable` is 1 before the first byte",
        "arrives: set it before the command ([DMAs](#dma)).",
    ],
    "sdcard_mem2block": [
        "The registers come from the LiteX `WishboneDMAReader`, which the descriptions call the DMA",
        "Reader: it reads from memory the blocks to write to the card. `base`, `length`, `offset` and",
        "`enable` behave as in block2mem ([DMAs](#dma)).",
    ],
    "sdcard_ev": [
        "`add_sdcard`, a method of the LiteX SoC, adds an `EventManager` with five sources:",
        "`card_detect`, `block2mem_dma`",
        "and `mem2block_dma` are pulses, cleared by writing 1 to their `pending` bit; `data_done`",
        "and `cmd_done` are levels that follow the `done` bits of the core events.",
        "",
        "The interrupt of the event manager",
        "goes to the interrupt controller of the SoC when the SoC has one, and to the `irq` pin of",
        "`litesdcard_gen`. A design built with `mode=\"read\"` or `mode=\"write\"` has one DMA and",
        "its event only: the registers of the other DMA are absent, the offsets after them move",
        "down, and the bits of the event sources after the missing one move down by one.",
    ],
}

# Opening paragraph of the appendix and the sentence that ends the access paragraph.
INTRO = ["This appendix lists the registers of LiteSDCard: the PHY, the core, the two DMAs and the",
         "events. It is generated from the register definitions of the gateware, elaborated without",
         "an FPGA toolchain on the standalone core that `litesdcard_gen` builds, with 4 and with 8",
         "data lines.",
         "",
         "A LiteX SoC places every register of LiteSDCard in one bank named after the",
         "module, `sdcard` with `add_sdcard()`. This appendix splits it by block: each table lists",
         "the registers whose names start with its prefix, so `card_detect` in the table of",
         "`sdcard_phy` is `sdcard_phy_card_detect` in `csr.csv`. Offsets are in bytes from the base",
         "of the `sdcard` bank; the base address depends on the SoC and is in the `csr.csv` of a",
         "build."]
USAGE = ["The BIOS driver uses these names through the generated `csr.h`, and the Linux driver",
         "finds the blocks through the device tree, so neither needs the offsets."]
MAIN_BANK = "Registers of the top-level `main` bank of the SoC."


class _Region:
    """Part of a CSR region: the registers of one sub-module (csr_doc.py reads `obj` only)."""
    def __init__(self, obj):
        self.obj = obj


def _describe(soc):
    """Attach the descriptions above to the registers and fields that have none in the gateware."""
    for bank, region in soc.csr.regions.items():
        if not isinstance(region.obj, list):
            continue
        for csr in region.obj:
            desc = DESCRIPTIONS.get((bank, csr.name))
            if desc and not (getattr(csr, "description", None) or "").strip():
                csr.description = desc
            for f in getattr(csr, "fields", None) and csr.fields.fields or []:
                desc = FIELD_DESCRIPTIONS.get((bank, csr.name, f.name))
                if desc and not (f.description or "").strip():
                    f.description = desc


def _split(soc, csr_json, bank="sdcard"):
    """Split the bank of the module into one region per sub-module, at the base of the bank."""
    region = soc.csr.regions.pop(bank)
    base   = csr_json["csr_bases"][bank]
    unmatched = [c.name for c in region.obj if not any(c.name.startswith(sub + "_") for sub in SPLIT)]
    if unmatched:
        raise ValueError(f"Registers of bank {bank} with no prefix of SPLIT: {', '.join(unmatched)}")
    for sub in SPLIT:
        name = f"{bank}_{sub}"
        regs = [c for c in region.obj if c.name.startswith(sub + "_")]
        for c in regs:
            c.name = c.name[len(sub) + 1:]
        soc.csr.regions[name]       = _Region(regs)
        csr_json["csr_bases"][name] = base


def _gen_soc(vendor, clk_freq, dma_data_width, data_lines):
    """`LiteSDCardCore` of litesdcard/gen.py on a Lattice platform, with `data_lines` data lines."""
    assert vendor == "lattice"
    from litex.build.generic_platform import Pins, Subsignal
    from litex.build.lattice.platform import LatticePlatform
    from litesdcard import gen
    io = []
    for entry in gen._io:
        if entry[0] == "sdcard":
            entry = tuple(Subsignal("data", Pins(data_lines))
                if isinstance(e, Subsignal) and e.name == "data" else e for e in entry)
        io.append(entry)
    platform = LatticePlatform(device="", io=io)
    return gen.LiteSDCardCore(platform, clk_freq=int(clk_freq), dma_data_width=dma_data_width)


def elaborate(name, repo_root):
    """Elaborate the design with a Builder that runs no toolchain; return
    (soc, csr_json, module, argv)."""
    # The LiteSDCard of this repository, not an installed one.
    sys.path.insert(0, repo_root)
    from litex.soc.integration.builder import Builder
    old_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            soc     = _gen_soc(**PARAMS[name])
            builder = Builder(soc, output_dir=tmp, csr_csv=os.path.join(tmp, "csr.csv"),
                csr_json=os.path.join(tmp, "csr.json"), compile_software=False,
                compile_gateware=False)
            builder.build(build_name="litesdcard_core", run=False)
            csr_json = json.load(open(os.path.join(tmp, "csr.json")))
        finally:
            os.chdir(old_cwd)
    # Memories mapped on the CSR bus have no register definitions: keep the register banks only.
    for bank, region in list(soc.csr.regions.items()):
        if not isinstance(region.obj, list):
            del soc.csr.regions[bank]
    _split(soc, csr_json)
    _describe(soc)
    return soc, csr_json, "litesdcard_gen", CONFIGS[name]
