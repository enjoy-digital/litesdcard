```{=latex}
\frontmatter
```

# About this document {.unnumbered}

This manual is the reference of LiteSDCard, the SD card and eMMC host controller of the LiteX
ecosystem. It connects an FPGA directly to an SD card slot or to a soldered eMMC device. The manual
is written for FPGA engineers who want to use or extend LiteSDCard, and it teaches the SD bus along
the way.

No prior knowledge of SD cards is assumed. Part I explains the bus as the cards define it: pins,
commands, responses, initialization and data blocks, with the module that implements each
mechanism. Part II describes the implementation: the PHY and its engines, the core, the DMAs and
the emulator.

Part III is the user guide: the first run in simulation and on a board, the integration in a SoC,
the software side (BIOS, boot, Linux), the boards, the simulation and the debugging. The
appendices hold the register reference, the build options, the glossary, the performance figures
and the maintenance notes of this manual.

| If you want to | Read |
|------------------------------------------|----------------------------------------------|
| Know what LiteSDCard does and what it does not | [Introduction](#introduction) |
| Learn how an SD card talks to a host | [SD cards in a nutshell](#sd-primer) |
| See the blocks and how a transfer flows | [Architecture overview](#architecture) |
| Read a card in simulation or on a board | [Getting started](#getting-started) |
| Add an SD card slot or an eMMC to your SoC | [Adding LiteSDCard to a SoC](#integration) |
| Boot from the card or mount it in Linux | [Software](#software) |
| Understand a card that does not initialize | [Debugging](#debugging) |

The manual follows the repository: every name, number and default is taken from the source code,
and the register reference is generated from it. When the code and the manual disagree, the code
is right and the manual has a bug.

## Conventions {.unnumbered}

- Numbers: `0x` prefix for hexadecimal, `0b` for binary. Bit 0 is the least significant bit.
- Rates: card clocks in kHz and MHz; throughputs in MB/s, that is 10^6 bytes per second. Sizes in
  bytes, KiB and MiB; a block is 512 bytes unless stated.
- SD names follow the SD Physical Layer Simplified Specification, cited as "section 4.7"; eMMC
  names follow JEDEC JESD84. Commands are written CMD17 and application commands ACMD41.
- *The card* is the SD card or the eMMC device; *the host* is the FPGA design that drives it.
  *The PHY* is `SDPHY`, *the core* is `SDCore`, *block2mem* and *mem2block* are the two DMAs;
  *LiteSDCard* is the whole project.
- *Register* is a control and status register of the SoC, read and written by the CPU. *Card
  register* is a register inside the card, such as the OCR or the CSD.
- `<target>` stands for the name of a LiteX-Boards target script without its extension, such as
  `digilent_arty`.
- Paths are relative to the repository root, except paths of LiteX, written as in
  `litex/soc/software/liblitesdcard/sdcard.c`. Shell commands are given for a Linux host.
- When the text names a source file, it is the file to open to check or extend the fact.
