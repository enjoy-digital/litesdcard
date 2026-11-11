# Software: BIOS, boot and Linux {#software}

This chapter describes the software that drives LiteSDCard. All of it lives in LiteX: the BIOS
driver, the BIOS commands, the boot from a FAT file system, and the device tree that enables the
Linux driver. It ends with the register sequence for a driver of your own.

## At a glance {#sw-glance}

| Piece | LiteX file | Role |
|---------------|------------------------------------------------|-------------------------------------|
| BIOS driver | `liblitesdcard/sdcard.c` | Clock, initialization, block transfers, FatFs disk |
| BIOS commands | `bios/cmds/cmd_litesdcard.c` | The `sdcard_*` commands |
| SD card boot | `bios/boot.c` | `sdcardboot`: files from a FAT partition |
| Flash update | `bios/cmds/cmd_spiflash.c` | `flash_from_sdcard`: a file into the SPI flash |
| Linux device tree | `litex_json2dts_linux.py` | Node of the upstream `litex_mmc` driver |
| Zephyr device tree | `litex_json2dts_zephyr.py` | `sdhc0` node, `litex,mmc` |

The BIOS files are under `litex/soc/software/` and the device tree generators under
`litex/tools/` in the LiteX repository.

The BIOS builds the driver when the SoC has a module named `sdcard` (`CSR_SDCARD_BASE` in
`csr.h`); the read and write functions need the matching DMA.

## The BIOS driver {#sw-bios}

The driver programs the registers of the PHY, the core and the DMAs, and polls their event
registers; it uses no interrupt. Each command is sent by writing its argument and its command
word, then waiting for the `done` bit of `cmd_event`. The SD card CMD6, ACMD51 and the data
commands are retried up to `SDCARD_CMD_RETRIES` times when they fail; the eMMC CMD6 SWITCH is not.

