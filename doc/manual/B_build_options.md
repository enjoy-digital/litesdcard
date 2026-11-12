# Build options {#build-options}

This appendix lists the parameters and options of every part of the project: the classes of the
gateware, the LiteX integration, the standalone generator, the configuration macros of the BIOS
driver, and the scripts of the benches. The chapters explain when to use them; this appendix
gives their names and defaults.

## Gateware classes {#opt-classes}

The classes are LiteX modules: add them to a SoC as attributes, and their registers join the bank
named after the attribute. `add_sdcard` instantiates them for most designs ([Adding LiteSDCard
to a SoC](#integration)).

| Class | Parameter | Default | Meaning |
|-------------------------|------------------------|-------------|--------------------------------------|
| `SDPHY` | `pads` | required | Platform pads, or the pads of `SDEmulator` |
| | `device` | required | FPGA device string; not used by the class |
| | `sys_clk_freq` | required | System clock frequency in Hz, for the timeouts |
| | `cmd_timeout` | `10e-3` | Response timeout in seconds |
| | `data_timeout` | `10e-3` | Read timeout per block in seconds |
| | `write_timeout` | `500e-3` | Write timeout per block in seconds: CRC status token and busy |
| `SDCore` | `phy` | required | The `SDPHY` whose engines the core drives |
| `SDBlock2MemDMA` | `bus` | required | Wishbone master interface, written by the DMA |
| | `endianness` | required | `"little"` or `"big"`, as the CPU |
| | `fifo_depth` | `512` | Bytes of the FIFO between the core and the DMA |
| `SDMem2BlockDMA` | `bus`, `endianness` | required | As for block2mem; the DMA reads |
| | `fifo_depth` | `512` | Bytes of the FIFO between the DMA and the core |
| `SDEmulator` | `platform` | required | Platform that receives the emulator Verilog sources |
| | `size` | `None` | Bytes of a block-addressed store, a multiple of 512 KiB; `None` with no `image`: one 512-byte buffer for every address |
| | `image` | `None` | Raw disk image that initializes the store; without `size`, the store is the image rounded up to 512 KiB |

The PHY takes its bus width from the pads: 1, 4 or 8 data lines. Its pads are subsignals of
the platform resource:

| Subsignal | Width | Use |
|------------------|-------------|------------------------------------------------------|
| `clk` | 1 | Card clock, an output |
| `cmd` | 1 | CMD line, bidirectional; needs a pull-up |
| `data` | 1, 4 or 8 | DAT lines, bidirectional; need pull-ups |
| `cd` | 1, optional | Card detect, read in `card_detect` |
| `rst` | 1, optional | Card reset, high for 4096 card clock periods, clock stopped, at `init_initialize` |
| `cmd_dir` | 1, optional | Direction of an external buffer on CMD: 1 when the host drives |
| `dat0_dir`, `dat13_dir` | 1, optional | Direction of external buffers on DAT0 and DAT1 to DAT3 |

The emulator pads (`cmd_t`, `dat_t` and their companions) select the emulator IO in place of the
FPGA IO. [PHY: clocking and IO](#phy) describes both.

The BIST frontend (`litesdcard/frontend/bist.py`) has `BISTBlockGenerator(random)` and
`BISTBlockChecker(random)`: `random=True` uses an LFSR, `False` a counter. Their streams are
32 bits wide while the core streams are 8 bits, and no integration in the repository or in
LiteX uses them ([DMAs](#dma)).

## LiteX integration {#opt-litex}

`add_sdcard` is a method of the LiteX SoC (`litex/soc/integration/soc.py`).

| Parameter | Default | Meaning |
|----------------------|----------------------|-----------------------------------------------|
| `name` | `"sdcard"` | Attribute of the SoC and name of the register bank |
| `sdcard_name` | `"sdcard"` | Platform resource requested for the pads |
| `mode` | `"read+write"` | `"read"`: block2mem only; `"write"`: mem2block only |
| `use_emulator` | `False` | Uses `SDEmulator` in place of the pads |
| `emulator_size` | `None` | `size` of `SDEmulator`: store size in bytes, a multiple of 512 KiB |
| `emulator_image` | `None` | `image` of `SDEmulator`: raw disk image file; without both, the store is one 512-byte buffer |
| `software_debug` | `False` | Adds the constant `<NAME>_DEBUG` to `soc.h`, which turns on the BIOS trace |

The method builds the PHY with `cmd_timeout=10e-1` and `data_timeout=10e-1` (1 s) and the default
write timeout (500 ms), the core, the
DMAs of `mode` at the data width of the main bus, on the DMA bus when the SoC has one, and an
event manager with an interrupt when the SoC has interrupts. The Linux device tree generator
needs both DMAs ([Software: BIOS, boot and Linux](#software)).

`add_spi_sdcard` drives a card in SPI mode with the LiteX `SPIMaster`, not with LiteSDCard:

| Parameter | Default | Meaning |
|----------------------|----------------------|-----------------------------------------------|
| `name` | `"spisdcard"` | Attribute, bank and platform resource |
| `spi_clk_freq` | `400e3` | SPI clock in Hz at reset; the BIOS sets 400 kHz, then 20 MHz, through the divider |
| `with_tristate` | `False` | Adds tristate buffers on `clk`, `cs_n` and `mosi` |
| `software_debug` | `False` | Adds the constant `<NAME>_DEBUG` to `soc.h` |

Many LiteX-Boards targets expose the two methods as the mutually exclusive options
`--with-sdcard` and `--with-spi-sdcard`; some targets with an eMMC add `--with-emmc`
([Boards and examples](#boards)). `litex_sim --with-sdcard` adds LiteSDCard with the emulator,
and `litex_sim --sdcard-image <file>` adds it with its store loaded from a raw disk image
([Simulation and verification](#sim-litex-sim)).

## Standalone generator {#opt-gen}

`litesdcard_gen` (`litesdcard/gen.py`) writes the core as Verilog in
`build/gateware/litesdcard_core.v`, with the register map in `build/csr.csv` and `build/csr.json`.
It runs no toolchain.

| Option | Default | Meaning |
|----------------------------|--------------|-----------------------------------------------------|
| `--clk-freq` | `100e6` | Frequency of the `clk` input in Hz |
| `--vendor` | `xilinx` | `xilinx`, `altera`, `intel` or `lattice`: the LiteX platform of the IO lowering |
| `--dma-data-width` | `32` | Width of the `wb_dma` Wishbone master: 32, 64, 128, 256 or 512 |

The core has 4 data lines, `cd`, `cmd_dir`, `dat0_dir` and `dat13_dir`, both DMAs, a Wishbone
slave `wb_ctrl` for the registers and an `irq` output ([Adding LiteSDCard to a
SoC](#integration)).

## BIOS driver macros {#opt-bios}

The BIOS driver (`liblitesdcard/sdcard.c` in LiteX) reads these macros. Each one defined in
`soc.h`, for instance with `self.add_constant("SDCARD_CLK_FREQ", 50000000)` in the target,
replaces the default.

| Macro | Default | Meaning |
|---------------------------------|--------------|---------------------------------------------|
| `SDCARD_CLK_FREQ_INIT` | `400000` | Card clock during the identification, up to CMD3 (SD card) or CMD7 (eMMC), in Hz |
| `SDCARD_CLK_FREQ` | `25000000` | Card clock after CMD3 (SD card), or after CMD7 and before high speed (eMMC), in Hz |
| `SDCARD_MMC_CLK_FREQ` | `50000000` | Card clock of an eMMC after the switch to high speed, in Hz |
| `SDCARD_CMD_RETRIES` | `16` | Attempts of the SD CMD6, ACMD51 and the data commands (reads, writes) |
| `SDCARD_DMA_TIMEOUT_US` | `1000000` | Wait for the done bit of a DMA, in µs |
| `SDCARD_DEBUG` | undefined | Prints each command and its events |
| `SDCARD_BOOT_PRIORITY` | `30` | Rank of `sdcardboot` among the boot methods |
| `SDCARD_BOOT_DISABLE` | undefined | Removes `sdcardboot` from the boot sequence |

Each clock is rounded to the even divider of the clocker, with the divider between 2 and 511
([Performance and resources](#perf-divider)). The driver also defines `SDCARD_CMD23_SUPPORT`,
`SDCARD_CMD18_SUPPORT` and `SDCARD_CMD25_SUPPORT` in its source: multi-block transfers, with
CMD23 when the SCR of the card lists it.

## Bench scripts {#opt-bench}

The scripts of `bench/` build a test SoC for one board. Run them from `bench/`: the build
directory and `csr.csv` are written in the working directory.

| Option | Scripts | Values | Meaning |
|------------------------------|----------------------|------------------------|--------------------------------|
| `--bench` | Arty, TrellisBoard | `soc` (default), `phy` | SoC with CPU and BIOS, or the PHY alone |
| `--variant` | Arty, TrellisBoard | `standard` (default), `minimal` | CPU and memory of the SoC |
| `--with-sampler` | Arty, TrellisBoard | flag | 8-bit sampler streamed over UDP |
| `--with-analyzer` | All three | flag | LiteScope on the PHY |
| `--build`, `--load` | All three | flag | Build, then load the bitstream |
| `--load-bios` | All three | flag | Loads the BIOS over Etherbone and reboots |

The scripts are `arty.py`, `genesys2.py` and `trellisboard.py`; [LiteScope
captures](#debug-litescope) describes the analyzer option. `bench/sim.py` takes `--trace`,
`--trace-fst`, `--trace-start` and `--trace-end` ([Bench simulation](#sim-bench)).
