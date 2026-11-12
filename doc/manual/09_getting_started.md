```{=latex}
\part{Use it}
```

```{=html}
<h1 class="part">Part III. Use it</h1>
```

# Getting started {#getting-started}

This chapter takes you from a fresh machine to a card that answers. It checks the installation,
runs a simulated SoC in which the emulator plays the card, then builds a board with a microSD
slot. Each step gives the commands, what you should see, and what to check when you do not.

## Prerequisites {#gs-install}

LiteSDCard is a Python package built on Migen and LiteX, for Python 3.7 or newer. Install LiteX
with `litex_setup.py`, as its wiki describes: it installs Migen, LiteX, LiteX-Boards and the
cores, LiteSDCard included. To work on a clone of the repository, install it in development
mode:

```sh
git clone https://github.com/enjoy-digital/litesdcard
cd litesdcard
pip3 install -e .
```

The other tools depend on what you run, as the table below shows.

| Task | Tools |
|-----------------------------------|-----------------------------------------------------------------|
| Unit tests | Python 3, pytest |
| Standalone generator | Nothing more: it stops before the vendor tools |
| Simulated SoC (`litex_sim`) | Verilator, a C++ compiler, libevent, json-c, RISC-V GCC |
| Board build | The vendor toolchain of the board (Vivado for the Arty A7) |
| Serial console | `litex_term`, installed with LiteX |

`litex_setup.py --gcc=riscv` installs the RISC-V GCC toolchain that the BIOS needs.

## Step 1: check the installation {#gs-check}

The unit tests check the CRC, the PHY and the core in the Migen simulator, with no FPGA tool. Run
them from the root of the repository:

```sh
python3 -m pytest -v
```