**Card clock.** `sdcard_set_clk_freq` computes the divider as the system clock divided by the
wanted frequency, rounded up, then limited to the range 2 to 511, the values of the 9-bit divider
register. The clocker divides by an even
number, so the card clock is the system clock divided by the divider rounded up to even
([PHY: clocking and IO](#phy)).

The BIOS prints that effective value: at the 1 MHz of `litex_sim`, the 400 kHz request gives
250 kHz and the 25 MHz request gives 500 kHz.

The upper limit of 511, an effective division by 512, keeps the identification clock at or below
400 kHz up to a system clock of 204.8 MHz (computed).

**Configuration.** The driver reads the macros below. Each one can be set from the SoC as a
constant, which LiteX writes in `soc.h` before the driver includes it.

| Macro | Default | Role |
|---------------------------------------------|-------------------|------------------------------------|
| `SDCARD_CLK_FREQ_INIT` | `400000` | Identification clock, Hz |
| `SDCARD_CLK_FREQ` | `25000000` | SD card clock after identification, Hz |
| `SDCARD_MMC_CLK_FREQ` | `50000000` | eMMC clock in high speed timing, Hz |
| `SDCARD_CMD_RETRIES` | `16` | Attempts of the SD CMD6, ACMD51 and data commands |
| `SDCARD_DMA_TIMEOUT_US` | `1000000` | Wait for the end of a DMA, µs |
| `SDCARD_DEBUG` | undefined | Print every command, event and response |
| `SDCARD_BOOT_PRIORITY` | `30` | Rank of the SD card in the boot sequence |
| `SDCARD_BOOT_DISABLE` | undefined | Remove the SD card from the boot sequence |

```python
# A board whose traces do not pass 25 MHz: run the card at 12.5 MHz.
soc.add_sdcard()
soc.add_constant("SDCARD_CLK_FREQ", 12500000)
```

`add_sdcard(software_debug=True)` defines `SDCARD_DEBUG`. [Build options](#build-options) lists
the other BIOS options.

## Initialization {#sw-init}

`sdcard_init` brings the card from power-up to the transfer state, with 512-byte blocks. The
figure below shows its two paths: CMD8 tells an SD card from an eMMC, which answers CMD1 instead.

![sdcard_init of the BIOS driver. Both paths start on a 1-bit bus at the identification clock.
An SD card answers CMD8 and goes left; an eMMC does not, answers CMD1 and goes right. The
initialization starts over, up to 1000 times, while neither command is
answered.](sw_init_flow.svg)

**SD cards.** The driver sets the 1-bit bus and the identification clock, asks the PHY for 80
clocks, then sends CMD0 and CMD8 with the check pattern `0x1aa`.

It repeats CMD55 and ACMD41 until the card reports ready, and keeps the CCS bit of the OCR. CCS
tells block addressing (high capacity cards) from byte addressing (standard capacity cards). CMD2
reads the CID and CMD3 gets the relative address of the card, which ends the identification; only
then does the driver switch to the operating clock, `SDCARD_CLK_FREQ`.

It then reads the CID and the CSD again (CMD10, CMD9), selects the card with CMD7, and switches it
to high speed with CMD6. The 64-byte status of CMD6 and the 8-byte SCR of ACMD51 come through
block2mem.

When the SCR offers the 4-bit bus, ACMD6 sets it on the card and the driver sets it in the PHY.
CMD16 sets 512-byte blocks. The driver uses CMD23 for multiple blocks only when the SCR
announces it.

**eMMC.** When CMD8 gets no answer but CMD1 does, the driver repeats CMD1 until the device is
ready and takes the addressing mode from the OCR. At the identification clock, it reads the CID
(CMD2), assigns the relative address 1 with CMD3, reads the CSD and selects the device, then moves
to `SDCARD_CLK_FREQ`.

Two CMD6 SWITCH commands then write the EXT_CSD: the bus width (8 bits when the PHY has 8 data
lines, else 4) and the high speed timing, after which the clock rises to `SDCARD_MMC_CLK_FREQ`.

**A recorded trace.** The session below ran `sdcard_init` in `litex_sim --with-sdcard`, with a
BIOS built with `SDCARD_DEBUG`; the decoded CID, CSD and SCR fields are cut. After each command,
the driver prints the value of `cmd_event` and the four words of `cmd_response`. It prints CMD8
as `SEND_EXT_CSD`: it is SEND_IF_COND ([BIOS debug trace](#debug-trace)). The decoded CID and CSD
fields that it prints are shifted by one byte ([Known issues](#debug-known)): read the raw words.

```console
litex> sdcard_init
Setting SDCard clk freq to 250 kHz
CMD0: GO_IDLE
cmdevt: wait for event & 0x1
cmdevt: 00000001
00000900 00090011 09201000 20060000
CMD8: SEND_EXT_CSD, arg: 0x000001aa
cmdevt: wait for event & 0x1
cmdevt: 00000001
000001aa 00090008 09001100 20100000
CMD55: APP_CMD
[...]
ACMD41: APP_SEND_OP_COND, arg: 70ff8000
cmdevt: wait for event & 0x1
cmdevt: 00000001
c0ff8000 0001203f 01aa3700 00080000
CMD2: ALL_SEND_CID
[...]
CMD3: SET_RELATIVE_ADDRESS
cmdevt: wait for event & 0x1
cmdevt: 00000001
13370500 014fa703 00000001 4c4c4f10
Setting SDCard clk freq to 500 kHz
[...]
CMD6: SWITCH_FUNC
cmdevt: wait for event & 0x1
cmdevt: 00000001
00000900 00070006 001f0700 7f800a40
dataevt: wait for event & 0x1
dataevt: 00000001
[...]
SCR Register: 0x0215000000000000
1-bit support: 1
4-bit support: 1
[...]
CMD23 support: 0
[...]
ACMD6: SET_BUS_WIDTH
[...]
CMD16: SET_BLOCKLEN
cmdevt: wait for event & 0x1
cmdevt: 00000001
00000900 00092010 09200600 20370000
Initialize SDCard: OK
```

Read the first response word of each command. CMD8 echoes the check pattern `0x1aa`. The OCR
of ACMD41, `0xc0ff8000`, has bit 31 set (ready) and bit 30 set (CCS, block addressing). CMD3
returns the relative address `0x1337` of the emulator in its upper half, after which the driver
leaves the 250 kHz identification clock for 500 kHz, the closest to 25 MHz at the 1 MHz system
clock of `litex_sim`. The other words keep bytes of earlier responses and carry no meaning for a
short response.

`cmdevt: 00000001` is `done` alone. A response timeout reads `00000007` (done, error and timeout), a
CRC error on a response checked for its CRC `0000000b` (done, error and crc). The older core of the
trace of [BIOS debug trace](#debug-trace) reported a timeout as `00000005`. The SCR above has no
CMD23, so this card gets CMD12 after its multiple block transfers.

## Reads and writes {#sw-transfers}

`sdcard_read` and `sdcard_write` move whole requests of 512-byte blocks. Each request programs
its DMA with the buffer address and the length, then sends one command for all its blocks (the
driver defines `SDCARD_CMD18_SUPPORT` and `SDCARD_CMD25_SUPPORT`; without them, it sends one
command per block).

| Request | Commands | DMA |
|-----------------------------|------------------------------------------------|-----------------------|
| One block read | CMD17 | block2mem |
| Several blocks read | CMD23 and CMD18 when the card has CMD23, else CMD18 then CMD12 | block2mem |
| One block write | CMD24 | mem2block |
| Several blocks written | CMD23 and CMD25 when the card has CMD23, else CMD25 then CMD12 | mem2block |

The block number becomes the command argument directly on a high capacity card, or is
multiplied by 512 on a standard capacity card. After the command, the driver waits for the
`done` bit of `data_event`, then for the `done` register of the DMA, for at most
`SDCARD_DMA_TIMEOUT_US`. A failed command stops the DMA at once, since no data will come.

The wait for `data_event` has no bound of its own in the driver; the PHY bounds it, with the read
timeout for a read and the write timeout (CRC status token and busy, 500 ms with `add_sdcard`)
for a write, so a card that stops answering ends the request with `SD_TIMEOUT`.

The functions return `SD_OK`, `SD_TIMEOUT`, `SD_CRCERROR` or `SD_WRITEERROR`. The driver checks
the timeout, CRC and error bits of `data_event`, in this order: `SD_WRITEERROR` reports the error
bit that the core sets when a card refuses a written block. A failed command returns
`SD_TIMEOUT`, whatever the cause. After a read, the driver flushes the CPU and L2 caches when the
CPU has no DMA bus; before a write, it does not clean the data cache ([DMAs and
buses](#integ-dma)).

## BIOS commands {#sw-commands}

| Command | Arguments | Action |
|-------------------------------|---------------------------------------|------------------------------|
| `sdcard_detect` | none | Reads the card detect register: "inserted" when it reads 0 |
| `sdcard_init` | none | Runs the initialization; prints `OK` or `failed` |
| `sdcard_freq` | `<freq>` | Sets the card clock, prints the effective value |
| `sdcard_read` | `<block> [addr] [count]` | Reads `count` blocks (1 by default) to `addr`; dumps a single block |
| `sdcard_write` | `<block> <str>` | Fills one block with the repeated string and writes it |
| `sdcardboot` | `[manifest]` | Boots from the FAT partition ([Boot from the card](#sw-boot)) |
| `flash_from_sdcard` | `<filename>` | Copies a file of the card into the SPI flash |

`sdcard_read` and `sdcard_write` need an initialized card: run `sdcard_init` first, or let the
boot sequence do it. Without `addr`, `sdcard_read` reads into a buffer of the BIOS; with it, the
blocks go to any memory, the main RAM for a large `count`. [Step 3: talk to the
card](#gs-commands) shows a recorded session.

`flash_from_sdcard` exists when the SoC has a LiteSPI flash. It mounts the file system through
the FatFs disk functions of the last `sdcardboot` or `sataboot`, and selects none itself: run
`sdcardboot` first (it fails harmlessly when no boot file is found). On a SoC that also has
SATA, the boot sequence ends on the SATA disk, so run `sdcardboot` by hand ([Known
issues](#debug-known)).

## Boot from the card {#sw-boot}

`sdcardboot` is the boot method of priority 30 of the BIOS: the boot sequence tries it after the
serial, flash and ROM boots, and before the SATA and network boots. It mounts the FAT file
system of the card with FatFs, through the read function of the driver; the BIOS has no write
access to the file system.

1. **`boot.json`**: when this file exists at the root, the BIOS reads it, loads each file it
   names to its address, and jumps to the address given by `addr` in `bootargs`, or else to the
   address of the last image of the file.
2. **`boot.bin`**: otherwise, the BIOS loads this file at the start of the main RAM and jumps
   to it. A SoC without main RAM skips this step.

`sdcardboot <manifest>` reads another JSON file instead of `boot.json`. The BIOS checks every
entry before loading: it rejects two images at the same address and a file larger than the
memory up to the next image. The manifest below is the one of the LiteX documentation for Linux
on a VexRiscv-SMP SoC:

```json
{
    "Image":     "0x40000000",
    "rv32.dtb":  "0x40ef0000",
    "rootfs.cpio": "0x41000000",
    "opensbi.bin": "0x40f00000",
    "bootargs": {"addr": "0x40f00000", "r1": "0x40ef0000"}
}
```

The four files are copied to the FAT partition with the manifest; the BIOS jumps to OpenSBI with
the address of the device tree in `r1`. With the root file system on the card ([Linux](#sw-linux)),
the manifest drops `rootfs.cpio`. The boot cannot be tried in `litex_sim` ([What it does not
model](#emu-limits)).

## Linux {#sw-linux}

Linux drives LiteSDCard with the `litex_mmc` driver, upstream in the kernel at
`drivers/mmc/host/litex_mmc.c`. The driver is not part of LiteSDCard or LiteX: it finds the
hardware through a device tree node that LiteX generates from the `csr.json` of the build.

```sh
litex_json2dts_linux build/<target>/csr.json --root-device mmcblk0p2 --initrd disabled > soc.dts
```

`--root-device` puts the root file system on a partition of the card, and `--initrd disabled`
drops the RAM disk. The excerpt below is the output for the VexRiscv-SMP variant of `litex_sim
--with-sdcard`, a different SoC from the one of [Registers](#integ-registers): its interrupt
number differs.

```text
        chosen {
            bootargs = "console=liteuart earlycon=liteuart,0xf0002000 rootwait root=/dev/mmcblk0p2";
[...]
        vreg_mmc: vreg_mmc {
            compatible = "regulator-fixed";
            regulator-name = "vreg_mmc";
            regulator-min-microvolt = <3300000>;
            regulator-max-microvolt = <3300000>;
            regulator-always-on;
        };
[...]
            mmc0: mmc@f0001000 {
                compatible = "litex,mmc";
                reg = <0xf0001000 0x20>,
                      <0xf0001020 0x2c>,
                      <0xf000104c 0x20>,
                      <0xf000106c 0x20>,
                      <0xf000108c 0x100>;
                reg-names = "phy", "core", "reader", "writer", "irq";
                clocks = <&sys_clk>;
                vmmc-supply = <&vreg_mmc>;
                bus-width = <0x04>;
                interrupts = <3>;
                big-endian;
                status = "okay";
            };
```

The node gives the driver five register ranges, found from the register names: the PHY, the
core, block2mem (`reader`), mem2block (`writer`) and the event manager.

It adds the system clock, a fixed 3.3 V supply and the interrupt; with `--polling`, the
interrupt is left out. The generator still reads the interrupt number of the module, so on a SoC
without interrupts it stops with a `KeyError` (`sdcard_interrupt`) even with `--polling`. The bus
width is written as 4 in every case.

The generator reads the registers of both DMAs to build the node: on a SoC built with
`mode="read"` or `mode="write"` it stops with a `KeyError` and writes no device tree, so a SoC
needs `mode="read+write"` (the default of `add_sdcard`) to run Linux on the card.

**The driver.** The upstream driver (kernel master branch) handles SD cards only: it declares
the host unable to run MMC and SDIO devices, so Linux does not use an eMMC on LiteSDCard. It
drops the 8-bit bus and takes the bus width of the device tree, so the 4 of the node gives a
4-bit bus. The kernel sends ACMD6 itself; the driver only writes the width code into the PHY
`settings` register, at offset `0x18` of the `phy` range.

On the master branch of LiteSDCard, offset `0x18` of the PHY is `datar_timeout`: the write timeout
register `dataw_timeout` at `0x14` moved `settings` to `0x1c`, as the `phy` range of `0x20` bytes
above shows. The width code written by the driver therefore lands in the read timeout, and
`settings` keeps its reset value, so data transfers under Linux are expected to fail with this
gateware (not tested on hardware, [Known issues](#debug-known)).

With a driver and a gateware that agree on the register map, the card appears as `mmcblk0` with one
device per partition. The Linux-on-LiteX-VexRiscv project documents its use in its HOWTO:

```text
Plug the SDCard, it should be detected with all partitions on it:

`$ ls /dev/mmcblk*`:
/dev/mmcblk0    /dev/mmcblk0p1
[...]
$ mkdir /sdcard
$ mount /dev/mmcblk0p1 /sdcard/
[...]
$ echo "Hi SDCard" > /sdcard/test
$ cat /sdcard/test
Hi SDCard
```

The photo below shows such a system: a Trenz TEL0025 module, with a Lattice Certus-NX FPGA,
running Linux-on-LiteX-VexRiscv with its root file system on the second partition of its microSD
card. The Enjoy-Digital article on this board describes the option:

```text
**Move the rootfs off RAM entirely.** The board has an SD slot and the SoC has LiteSDCard, so
`--rootfs=mmcblk0p2` boots with `root=/dev/mmcblk0p2` and no initramfs resident in RAM at all.
```

![Linux on the Trenz TEL0025 (Lattice Certus-NX) with its root file system on the microSD card:
the kernel mounts `mmcblk0p2` as ext4, then Buildroot gives its login. Photo from an Enjoy-Digital
article.](sw_tel0025_linux_sd.jpg)

## Zephyr {#sw-zephyr}

`litex_json2dts_zephyr` describes the same module to Zephyr as a node named `sdhc` with the
compatible string `litex,mmc` and the alias `sdhc0`. The generator only writes the node; no
Zephyr driver is part of LiteX.

## A driver of your own {#sw-baremetal}

A driver for another environment follows the register sequence of the BIOS driver. The steps
below read `n` blocks into memory; [Register reference](#registers) gives the fields and
[Core: commands, responses, CRC](#core) the meaning of the command word.

1. **Clock and bus.** Write `phy_clocker_divider`, then `phy_settings` (0: 1-bit, 1: 4-bit,
   2: 8-bit). After a reset of the card, write `phy_init_initialize` for the 80 clocks.
2. **DMA.** Write 0 to `block2mem_dma_enable`, the buffer address to `block2mem_dma_base`,
   `512*n` to `block2mem_dma_length`, then 1 to `block2mem_dma_enable`.
3. **Command.** Write 512 to `core_block_length` and `n` to `core_block_count`. Write the block
   address to `core_cmd_argument`, then the command word to `core_cmd_command`: the index in bits
   13:8, the data type (1: read) in bits 6:5, the CRC check in bit 2 and the response type in
   bits 1:0. Write 1 to `core_cmd_send`. Use CMD17 for one block; for several, CMD18, preceded
   by CMD23 when the SCR offers it, else followed by CMD12 (R1b, response type 3) after the
   data. Data commands use the short response with the CRC check (`0x5` in bits 2:0).
4. **Completion.** Poll `core_cmd_event` until bit 0 (done) is set; bit 1 is an error, bit 2 a
   timeout and bit 3 a CRC error of the response. Then poll `core_data_event` the same way,
   where bit 2 is a timeout and bit 3 a CRC error, then `block2mem_dma_done`. A failed command
   also sets the error bit of `data_event`, since its data phase is skipped
   ([Limitations](#core-limitations)).
5. **Caches.** Invalidate or flush the data cache over the buffer when the DMA is not coherent.

A write follows the same steps with mem2block and the data type 2. A command without data uses
step 3 with data type 0 and step 4 without the data part.

## In the code {#sw-code}

| Function | LiteX file | Name |
|--------------------|--------------------------------------------|------------------------------------|
| Clock | `liblitesdcard/sdcard.c` | `sdcard_set_clk_freq` |
| Initialization | `liblitesdcard/sdcard.c` | `sdcard_init`, `mmc_init` |
| Transfers | `liblitesdcard/sdcard.c` | `sdcard_read`, `sdcard_write` |
| FatFs disk | `liblitesdcard/sdcard.c` | `fatfs_set_ops_sdcard` |
| Boot | `bios/boot.c`, `bios/main.c` | `sdcardboot` |
| Device trees | `litex_json2dts_linux.py` | `generate_dts_sdcard` |

A change to the registers of LiteSDCard needs the matching change in these files.

Where to go next: [Debugging](#debugging) when a card does not initialize, [Adding LiteSDCard
to a SoC](#integration) for the hardware side, [Boards and examples](#boards) for boards with a
slot or an eMMC.
