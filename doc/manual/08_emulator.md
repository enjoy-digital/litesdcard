# The SD card emulator {#emulator}

This chapter describes the emulator: a synthesizable model of an SD card that LiteSDCard drives
in place of a real card. The PHY, the core, the DMAs and the BIOS driver then run in a
simulation, or in an FPGA without a card slot. Read it to know what a simulation with the
emulator proves and what it does not.

## At a glance {#emu-glance}

| Item | Value |
|---------------------|---------------------------------------------------------------------------|
| Class | `SDEmulator(platform, size=None, image=None)` in `litesdcard/emulator/core.py` |
| Card model | Verilog `sd_phy` and `sd_link` (`litesdcard/emulator/verilog/`) |
| License | Wrapper BSD-2-Clause; Verilog files Apache License 2.0 |
| Modes | SD mode (1 or 4 DAT lines) and SPI mode; LiteSDCard uses SD mode |
| Card type | High capacity (CSD version 2.00), 125 MiB reported by default |
| Storage | One 512-byte buffer for all block addresses (default), or a block-addressed store |
| Clocks | Card clock from the PHY for the bit level, `sys` for the command logic |
| Used by | `litex_sim --with-sdcard`, `add_sdcard(use_emulator=True)` |

## Origin and license {#emu-origin}

The card model is Apache-2.0 licensed upstream code, extended with SPI mode support; its notice
is kept in the source files. The Migen wrapper `SDEmulator` and the rest of LiteSDCard are under
the BSD-2-Clause license.

The model does all the card work in hardware: it decodes the commands, keeps the card state,
builds the responses with their CRC7, and sends or receives the data blocks with their CRC16. The
wrapper adds the block storage and connects the model to the pads of the LiteSDCard PHY.

## Structure {#emu-structure}

The figure below shows the emulator and the PHY that drives it. `sd_phy` handles the bits on the
CMD and DAT lines; `sd_link` handles the commands and the card state; a memory holds the data,
one 512-byte block by default.

![Emulator. Look at the small loop above `sd_link`: every block request is acknowledged at once.
The memory next to `sd_phy` is addressed by the word in the block from `sd_phy` and, with a
block-addressed store, by the block address from `sd_link`.](emu_blocks.svg)