**What you should see.** On the master branch, the suite ends with `45 passed` in less than a
minute. [Simulation and verification](#simulation) says what each test covers.

**If not.** An import error names the missing package: `litex` or `migen` when LiteX is not
installed, `litesdcard` when the clone is not installed with `pip3 install -e .`.

## Step 2: simulate a SoC with a card {#gs-sim}

`litex_sim` builds a LiteX SoC with a VexRiscv CPU and runs it in Verilator. With
`--with-sdcard`, it adds the PHY, the core and both DMAs, with the emulator in place of the card
([The SD card emulator](#emulator)). The BIOS then runs its driver against the emulator as it
would against a card.

```sh
litex_sim --with-sdcard
```

**What you should see.** Verilator compiles the SoC, then the BIOS banner appears in the
terminal. The session below was recorded with this command on the master branches of LiteX and
LiteSDCard; the banner is cut.

```console
--================ SoC =================--
CPU:		VexRiscv @ 1MHz
BUS:		wishbone 32-bit data/32-bit addr
CSR:		32-bit data big ordering
ROM:		128.0KiB
SRAM:		8.0KiB

--================ Boot ================--
Booting from serial...
Press Q or ESC to abort boot completely.
sL5DdSMmkekro
Timeout
Booting from SDCard in SD-Mode...
Booting from boot.json...
Error: filesystem mount failed (FatFs error 13)
SDCard boot failed.
No boot medium found

--============== Console ===============--

litex>
```

The BIOS tries its boot methods in order. After the serial boot, the SD card boot initializes
the card and reads its first block to mount a FAT file system. By default, the emulator of
`litex_sim` holds one buffer and no file system, so FatFs stops with error 13 (no file system
found) and the BIOS gives its prompt. This failure is expected here; [Boot from a FAT image in
simulation](#gs-sim-boot) gives the emulator a file system to boot from.

**If not.** A Verilator or compiler error stops the build: check that Verilator and the RISC-V
toolchain are in the `PATH`. A missing `sd_phy.v` or `sd_link.v` means LiteSDCard is not
installed from a full checkout, since the emulator is Verilog.

## Step 3: talk to the card {#gs-commands}

At the prompt, `help` lists the commands of the BIOS. Those of LiteSDCard detect the card,
initialize it, set its clock, and read or write one block.

```console
litex> help
[...]
sdcard_write             - Write SDCard block
sdcard_read              - Read SDCard block
sdcard_freq              - Set SDCard clock freq
sdcard_init              - Initialize SDCard
sdcard_detect            - Detect SDCard

litex> sdcard_detect
SDCard inserted.
litex> sdcard_init
Initialize SDCard: OK
litex> sdcard_read 0
Memory dump:
0x10001ce0  00 00 00 00 00 00 00 01 00 00 00 02 00 00 00 03  ................
0x10001cf0  00 00 00 04 00 00 00 05 00 00 00 06 00 00 00 07  ................
0x10001d00  00 00 00 08 00 00 00 09 00 00 00 0a 00 00 00 0b  ................
[...]
0x10001ed0  00 00 00 7c 00 00 00 7d 00 00 00 7e 00 00 00 7f  ...|...}...~....
litex>
```

`sdcard_init` runs the whole initialization of the BIOS driver: identification at the low
initialization clock up to CMD3, then the operating clock, high speed and the 4-bit bus
([Initialization](#sw-init)). `sdcard_read 0` then reads block 0 through
block2mem into a buffer of the BIOS and dumps its 512 bytes. The pattern is the initial content
of the emulator: its 128 words hold their own index.

`sdcard_detect` reads the card detect register. The emulator has no card detect pin, and the PHY
reads 0 when the pin is absent, so the command always answers "inserted" here.

A write goes through mem2block. `sdcard_write` fills a block with its string, prints the block
and writes it; a read then returns it. The session below continues the previous one.

```console
litex> sdcard_read 1000
Memory dump:
0x10001ce0  00 00 00 00 00 00 00 01 00 00 00 02 00 00 00 03  ................
[...]
litex> sdcard_write 0 LiteSDCard
Memory dump:
0x10001cf0  4c 69 74 65 53 44 43 61 72 64 4c 69 74 65 53 44  LiteSDCardLiteSD
[...]
litex> sdcard_read 0
Memory dump:
0x10001ce0  4c 69 74 65 53 44 43 61 72 64 4c 69 74 65 53 44  LiteSDCardLiteSD
0x10001cf0  43 61 72 64 4c 69 74 65 53 44 43 61 72 64 4c 69  CardLiteSDCardLi
[...]
litex> sdcard_freq 250000
Setting SDCard clk freq to 250 kHz
litex>
```

Block 1000 returns the same data as block 0: the emulator stores one block and ignores the
address ([What it does not model](#emu-limits)). On a real card each block is distinct.

`sdcard_freq` sets the card clock and prints the clock it gets, the system clock divided by an
even number ([The BIOS driver](#sw-bios) gives the rule). At the nominal 1 MHz of `litex_sim`,
250 kHz is both the request and the result.

**If not.** `Initialize SDCard: failed` means a command failed. In simulation, this points to the
software or the gateware, not to signal integrity: rebuild with the debug trace of the BIOS
driver, as [Initialization](#sw-init) shows, and see which command stops.

## Boot from a FAT image in simulation {#gs-sim-boot}

`litex_sim --sdcard-image` loads a raw disk image into the emulator, which then stores distinct
blocks ([The SD card emulator](#emu-limits)), so the BIOS boots from the card as on a board. The
image below is a 512 KiB FAT file system without partition table, with the bare metal demo of
LiteX and a `boot.json` that loads it at the start of the main RAM. The default simulation SoC
has no main RAM: `--integrated-main-ram-size` adds 64 KiB at `0x40000000`.

```sh
# Build the BIOS and the libraries of the SoC, without the gateware.
litex_sim --integrated-main-ram-size=0x10000 --with-sdcard --no-compile-gateware
# Build the demo for that SoC: demo.bin, linked for the main RAM.
litex_bare_metal_demo --build-path=build/sim
# A 512 KiB FAT image with the demo and its boot.json.
printf '{\n    "demo.bin": "0x40000000"\n}\n' > boot.json
mkfs.fat -C -n LITEX sdcard.img 512
mcopy -i sdcard.img boot.json demo.bin ::/
# Run the SoC with the image in the emulator.
litex_sim --integrated-main-ram-size=0x10000 --sdcard-image sdcard.img
```

**What you should see.** After the memory test of the main RAM and the serial boot timeout, the
BIOS mounts the file system, reads `boot.json`, copies `demo.bin` and jumps to it. The session
below was recorded with these commands on the master branches of LiteX and LiteSDCard, with
`helloc` typed at the prompt of the demo; the banners are cut.

```console
--================ Boot ================--
Booting from serial...
Press Q or ESC to abort boot completely.
sL5DdSMmkekro
Timeout
Booting from SDCard in SD-Mode...
Booting from boot.json...
Copying demo.bin to 0x40000000 (6264 bytes)...
[...]
Executing booted program at 0x40000000

--============== Liftoff! ==============--

LiteX minimal demo app built Nov 12 2026 11:30:35
[...]
litex-demo-app> helloc
Hello C demo...
C: Hello, world!
litex-demo-app>
```

**If not.** `Error: filesystem mount failed (FatFs error 13)` means the image holds no FAT file
system, and `Error: cannot open boot.json` that the file is not at its root; [Boot
fails](#debug-boot) lists the other messages.

## Step 4: a board {#gs-board}

The Arty A7 has no SD slot of its own. Its LiteX-Boards target plugs the Digilent Pmod MicroSD on
the `pmodd` connector and adds LiteSDCard with `--with-sdcard`. The system clock is 100 MHz by
default. Build and load the bitstream, then open the console:

```sh
python3 -m litex_boards.targets.digilent_arty --with-sdcard --build --load
litex_term /dev/ttyUSB1
```

`--pmod pmodd=numato_sdcard` selects the Numato adapter instead, which has no card detect pin.
Other boards, with an on-board slot or an eMMC, are listed in [Boards and examples](#boards).

**What to look for.** With a card inserted, `sdcard_detect` answers `SDCard inserted.`, and
`sdcard_init` ends with `Initialize SDCard: OK`. `sdcard_read 0` dumps the first block of the
card: with a partition table, its last two bytes are `55 aa`. No hardware log is reproduced
here; [Debugging](#debugging) covers a card that does not initialize.

**Boot from the card.** Format a partition of the card as FAT and copy a program to its root, with a
`boot.json` file that gives each file its load address. The BIOS loads the files and jumps to the
address of the last one (here the only one). The program below is linked for the main RAM of the
Arty target, at `0x40000000`:

```json
{
    "app.bin": "0x40000000"
}
```

At power-up, the BIOS reaches the SD card boot after the serial boot and loads `app.bin`. Type
`sdcardboot` at the prompt to run the same boot by hand. Without `boot.json`, the BIOS looks for
`boot.bin` and loads it at the start of the main RAM. [Boot from the card](#sw-boot) gives the
details, and the Linux images.

Where to go next: [Adding LiteSDCard to a SoC](#integration) to put it in your design,
[Software: BIOS, boot and Linux](#software) for the driver and the boot, [Boards and
examples](#boards) for the targets.
