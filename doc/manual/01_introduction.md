```{=latex}
\mainmatter
\part{Understand}
```

```{=html}
<h1 class="part">Part I. Understand</h1>
```

# Introduction {#introduction}

This chapter says what LiteSDCard is, what it does and what it does not do, and how far it has
been validated. It ends with the layout of the repository and a map of the manual. Every reader
should start here.

## What LiteSDCard is {#intro-what}

LiteSDCard is an SD card and eMMC host controller written in Python with Migen and LiteX. It
drives a card in SD mode directly from FPGA pins: a clock, a command line and 1, 4 or 8 data
lines, with no controller chip on the board.

The same gateware runs on every FPGA family whose input and output registers LiteX knows how to
generate.

The project has four parts, shown in the figure below. The PHY clocks the card and moves bits on
its lines. The core builds the commands, checks the responses and their CRC, and frames the data
blocks. Two DMAs move the blocks between the core and the system memory, so the CPU only programs
registers.

![LiteSDCard in a LiteX SoC. The CPU programs the registers of the PHY, the core and the DMAs;
block2mem writes the blocks read from the card into memory and mem2block reads the blocks to
write; the PHY drives the card lines.](intro_overview.svg)

Two more parts complete the repository. The emulator is a Verilog model of an SD card that the
PHY can drive in a simulation or inside an FPGA. The generator, `litesdcard_gen`, produces a
standalone Verilog core with Wishbone ports for designs that are not built with LiteX.

## What lives in LiteX {#intro-litex}

LiteSDCard is the gateware. The integration and the software live in LiteX, as the figure below
shows, and change together with the gateware. In the table that follows, the paths are relative to
`litex/soc/` of the LiteX repository, and the device tree generator is in `litex/tools/`.

![The software around LiteSDCard. The BIOS driver initializes the card and reads blocks for the
BIOS commands and for the boot from a FAT file system; Linux uses the upstream `litex_mmc`
driver, enabled by the device tree that LiteX generates. Both only go through the
registers.](intro_software.svg)

| Part | Where | Role |
|--------------------|---------------------------------------|-----------------------------------------|
| SD-mode integration | `integration/soc.py` | `add_sdcard`: adds the PHY, the core, the DMAs and the interrupts |
| SPI-mode alternative | `integration/soc.py` | `add_spi_sdcard`: a LiteX SPI master instead of LiteSDCard |
| BIOS driver | `software/liblitesdcard/` | Card initialization, block read and write, FatFs disk access |
| BIOS commands and boot | `software/bios/` | `sdcard_init`, `sdcard_read`, `sdcard_write`, `sdcardboot` |
| Device tree generator | `litex_json2dts_linux.py` | Emits the `litex,mmc` node of the Linux driver |

