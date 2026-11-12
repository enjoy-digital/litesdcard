# Adding LiteSDCard to a SoC {#integration}

This chapter puts LiteSDCard in a design. Most users call one LiteX method, `add_sdcard`, and
describe the card pins in their platform; the chapter explains what that method builds and what
it expects. It then covers the classes used directly, the SPI-mode alternative of LiteX, and the
standalone Verilog core for designs built without LiteX.

## At a glance {#integ-glance}

`add_sdcard` is a method of the LiteX SoC class (`litex/soc/integration/soc.py`). Its arguments
are listed below with their defaults.

| Argument | Default | Role |
|------------------------------|--------------------------|--------------------------------------------|
| `name` | `"sdcard"` | Name of the module, its registers and its interrupt |
| `sdcard_name` | `"sdcard"` | Name of the platform resource holding the card pins |
| `mode` | `"read+write"` | `"read"`: block2mem only; `"write"`: mem2block only |
| `use_emulator` | `False` | Use the emulator instead of platform pins |
| `emulator_size` | `None` | Emulator store size in bytes, a multiple of 512 KiB ([The SD card emulator](#emu-limits)) |
| `emulator_image` | `None` | Raw disk image file loaded into the emulator store |
| `software_debug` | `False` | Add the `SDCARD_DEBUG` constant: trace of the BIOS driver |

The BIOS driver and the device tree generator look for registers named `sdcard_*`, so keep
`name` at its default. `sdcard_name` changes only the resource: a target with an eMMC calls
`add_sdcard(sdcard_name="emmc")` and keeps the software unchanged.

## What add_sdcard builds {#integ-build}

The method requests the pins, builds the PHY, the core and the DMAs, and connects them as the
figure below shows. Both DMAs are bus masters of the SoC, and an event manager gathers the
events of the PHY, the core and the DMAs into one interrupt.

![What add_sdcard builds. The PHY drives the pins of the platform resource; the core sits
between the PHY and the two DMAs; the DMAs are masters of the DMA bus when the SoC has one,
else of the main bus; the event manager gathers the card detect of the PHY, the done events of
the core and those of the two DMAs, and raises one interrupt to the CPU. The CPU programs every
block through its registers.](integ_soc.svg)

The PHY gets two timeouts of 1 s, for the command responses and for the read blocks, instead of the
10 ms defaults of the class. The third one, for the CRC status token and the busy of a write, keeps
the 500 ms default of the class, since `add_sdcard` does not set it. All three are registers counted
in system clock cycles ([PHY: command and data engines](#phy-engines)). The DMAs have the data width
of the SoC bus and the byte order of its CPU ([DMAs](#dma)).

The build log of a SoC tells where each part went. The lines below come from `litex_sim
--with-sdcard`; the SD card adds two bus masters, one interrupt and one register bank.

```console
INFO:SoCBusHandler:sdcard_block2mem added as Bus Master.
INFO:SoCBusHandler:sdcard_mem2block added as Bus Master.
INFO:SoCIRQHandler:sdcard IRQ allocated at Location 2.
[...]
INFO:SoCCSRHandler:sdcard CSR allocated at Location 2.
[...]
Bus Masters: (4)
- cpu_bus0          : rw
- cpu_bus1          : rw
- sdcard_block2mem  : w
- sdcard_mem2block  : r
```

## The platform resource {#integ-pads}

The card pins are a platform resource, named `sdcard` by default, with the subsignals below.
Only `clk`, `cmd` and `data` are required; the PHY looks for the others and uses them when they
exist.

| Subsignal | Pins | Use |
|--------------------------|----------|----------------------------------------------------------------|
| `clk` | 1 | Card clock, output |
| `cmd` | 1 | Command line, bidirectional, pull-up |
| `data` | 1, 4 or 8 | Data lines, bidirectional, pull-ups; the count sets the widest bus |
| `cd` | 1 | Card detect, input; read as 0 (card present) when absent |
| `rst` | 1 | Card reset or power control, output, driven during the PHY init |
| `cmd_dir`, `dat0_dir`, `dat13_dir` | 1 each | Direction of an external level shifter, outputs |

The number of `data` pins fixes what the PHY can do. With 4 pins or more, the PHY adds the
constant `SDCARD_PHY_SUPPORT_4X`; with 8 pins, it also adds the constant that the BIOS reads
(`SDCARD_PHY_SUPPORT_8X`) to choose the 8-bit bus of an eMMC.

With 1 pin, the PHY has no 4-bit data path and `settings` resets to 1 bit, while the BIOS driver
selects the 4-bit bus whenever the card offers it, without checking `SDCARD_PHY_SUPPORT_4X`. A 1-bit resource therefore needs a
driver that keeps the 1-bit setting ([Initialization](#sw-init), [Known issues](#debug-known)).

The CMD and DAT lines need pull-ups, on the board or in the FPGA pads. The resource below, from
the Nexys4 DDR platform of LiteX-Boards, enables the internal pull-ups of a Xilinx FPGA. It also
has the `rst` pin, which controls the power of the slot on that board.

```python
("sdcard", 0,
    Subsignal("rst",  Pins("E2"),          Misc("PULLUP True")),
    Subsignal("data", Pins("C2 E1 F1 D2"), Misc("PULLUP True")),
    Subsignal("cmd",  Pins("C1"),          Misc("PULLUP True")),
    Subsignal("clk",  Pins("B1")),
    Subsignal("cd",   Pins("A1")),
    Misc("SLEW=FAST"),
    IOStandard("LVCMOS33"),
),
```

Each time the PHY starts its init sequence, it holds `rst` high for the time of 4096 card clock
periods, with the card clock stopped, then low. Lattice pads spell the pull-up
`Misc("PULLMODE=UP")`; the ECPIX-5 platform adds the three direction pins of its level shifter in
the same way.

An SD card slot takes a 3.3 V IO standard. LiteSDCard does not switch to 1.8 V signalling; a
soldered eMMC wired at 1.8 V uses a 1.8 V IO standard from power-up, as the Ti375 C529 platform
does.

**Pmod adapters.** A board without a slot takes one through a Pmod connector. LiteX-Boards
describes two adapters as extensions: `PmodSDCard` (Digilent Pmod MicroSD, with card detect) and
`PmodNumatoSDCard` (no card detect). Each defines both the `sdcard` and the `spisdcard` resources
on the connector, with the pull-ups and the 3.3 V IO standard of the platform.

```python
from litex_boards.extensions.pmod import PmodSDCard

platform.add_extension(PmodSDCard("pmodd"))
soc.add_sdcard()
```

Targets that call `add_pmods` accept the same from the command line, `--pmod pmodd=sdcard`, used
with `--with-sdcard`. The pins become IO registers and tristate buffers through LiteX, for each
FPGA family; [PHY: clocking and IO](#phy) gives the primitives per family.

## Clocking {#integ-clocking}

LiteSDCard runs entirely in the `sys` clock domain; it adds no clock domain and no clock
crossing. The PHY makes the card clock by dividing the system clock by an even number, 2 at
least, so the card clock is at most half the system clock.

| Card clock wanted | Where | Smallest system clock |
|------------------------------------|-------------------------------------------------|---------------|
| 400 kHz, identification (SD: CMD0 to CMD3; eMMC: CMD1 to CMD7) | BIOS, `SDCARD_CLK_FREQ_INIT` | Any |
| 25 MHz, SD default and high speed | BIOS, `SDCARD_CLK_FREQ` | 50 MHz |
| 50 MHz, eMMC high speed | BIOS, `SDCARD_MMC_CLK_FREQ` | 100 MHz |

Below these system clocks, the driver gets a lower card clock, which the card accepts. Above
them, the even divider rounds the card clock down: [Performance and resources](#performance)
gives the clock obtained for common system clocks.

The BIOS caps its divider at 511, the largest value of the 9-bit register, so the identification
clock stays at or below 400 kHz up to a system clock of 204.8 MHz (computed, [The BIOS
driver](#sw-bios)).

## DMAs and buses {#integ-dma}

The DMAs move the blocks between the core and the system memory, so the CPU never copies data.
`add_sdcard` connects them to the DMA bus of the SoC when it has one (`soc.dma_bus`, created for
CPUs with a coherent DMA port), and to the main bus otherwise. A Wishbone master is added per
direction: `sdcard_block2mem` writes, `sdcard_mem2block` reads.

On the main bus, the data cache of the CPU does not see the DMA writes. The BIOS driver therefore
flushes the CPU and L2 caches after a read when the CPU has no DMA bus
(`CONFIG_CPU_HAS_DMA_BUS` undefined); other software must do the same ([Caches](#dma-caches)).
Before a write, the buffer must be in memory: the BIOS relies on a write-through data cache and
does not clean it.

`mode` removes the DMA a design does not need. A read-only SoC (`mode="read"`) keeps
`sdcard_read`, `sdcardboot` and the FAT file system of the BIOS. It loses `sdcard_write`, and
`litex_json2dts_linux` stops with an error on such a SoC, since it reads the registers of both
DMAs ([Linux](#sw-linux)). The same holds for a write-only SoC (`mode="write"`).

## Interrupts {#integ-irq}

The event manager of `add_sdcard`, named `ev`, has the sources below. When the SoC has
interrupts, the method allocates one interrupt line for the module; on a SoC without them, the
software polls the same registers.

| Source | Kind | Raised when |
|----------------------------------|------------|------------------------------------------------------|
| `card_detect` | Pulse | The card detect input changes level |
| `block2mem_dma` | Pulse | The block2mem DMA has written its last word (read mode) |
| `mem2block_dma` | Pulse | The mem2block DMA has read its last word (write mode) |
| `data_done` | Level | The core sets `done` in `data_event` |
| `cmd_done` | Level | The core sets `done` in `cmd_event` |

The BIOS polls the event registers and does not use the interrupt. The device tree generator
passes the interrupt to the Linux driver, unless it runs with `--polling`. The interrupt output
of the core itself (`SDCore.irq`) is not connected by `add_sdcard`.

## Registers {#integ-registers}

All registers sit in one bank named after the module, in this order: the PHY, the core, the
block2mem DMA, the mem2block DMA, and the event manager. The `csr.csv` of a build lists them with
their addresses; the lines below come from the `litex_sim --with-sdcard` build.

```text
csr_base,sdcard,0xf0001000,,
csr_register,sdcard_phy_card_detect,0xf0001000,1,ro
csr_register,sdcard_phy_clocker_divider,0xf0001004,1,rw
[...]
csr_register,sdcard_core_cmd_argument,0xf0001020,1,rw
[...]
csr_register,sdcard_block2mem_dma_base,0xf000104c,2,rw
[...]
csr_register,sdcard_mem2block_dma_base,0xf000106c,2,rw
[...]
csr_register,sdcard_ev_status,0xf000108c,1,ro
csr_register,sdcard_ev_pending,0xf0001090,1,rw
csr_register,sdcard_ev_enable,0xf0001094,1,rw
```

[Register reference](#registers) describes every register and field. The Linux device tree
uses the start of each group as the base of a register range.

## Using the classes directly {#integ-classes}

`add_sdcard` is a thin wrapper. A design that consumes the blocks in gateware, for example to
stream them into a video pipeline, builds the PHY and the core itself and connects the 8-bit
streams of the core to its own logic instead of the DMAs.

```python
from litesdcard.phy import SDPHY
from litesdcard.core import SDCore

self.sdphy  = SDPHY(platform.request("sdcard"), platform.device, sys_clk_freq,
    cmd_timeout=1e-1, data_timeout=1e-1)
self.sdcore = SDCore(self.sdphy)
# Read data: self.sdcore.source (8-bit stream, last on the last byte of each block).
# Write data: self.sdcore.sink (8-bit stream).
self.comb += self.sdcore.source.connect(my_consumer.sink)
```

The registers of the PHY and the core need a master all the same: the CPU of the SoC, or a
bridge such as UARTBone or Etherbone. The BIOS driver expects the DMAs, so a design without them
needs its own command sequence; [Without the DMAs](#dma-custom) and [A driver of your
own](#sw-baremetal) give the order of the register accesses.

## SPI mode: add_spi_sdcard {#integ-spi}

LiteX offers a second way to reach a card: SPI mode, through its generic SPI master
(`litex/soc/cores/spi`), with no LiteSDCard gateware. It uses four pins of the same slot:
clock, chip select on DAT3, MOSI on CMD and MISO on DAT0. The platform resource is named
`spisdcard`.

| Argument | Default | Role |
|---------------------------------|-------------------------|------------------------------------------|
| `name` | `"spisdcard"` | Name of the module and of the platform resource |
| `spi_clk_freq` | `400e3` | Initial SPI clock; the driver changes it through a divider |
| `with_tristate` | `False` | Drive the pins through tristate buffers |
| `software_debug` | `False` | Add the debug constant of the SPI-mode driver |

SPI mode is smaller: an 8-bit shift register and a clock divider, with no DMA, no CRC engine and
no interrupt line. It is also slower, with one data line and every byte copied by the CPU.

The BIOS has a driver for it (`spisdcard.c`) and boots from it with the same `sdcardboot`
command. LiteSDCard is the choice when the speed matters or when Linux uses the card through
`litex_mmc`.

## Standalone core: litesdcard_gen {#integ-gen}

`litesdcard_gen` produces a Verilog core for a design that is not built with LiteX. It builds a
small SoC around `add_sdcard` and exposes its buses as ports, as the figure below shows.

![Ports of the core made by litesdcard_gen. The host programs the registers through the
Wishbone slave wb_ctrl; the DMAs reach the memory through the Wishbone master wb_dma; irq
signals the events; the sdcard_* pins go to the card.](integ_gen.svg)

```sh
litesdcard_gen --vendor xilinx --clk-freq 100e6 --dma-data-width 32
```

| Option | Default | Values |
|------------------------------------|----------------|------------------------------------------------|
| `--vendor` | `xilinx` | `xilinx`, `altera`, `intel`, `lattice`: selects the IO primitives |
| `--clk-freq` | `100e6` | Frequency of the `clk` input, in Hz |
| `--dma-data-width` | `32` | Data width of `wb_dma`, a width the LiteX bus handler supports |

The generator writes into `build/`: `gateware/litesdcard_core.v`, the register map (`csr.csv`,
`csr.json`) and the C headers (`software/include/generated/`). It does not run a vendor tool.

| Port | Direction | Content |
|-------------------------------|----------------|-----------------------------------------------------|
| `clk`, `rst` | In | System clock and reset of the core |
| `wb_ctrl_*` | Slave | 32-bit Wishbone, word addresses, registers from byte `0x800` |
| `wb_dma_*` | Master | Wishbone of `--dma-data-width` bits, word addresses, 4 GiB |
| `irq` | Out | Interrupt of the event manager |
| `sdcard_clk`, `sdcard_cmd`, `sdcard_data` | Out, inout | Card clock, CMD, 4 DAT lines |
| `sdcard_cd` | In | Card detect |
| `sdcard_*_dir` | Out | Level shifter direction pins |

The core has 4 data lines, a card detect pin and the three direction pins in its fixed IO list.
The CMD and DAT pins need pull-ups at the top level of the design. The generator is
[build-tested](#intro-status).

## In the code {#integ-code}

| Function | Repository and file | Name |
|-----------------|------------------------------------------------------|-----------------------------|
| SoC integration | LiteX, `litex/soc/integration/soc.py` | `add_sdcard`, `add_spi_sdcard` |
| Simulation SoC | LiteX, `litex/tools/litex_sim.py` | `--with-sdcard` |
| Pmod adapters | LiteX-Boards, `litex_boards/extensions/pmod.py` | `PmodSDCard`, `PmodNumatoSDCard` |
| Standalone generator | LiteSDCard, `litesdcard/gen.py` | `LiteSDCardCore` |

Where to go next: [Software: BIOS, boot and Linux](#software) for the software that drives this
hardware, [Boards and examples](#boards) for the targets that use it, [Register
reference](#registers) for the register map.