The PHY selects its emulator IO (`SDPHYIOEmulator`) when its pads record has the `cmd_t` and
`dat_t` fields of the emulator pads. The CMD and DAT lines then connect directly, without
tristate buffers and without IO registers, and the PHY uses 4 DAT lines. The clock that reaches
the emulator is the clocker output itself, the inverse of the card clock of a hardware PHY, and it
idles low when gated ([Emulator IO](#phy-emulator-io)).

The emulator has two clocks. The card clock from the PHY drives a clock domain of its own
(`sd_ll`), in which `sd_phy` samples and drives the lines and accesses the buffer. `sd_link` runs
on the `sys` clock and synchronizes the signals it exchanges with `sd_phy`.

## What the card reports {#emu-identity}

The card registers come from `sd_params.vh`. The table gives the values the BIOS sees.

| Register | Field | Value |
|----------|------------------|-------------------------------------------------------------|
| OCR | Voltage window | `0xFF8000` (2.7 V to 3.6 V) |
| OCR | CCS | 1: high capacity, block addressing |
| CID | Product name | `HELLO` |
| CSD | Structure | Version 2.00 |
| CSD | `C_SIZE` | 249 by default: (249 + 1) × 512 KiB = 125 MiB, 256 000 blocks |
| CSD | `TRAN_SPEED` | `0x32`: 25 MHz |
| SCR | Specification | Version 2.00 |
| SCR | Bus widths | 1 and 4 bits |
| SCR | Command support | No CMD23: the BIOS uses CMD12 after a multiple-block command |

CMD6 accepts the high speed function, which the BIOS selects, and its status reports the high speed
capability bit, which the wrapper option `opt_enable_hs` sets. The card answers CMD8 with the echo
of the check pattern, so the BIOS takes the SD path of its initialization, not the eMMC one
([Software](#software)).

## What it does not model {#emu-limits}

The card model checks the block address of each read and write against its capacity, then
requests the block. The wrapper acknowledges every request at once. What it stores depends on its
two arguments:

| Arguments | Store | Reported capacity |
|------------------------------|-----------------------------------------------------------|--------------------------|
| None (default) | One 512-byte buffer for every block address; at power-up, its word index in each of its 128 words | 125 MiB (`C_SIZE` 249) |
| `size` | `size` bytes of distinct blocks, zeros at power-up | `size` |
| `image` | The raw disk image file, then zeros up to `size` | `size`, or the image size rounded up to 512 KiB |

`size` must be a multiple of 512 KiB, the capacity unit of a CSD version 2.00, and the image must
fit in it; the wrapper raises a `ValueError` otherwise. The store is a memory of the design,
initialized from the image when it is built: a simulation or a bitstream holds a whole disk only
when the memory can be that large.

`add_sdcard(use_emulator=True)` passes its `emulator_size` and `emulator_image` arguments to
`SDEmulator` as `size` and `image`. Without them, as in `litex_sim --with-sdcard` and the
LiteX-Boards targets, the emulator has the default single buffer: every read returns the content
of the buffer and every write overwrites it, whatever the block address. The table below gives
the limits of that default emulator.

| Feature | Emulator |
|----------------------------|---------------------------------------------------------------|
| Distinct blocks | No: one buffer for all addresses (yes with `size` or `image`) |
| A FAT file system | No: the buffer holds no boot sector, `sdcardboot` finds none (yes with an `image` that holds one, as `litex_sim --sdcard-image`) |
| Persistent data | No: initial content at each start |
| 8 DAT lines, eMMC | No: 4 DAT lines, SD card only |
| Card access and busy times | Set by the model, not those of a real card |
| Clock polarity, IO delays | As the hardware IO registers, without pad and board delays ([Emulator IO](#phy-emulator-io)) |
| Signal integrity, pull-ups | Not applicable: the lines connect without IO buffers |

A simulation with the emulator therefore checks the protocol: the initialization flow, the
switch to 4 bits and high speed, single and multiple block reads and writes, the CRCs and the
DMAs. With the default store it does not check the content of a disk, and it never checks timing
at the pads.

## Using it {#emu-using}

`litex_sim --with-sdcard` adds the emulator to the LiteX simulation SoC through
`add_sdcard(use_emulator=True)`. The emulator needs its Verilog sources, so the simulation runs
with Verilator, as every `litex_sim` design does. The first run, with the BIOS commands to try,
is in [Getting started](#getting-started); the simulation flow is in
[Simulation and verification](#simulation).

```sh
litex_sim --with-sdcard
```

The same option of `add_sdcard` builds the emulator into an FPGA design, where the PHY drives it
through internal signals instead of pads. One LiteX-Boards target offers it,
`efinix_tz170_j484_dev_kit.py --with-sdcard-emulator` ([Boards and examples](#boards)).

A block-addressed store comes from the arguments of `add_sdcard`, or from `--sdcard-image` in
`litex_sim`, which builds the emulator from a raw disk image (and implies `--with-sdcard`):

```python
# Emulator store loaded from a raw disk image, its size rounded up to 512 KiB.
soc.add_sdcard(use_emulator=True, emulator_image="sdcard.img")
```

```sh
litex_sim --sdcard-image sdcard.img
```

[Boot from a FAT image in simulation](#gs-sim-boot) builds such an image and boots from it.

## In the code {#emu-code}

The emulator files are in `litesdcard/emulator/`; the PHY side is in `litesdcard/phy.py`
(`SDPHYIOEmulator`).

| Function | File | Content |
|----------------|-----------------------------------|---------------------------------------|
| Wrapper | `core.py` | `SDEmulator`, block store, `sd_ll` clock domain |
| Card bit level | `verilog/sd_phy.v` | `sd_phy` |
| Commands, state | `verilog/sd_link.v` | `sd_link` |
| Card registers | `verilog/sd_params.vh` | OCR, CID, CSD, SCR values |
| Command indexes | `verilog/sd_const.vh` | CMD and ACMD constants |
| Tests | `test/test_emulator.py` | Default buffer, size, image, addressing |

Where to go next: [Getting started](#getting-started) for a first session with the emulator,
[Simulation and verification](#simulation) for the test flow, [Core: commands, responses,
CRC](#core) for the commands the BIOS sends to it.