[Software: BIOS, boot and Linux](#software) describes the software side, and [Adding LiteSDCard
to a SoC](#integration) the integration.

## Features at a glance {#intro-features}

| Area | Features |
|--------------------|------------------------------------------------------------------------|
| Cards | SD cards (SDSC, SDHC, SDXC) and eMMC devices, in SD mode |
| Bus | 1-bit, 4-bit and 8-bit data, selected at run time; card clock from the system clock divided by an even number, up to half the system clock |
| PHY | Vendor-neutral IO through LiteX; optional card detect, card reset and level-shifter direction pins |
| Core | Command frames with CRC7, short and long responses with CRC7 check, busy wait, data blocks with one CRC16 per data line, CRC status token on writes, timeouts on responses, reads and writes |
| Transfers | Single and multiple blocks; block length up to 1023 bytes on writes and 1022, 1016 or 1008 bytes on reads (1, 4 or 8-bit bus); block count up to 2^32 - 1, a count of 0 skips the data phase |
| Frontends | block2mem and mem2block DMAs (Wishbone masters); a BIST frontend, not integrated |
| Software | BIOS driver for SD cards and eMMC, boot from a FAT file system, Linux and Zephyr device tree nodes |
| Verification | Unit tests of the PHY, the core and the CRC; card emulator for full-system simulation |

The block length register is 10 bits wide. On reads, the PHY counts each block with its CRC bytes
on 10 bits, which sets the lower read limits ([Core: commands, responses, CRC](#core)). The BIOS
driver uses 512-byte blocks, except for two short reads during the initialization ([Software:
BIOS, boot and Linux](#software)).

## Status {#intro-status}

This is the one status table of the manual; every other chapter links here. The statuses are
statements of the maintainer. A number is given only when a public record of it exists, and
[Performance and resources](#performance) gives the details of each record.

| Function | Status | Public records |
|-------------------------------|------------------------|-------------------------------------------------------|
| SD card, 1-bit and 4-bit bus | Validated on hardware | 50 MHz card clock at 100 MHz system clock on an Arty A7-100; more than 10 MB/s in multi-block reads at 25 MHz |
| eMMC, 8-bit bus, high speed | Validated on hardware | 46 MB/s reading from the eMMC of the Efinix Ti375 C529 Dev Kit |
| Standalone generator `litesdcard_gen` | Build-tested | None |

The SD card row covers every family where LiteX provides the IO of the PHY: Xilinx, Intel/Altera,
Lattice and the others listed in [PHY: clocking and IO](#phy). The two records of that row come
from the history of LiteSDCard and of LiteX; [Performance and resources](#performance) gives the
source of the eMMC record.

The status words mean:

- **Validated on hardware**: the maintainer states that the function works on boards with real
  cards.
- **Build-tested**: the function elaborates and builds; no hardware result is recorded.

## Users {#intro-users}

LiteSDCard is the SD card controller of the LiteX boards. In LiteX-Boards, 81 targets call
`add_sdcard` and 71 platforms define an `sdcard` resource on the board (the other targets take it
from a Pmod or daughterboard extension); 75 targets also offer the SPI-mode alternative. These counts come from the commands below, run in a LiteX-Boards checkout.

```sh
git grep -l "add_sdcard(" -- litex_boards/targets | wc -l
git grep -l '"sdcard"' -- litex_boards/platforms | wc -l
git grep -l "add_spi_sdcard(" -- litex_boards/targets | wc -l
```

| FPGA family | Examples of targets |
|-----------------------------|----------------------------------------------------------|
| Xilinx 7-Series | `digilent_arty`, `digilent_genesys2`, `digilent_nexys_video` |
| Xilinx UltraScale(+) | `xilinx_kcu105`, `alinx_axau15` |
| Lattice ECP5 and NX | `radiona_ulx3s`, `colorlight_i5`, `trellisboard`, `trenz_tel0025` |
| Intel/Altera | `terasic_de2_115`, `qmtech_5cefa2`, `altera_agilex5e_065b_premium_devkit` |
| Gowin | `sipeed_tang_primer_20k`, `sipeed_tang_mega_138k` |
| Efinix | `efinix_ti60_f225_dev_kit`, `efinix_ti375_c529_dev_kit` (eMMC, 8-bit) |
| Cologne Chip | `colognechip_gatemate_evb`, `olimex_gatemate_a1_evb` |

Most targets add the microSD slot of the board or of a Pmod adapter. One target drives the
emulator inside the FPGA (`efinix_tz170_j484_dev_kit`). [Boards and examples](#boards) lists the
targets with their slot and bus width.

## What it is not {#intro-limits}

LiteSDCard is an SD-mode host at a fixed IO voltage (3.3 V for SD cards, the bank voltage for an
eMMC, 1.8 V on some boards), at default speed and high speed. The following are not implemented:

- UHS-I: no switch to 1.8 V signalling (CMD11), no tuning (CMD19) and no double data rate mode.
- SDIO cards, UHS-II and SD Express.
- SPI mode in LiteSDCard itself: LiteX offers it with `add_spi_sdcard` and its own SPI master.
- AXI or Avalon interfaces: the DMAs are Wishbone masters and the registers sit on the LiteX
  register bus.
- Writing files from the BIOS: its FAT file system access only reads.
- The BIST frontend is not connected by `add_sdcard`, by the benches or by the LiteX-Boards
  targets.

By default the emulator holds a single 512-byte block, so it answers the commands of a card but
does not store a disk image. Its `size` and `image` parameters give it a block-addressed store,
optionally loaded from a raw disk image, but `add_sdcard` does not pass them ([The SD card
emulator](#emulator)).

## Repository layout {#intro-layout}

| Path | Content |
|----------------------------------|----------------------------------------------------------------|
| `litesdcard/phy.py` | The PHY: clocker, init block, command and data engines, IO |
| `litesdcard/core.py` | The core: registers, command frames, CRC7, main state machine, read FIFO |
| `litesdcard/crc.py` | CRC generators: generic parallel CRC, one CRC16 per data line |
| `litesdcard/common.py` | Constants shared with the software: status codes, transfer types, bus widths |
| `litesdcard/frontend/` | block2mem and mem2block DMAs (`dma.py`), BIST (`bist.py`) |
| `litesdcard/emulator/` | SD card emulator: Migen wrapper and Verilog card model |
| `litesdcard/gen.py` | Standalone generator `litesdcard_gen` |
| `bench/` | Hardware benches (Arty, Genesys2, TrellisBoard), simulation bench, logic sampler |
| `test/` | Unit tests (pytest) of the PHY, the core and the CRC |
| `doc/` | This manual (`doc/manual/`) and its figures (`doc/diagrams/`) |

## License and credits {#intro-license}

LiteSDCard is released under the BSD 2-Clause license by Enjoy-Digital. The contributors of the
project are recorded in its repository history and in the `CONTRIBUTORS` file.

The Verilog card model of the emulator (`litesdcard/emulator/verilog/`) is Apache-2.0 licensed
upstream code; its notice is kept in the source files. The SPI mode support was added under the
same license. The Migen wrapper of the emulator is BSD 2-Clause like the rest of the project.

## How to read this manual {#intro-reading}

If SD cards are new to you, read [SD cards in a nutshell](#sd-primer) next. Otherwise, the table
below sends each question to its chapter.

| Question | Chapter |
|-----------------------------------------------|----------------------------------------|
| How does a card talk to a host? | [SD cards in a nutshell](#sd-primer) |
| How are the blocks organised? | [Architecture overview](#architecture) |
| How is the card clock made and sampled? | [PHY: clocking and IO](#phy) |
| How do bits go on the lines? | [PHY: command and data engines](#phy-engines) |
| How are commands and CRC handled? | [Core: commands, responses, CRC](#core) |
| How do blocks reach memory? | [DMAs](#dma) |
| How do I simulate a card? | [The SD card emulator](#emulator) |
| How do I read a first card? | [Getting started](#getting-started) |
| How do I add LiteSDCard to my SoC? | [Adding LiteSDCard to a SoC](#integration) |
| How do the BIOS and Linux use it? | [Software: BIOS, boot and Linux](#software) |
| Which board can I use? | [Boards and examples](#boards) |
| How is it tested? | [Simulation and verification](#simulation) |
| The card does not initialize: what now? | [Debugging](#debugging) |
| What does this acronym mean? | [Glossary](#glossary) |
