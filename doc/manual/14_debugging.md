# Debugging {#debugging}

This chapter helps when a card does not work: it is not detected, the initialization stops,
transfers fail with CRC errors or timeouts, the data is wrong, a DMA never ends or the boot
fails. It gives a method, the registers to read first, the debug trace of the BIOS driver, the
usual causes of each symptom, and the LiteScope probes of the benches.

## Method {#debug-method}

Work from the software towards the pads, and check each step before the next one.

1. Check that the board runs the bitstream you expect: with a bridge, `litex_cli --ident` prints
   the identifier of the build.
2. Read the registers of LiteSDCard ([Registers to read first](#debug-registers)). They tell
   where the last command stopped without changing anything in the core.
3. Build the BIOS driver with its debug trace and run `sdcard_init` again
   ([BIOS debug trace](#debug-trace)): it prints every command and its event register.
4. Only then capture the pads and the PHY streams with LiteScope, on one command at a time
   ([LiteScope captures](#debug-litescope)).

```sh
# Identifier of the SoC, then every register of LiteSDCard
litex_cli --ident
litex_cli --regs --filter sdcard_
```

The `AGENTS.md` file of the repository and the LiteX wiki page on debugging a SoC on hardware
(<https://github.com/enjoy-digital/litex/wiki/Debug-A-SoC-On-Hardware>) describe the same method
for the whole SoC: the link and `--ident` first, registers before traces, narrow captures. Reading
the registers of LiteSDCard has no side effect.

## Registers to read first {#debug-registers}

The table gives the registers that tell the state of the last command, with the value of a
healthy card after `sdcard_init`. The names are those of `csr.csv`; [Register
reference](#registers) gives every field.

| Register | Tells | Healthy value |
|-------------------------------------------------|--------------------|-------------------------------------|
| `sdcard_phy_card_detect` | Level of the card detect pad | 0 with a card (no pad: always 0) |
| `sdcard_phy_clocker_divider` | Card clock = system clock / divider rounded up to even | `ceil(f_sys / 25 MHz)` for an SD card, `ceil(f_sys / 50 MHz)` for an eMMC in high speed, between 2 and 511 |
| `sdcard_phy_settings` | Bus width of the data transfers | 1 (4-bit), 2 (8-bit eMMC), 0 (1-bit card) |
| `sdcard_core_cmd_event` | Last command: done, error, timeout, CRC | `0x1` |
| `sdcard_core_data_event` | Last data transfer: done, error, timeout, CRC | `0x1` |
| `sdcard_core_cmd_response` | Last response, right-aligned | Card status in bits 31:0 |
| `sdcard_phy_dataw_status` | CRC status tokens of the last write | `0x1` (accepted) |
| `sdcard_block2mem_dma_done` | Block2mem has written `length` bytes | 1 after a read (also 1 at once on an error) |
| `sdcard_block2mem_dma_error` | Misaligned `base` or `length` | 0 |
| `sdcard_block2mem_dma_offset` | Bus words written so far | `length` / word size |

`cmd_event` reads `0x7` (done, error and timeout) when the card did not answer, and `0xb`
(done, error and CRC) when the CRC7 of a response checked by the core is wrong; for a data command,
both also set the error bit of `data_event`, since the data phase is skipped. `data_event` reads
`0x9` (done and CRC) after a block with a bad CRC16 or a `101` token, `0x5` (done and timeout)
after a read or write timeout, and `0x3` (done and error) after another rejected token. The BIOS
driver sends ACMD41 and CMD1 without the CRC check (their R3 response has no CRC), so a bad CMD
line shows there as a wrong response, not as a flag.

## BIOS debug trace {#debug-trace}

The BIOS driver prints each command, the value of `cmd_event` and the response when it is built
with `SDCARD_DEBUG`. `add_sdcard(software_debug=True)` defines it in `soc.h`, so no source file
changes:

```python
self.add_sdcard(software_debug=True)
```

The trace below is recorded in a public LiteX commit message (`bd7b951af`); it shows a card that
does not answer. The board is not named, and the BIOS of that revision printed the unit as `KHz`
(the driver now prints `kHz`).

```console
Booting from SDCard in SD-Mode...
Booting from boot.json...
Setting SDCard clk freq to 781 KHz
CMD0: GO_IDLE
cmdevt: wait for event & 0x1
cmdevt: 00000001
00000000 00000000 00000000 00000000
CMD8: SEND_EXT_CSD, arg: 0x000001aa
cmdevt: wait for event & 0x1
cmdevt: 00000005
00000000 00000000 00000000 00000000
[...]
SDCard boot failed.
No boot medium found
```

Read it line by line. CMD0 has no response, so `cmdevt: 00000001` is only done. CMD8 ends with
`00000005`, done and timeout: the card never started a response, and the four response words stay
at 0. The core of the master branch also sets the error bit on a timeout, so the same failure
reads `00000007`.

The driver names CMD8 `SEND_EXT_CSD`, but the command it sends is SEND_IF_COND with the check
pattern `0x1aa` ([Initialization](#primer-init)). The driver of the master branch also tries CMD1
after each CMD8 timeout, for an eMMC, so its trace shows `CMD1: SEND_OP_COND` after
each CMD8, up to 1000 times.

The 781 kHz identification clock of the trace came from the driver of that revision, which
capped the divider at 256: with a system clock above 102.4 MHz, it got more than the 400 kHz it
asked for. The driver of the master branch accepts dividers up to 511, the range of the
register, and stays at 400 kHz or below up to a 204.8 MHz system clock (computed).

## Card not detected {#debug-detect}

`sdcard_detect` prints `SDCard inserted.` when `card_detect` reads 0, and `SDCard not inserted.`
when it reads 1: the BIOS takes the detect pad as active low. Without a `cd` subsignal in the
platform, the register reads 0 and every card is reported inserted.

A detect switch of the other polarity only makes `sdcard_detect` wrong. The initialization does
not read `card_detect`: `sdcard_init` runs whatever the detect pad says, so a wrong polarity does
not prevent a boot.

## Initialization stops {#debug-init}

`sdcard_init` prints `Initialize SDCard: failed` when a step fails. The driver repeats CMD0 and
CMD8 up to 1000 times, then ACMD41 up to 1000 times, and stops at the first failed command after
that ([Software: BIOS, boot and Linux](#software)). For an SD card, it keeps the identification
clock, 400 kHz by default, until the card has its address (CMD3), then switches to the operating
clock, 25 MHz by default: CMD10 and the later commands run at that clock.

| Last command in the trace | `cmd_event` | Usual causes |
|----------------------------|---------------|----------------------------------------------------|
| CMD8, then CMD1 | `0x7` | No card, no pull-ups on CMD and DAT, wrong pins, no 3.3 V on the card, card clock not reaching the card |
| CMD8, then CMD1 answers | `0x1` | An eMMC, or a card that answers CMD1: the driver takes the eMMC path |
| ACMD41, repeated | `0x1` | Card never ready (bit 31 of the OCR stays 0): power supply, or a card that needs more time |
| CMD2 or CMD3 | `0x7`, or `0xb` on a CRC error | Signal problem at the identification clock: wiring, pull-ups, IO standard |
| CMD10 to CMD7 | `0x7`, or `0xb` on a CRC error | Marginal signal at the operating clock: lower `SDCARD_CLK_FREQ` |
| CMD6 `SWITCH_FUNC` | `0x1` | The 64-byte status did not arrive (check `data_event`), or the card did not select high speed, which ends the initialization |
| ACMD51 | `0x1` | The 8-byte SCR did not arrive: check `data_event` and the DAT lines ([CRC errors](#debug-crc)) |

The CMD and DAT lines are open lines that the card and the host drive in turn: they need
pull-ups, internal or on the board ([The bus](#primer-bus)). A platform that omits them can pass
the identification at a low clock and fail later.

## CRC errors and wrong data at speed {#debug-crc}

A CRC error on a read sets `data_event.crc` and makes the BIOS driver return an error. The PHY
samples the inputs on one fixed system clock cycle of each card clock period, and inverts the output
clock to meet the setup and hold times of the card ([PHY: clocking and IO](#phy)). What varies
from board to board is the delay of the wiring and of any level shifter.

- Lower the card clock with `sdcard_freq` at the BIOS prompt after `sdcard_init` (which sets it
  back to `SDCARD_CLK_FREQ`), then read again. A read that works
  at a lower clock points to the board, not to the core.
- On a Pmod adapter or long wires, keep the card clock at 25 MHz or below, and check that the
  pull-ups and the IO standard of the platform match the adapter.
- A DAT1 or DAT2 line that is not connected, or stuck, fails only in 4-bit mode: the
  identification and the 64-byte status of CMD6 travel on CMD and DAT0 only, before the switch to
  4 bits. Reads that fail only after the switch point to DAT1 to DAT3. DAT3 held low at CMD0 is
  worse: the card takes it as the chip select of SPI mode and the identification fails.
- A write that fails with `data_event.crc` set received the `101` token: the card saw a CRC error
  on the data the host sent, so check the output side of the DAT lines.

## Timeouts {#debug-timeouts}

The PHY counts its timeouts in system clock cycles. `add_sdcard` sets the response and read
timeouts to 1 s, against 10 ms for the class defaults, and leaves the write timeout at its class
default, 500 ms ([Register reference](#reg-sdcard-phy)). A response timeout ends the command
with `cmd_event` at `0x7`; a read or write timeout ends the transfer with `data_event` at `0x5`.
The BIOS driver sends the data commands (CMD6 `SWITCH_FUNC` of an SD card, ACMD51, the reads and
the writes) up to `SDCARD_CMD_RETRIES` times, 16 by default, and the other commands once.

The response timeout also covers the busy of an R1b response, such as after CMD7 or a CMD6 on an
eMMC. The read timeout counts each block, and does not count while the PHY stops the card clock
because the DMA is not ready.

The write timeout covers the CRC status token and the busy of each written block. A card that
never sends its token, or holds DAT0 low longer than `dataw_timeout`, ends the write with
`data_event` at `0x5`. The BIOS driver waits for `data_event.done` after each write command
without a bound of its own (`sdcard_wait_data_done`), so this timeout is what bounds the wait:
`sdcard_write` then fails and disables mem2block, which drops the bytes of the failed write
that it had already fetched ([Mem2block](#dma-mem2block)).

A write that fails with `data_event.timeout` set points to a card stuck in busy, or a CRC status
token that never came: check DAT0 with LiteScope. A card that needs longer to program a block
needs a larger `dataw_timeout`, written before the write.

## Wrong data with a standard-capacity card {#debug-ccs}

A standard-capacity card (SDSC) takes byte addresses in the read and write commands; SDHC and SDXC
cards take block numbers ([Capacity and addressing](#primer-capacity)).

The BIOS driver reads the CCS bit of the OCR after ACMD41 and multiplies the block number by 512
when it is 0. A custom driver that skips this step sends block number n as byte address n on such a
card, and reads or writes the wrong place.

## DMA never done {#debug-dma}

The BIOS driver waits on `dma_done` with a bound of `SDCARD_DMA_TIMEOUT_US`. When it times out,
check in order:

1. `enable` was 1 before the command: block2mem only takes the data of a read that starts while
   it is enabled ([DMAs](#dma)).
2. `length` is `512` times `block_count`, and the command had a data type.
3. `data_event` and `cmd_event`: after a response timeout or a CRC7 error, the core skips the
   data phase, so no data reaches the DMA.

A DMA that reads done at once without any data is the opposite case: `dma_error` is 1 when
`base` or `length` is not a multiple of the bus word (4 bytes on a 32-bit bus), and a `length`
of 0 is done immediately.

A DMA that ends but leaves old data in memory is a cache issue. Without a DMA bus, the DMAs write
through the main bus behind the CPU caches, and the BIOS driver flushes them after each read; a
custom driver must do the same ([Caches](#dma-caches)).

## Boot fails {#debug-boot}

`sdcardboot` mounts the FAT file system of the card with FatFs, loads `boot.json`, and falls back
to `boot.bin`. The messages tell which step failed:

- `Error: filesystem mount failed (FatFs error N)`: `sdcard_init` failed, or the card has no
  FAT partition.
- `Error: cannot open boot.json (FatFs error N)`: no such file at the root; the BIOS then tries
  `boot.bin`.
- `Error: <file> is empty or too large for destination`: the file does not fit the memory at its
  load address.
- `SDCard boot failed.`: neither `boot.json` nor `boot.bin` could be loaded.

Run `sdcard_init` alone first: a mount failure with a failed initialization is a card or board
problem, not a file system problem. In simulation the boot does not work with the default
emulator ([What the emulator does not model](#emu-limits)).

On Linux, `litex_json2dts_linux` reads the registers of both DMAs and the interrupt number of
the module to build the `mmc` node: a SoC built with `mode="read"` or `mode="write"`, or without
an interrupt for the module, makes it stop with a `KeyError`, even with `--polling` ([Software:
BIOS, boot and Linux](#software)).

## LiteScope captures {#debug-litescope}

The benches of the repository add a LiteScope analyzer on the pads and the streams of the PHY with
`--with-analyzer`: the pads record (`sdpads`), the sink of `cmdw`, the sink and source of `cmdr`,
the sink of `dataw` with its `stop`, its CRC receiver and its `status`, the sink and source of
`datar`, and `ce` and `stop` of the clocker, on a depth of 2048 samples.

In a target, add a narrower analyzer on `self.sdcard.phy` and a bridge (UARTBone, JTAGBone or
Etherbone):

```python
from litescope import LiteScopeAnalyzer
phy = self.sdcard.phy
self.analyzer = LiteScopeAnalyzer([
        phy.sdpads,
        phy.cmdw.sink,
        phy.cmdr.source,
        phy.datar.source,
        phy.dataw.status.status,
        phy.clocker.ce,
    ],
    depth        = 2048,
    clock_domain = "sys",
    samplerate   = self.sys_clk_freq,
    csr_csv      = "analyzer.csv")
```

Trigger on the start of a command and run the BIOS command at the prompt:

```sh
# Names of the probes, then a capture on the next command sent to the card
litescope_cli --list
litescope_cli -r cmdw_sink_valid
```

The system clock samples the pads, and a card clock period spans the divider rounded up to even
in samples: at
25 MHz from 100 MHz, 4 samples per bit. A block read takes about 1050 card clocks in 4-bit mode
([Performance and resources](#perf-bounds)), so capture with subsampling or trigger on
`datar_source_source_valid` to see the data. The LiteScope manual
(<https://github.com/enjoy-digital/litescope>) describes the triggers and the subsampler.

## Known issues {#debug-known}

The issues of the code that show up while debugging are listed here with the place to look.
[Limitations](#core-limitations) explains the ones of the core.

| Issue | Effect | Where |
|------------------------------------|----------------------------|-----------------------------------------------------|
| Unsupported `settings` width | A width the pads do not have moves the data on DAT0 only, without an error (see the `support_4x` and `support_8x` constants) | `litesdcard/phy.py` |
| BIOS 4-bit switch without a PHY width check | A 1-bit slot fails after the bus switch | LiteX `sdcard.c` |
| BIOS ACMD41 argument | Sets bit 29, which the SD specification reserves | LiteX `sdcard.c` |
| BIOS CID and CSD decode | Debug trace prints shifted CID fields and the CSD structure as the transfer rate | LiteX `sdcard.c` (`SDCARD_DEBUG`) |
| `flash_from_sdcard` disk functions | Uses the FatFs disk of the last `sdcardboot` or `sataboot`, none at reset | LiteX `bios/cmds/cmd_spiflash.c` |
| DTS generator needs both DMAs and the IRQ | `KeyError` with one DMA, or without an interrupt even with `--polling` | LiteX `litex_json2dts_linux.py` |
| DTS `bus-width` always 4 | An 8-bit eMMC is described as 4-bit | LiteX `litex_json2dts_linux.py` |
| Linux driver PHY offsets | The mainline `litex_mmc` writes the bus width at offset `0x18` of the PHY, where the master branch has `datar_timeout` (`settings` is at `0x1c`) | `litesdcard/phy.py` (`dataw_timeout`), Linux `litex_mmc.c` (`drivers/mmc/host`) |
| Emulator with one buffer by default | No boot in simulation with `add_sdcard` | LiteX `add_sdcard`, `litesdcard/emulator/` |

## Where to go next {#debug-next}

[Register reference](#registers) for every register; [Software: BIOS, boot and Linux](#software)
for the driver; [Simulation and verification](#simulation) to reproduce a problem without a card.
