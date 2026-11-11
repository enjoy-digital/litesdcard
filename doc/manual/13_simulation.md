# Simulation and verification {#simulation}

This chapter describes how LiteSDCard is checked: the Migen unit tests of the CRC, the PHY and the
core, the continuous integration, and the simulation of a whole SoC with the emulator in place of
a card. It is for contributors who change the gateware and for users who want to run the BIOS
driver without a board.

## Verification strategy {#sim-strategy}

Each part is checked at the cheapest level that exercises it. The unit tests run in the Migen
simulator in a few seconds; a SoC with a CPU, the BIOS driver and the emulator runs in Verilator;
the rest needs a board.

| Level | What runs | Card | Where |
|-------------|-------------------------------|---------------|------------------------------------|
| CRC | `CRC16` on 1, 4 and 8 lines | None | `test/test_crc.py` |
| PHY | Clocker, bit receiver, power-up clocks, command engines, data writer, read timeout | Bit patterns | `test/test_phy.py` |
| Core | Read and write commands, events, with a fake PHY | Fake PHY | `test/test_core.py` |
| Emulator | Block store of the wrapper | None | `test/test_emulator.py` |
| SoC | CPU, BIOS driver, core and DMAs, in Verilator | Emulator | `litex_sim` |
| Bench SoC | The SoC plus SDRAM, Etherbone and a sampler | Emulator | `bench/sim.py` |
| Hardware | A board with a slot or an eMMC | Real card | Not in CI |

The suite collects 36 tests and runs in about 4 s. The Verilator simulations are not part of it:
they are run by hand, and the CI does not run them.

## Running the tests {#sim-run}

The tests are Python `unittest` classes in `test/`, collected by pytest.

```sh
# Whole suite, as the CI runs it
python3 -m pytest -v
# One file, or the tests whose name matches
python3 -m pytest -v test/test_crc.py
python3 -m pytest -v test/test_phy.py -k clocker
```

The tests write no file in the working directory.

The continuous integration (`.github/workflows/ci.yml`) runs on Ubuntu 22.04 with Python 3.9. It
installs LiteX and its cores with `litex_setup.py`, then LiteSDCard. It checks that the register
appendix of this manual is up to date with the gateware ([Register reference](#registers)), then
runs `python3 -m pytest -v`. The register snapshots include the descriptions of the LiteX DMA and
event registers, so a change of those in LiteX also makes the check fail: regenerate as below. A second workflow, `.github/workflows/doc.yml`, checks the figures
and the sources of this manual ([Maintaining this manual](#maintenance)).

The register check elaborates the core of `litesdcard_gen` without a toolchain and compares the
result with the snapshots in `doc/manual/csr/`. After a change of a register, regenerate both:

```sh
python3 doc/manual/tools/csr_doc.py dump
python3 doc/manual/tools/csr_doc.py generate
```

## What the unit tests cover {#sim-coverage}

Most PHY tests drive the pads with strings of `-` (high) and `_` (low), one character per
system clock cycle, and compare the outputs the same way. The table lists what each test checks.

| Test | Checks |
|---------------------------------------|--------------------------------------------------------|
| `test_crc_inserter_ones` | 512 bytes of `0xff` give the CRC16 `0x7fa1` on 1, 4 and 8 lines; the 16 CRC bits are then serialized on every line |
| `test_crc_inserter_` `tuning_block` | The 512 bits of the tuning block, fed least significant bit first and copied on each of 4 lines, give `0x6b02` on every line |
| `test_clocker_div0` to `div8` | Dividers 0, 1 and 2 divide by 2, 3 and 4 by 4, 5 by 6, 8 by 8: card clock and `ce` pulse |
| `test_phyr_cmd`, `test_phyr_data` | The bit receiver finds the start bit and assembles bytes from CMD and from 4 DAT lines |
| `test_phyinit` | Each `initialize` strobe gives 80 card clocks |
| `test_phycmdw` | Three command bytes go out MSB first on CMD, with the output enable |
| `test_phycmdr` | A 3-byte response is received after its start bit, `last` on the third byte |
| `test_phydataw` | One block written, an accepted token (`010`), a short busy: one status, the block released |
| `test_phydataw_` `busy_timeout` | The same with DAT0 held low: the accepted status, then a timeout status, and the block released |
| `test_phydatar_` `backpressure_no_timeout` | A 1-bit read with the consumer stalled for three times the read timeout: no timeout, every byte delivered |
| `test_read_data_` `reception_starts_` `during_cmd_response` | The core asks the PHY for read data before the last response byte, then delivers the data byte |
| `test_write_block_` `delimiter_512`, `_above_512` | Two write blocks of 512 and of 1023 bytes: `last` on the final byte of each |
| `test_cmd_event_crc_ok`, `_crc_error`, `_crc_long_response`, `_crc_check_disabled` | `cmd_event` after a short response with a good or bad CRC7, after an R2 (CRC7 over the CID only), and with the check off for an R3 |
| `test_cmd_event_` `timeout`, `_timeout_data_cmd`, `_crc_error_data_cmd` | A response timeout sets `timeout` and `error`; on a data command, a timeout or a CRC7 error also sets `data_event.error` |
| `test_write_timeout_` `sets_data_timeout` | A timeout status of the data writer ends a write with `data_event` done and timeout |
| `test_zero_block_count_` `data_cmd` | A read or write command with `block_count` 0 returns to idle with `data_event.done` |
| `test_default_single_` `block_buffer`, `test_block_store_*` | The emulator store: one 512-byte buffer by default; with `size` or `image`, one block per address, the image words and the capacity given to the card model, and an invalid size rejected |

Two tests of `test_phy.py`, `test_phycrc` and `test_phydatar`, contain only `pass`: they
always pass and check nothing. The gaps are therefore:

- the data reader of the PHY: no test of a block read with its CRC16 check, or of its timeout;
- the CRC16 split of a 4-bit or 8-bit block over its lines: the tuning-block test copies one
  serial stream on every line, so it checks the CRC engine on a second pattern, not the per-line
  CRCs of the tuning block on a 4-bit bus;
- the CRC status tokens other than "accepted", and the bus widths of the data writer;
- the DMAs, the Verilog card model of the emulator and the BIST frontend.

The data path between the card and the DMAs and the BIOS driver are exercised only by the SoC
simulation below and by hardware.

## SoC simulation with the emulator {#sim-litex-sim}

`litex_sim --with-sdcard` builds the LiteX simulation SoC with a VexRiscv CPU and calls
`add_sdcard("sdcard", use_emulator=True)`. The PHY, the core and both DMAs are those of a board,
and the emulator replaces the card ([The SD card emulator](#emulator)). Verilator compiles the
emulator Verilog with the rest of the SoC, and the BIOS console appears in the terminal.

```sh
# Build and run the simulated SoC, then type the BIOS commands at the prompt
litex_sim --with-sdcard
# The same with a waveform of the whole SoC (VCD, or FST with --trace-fst)
litex_sim --with-sdcard --trace
```

At the prompt, `sdcard_init` runs the initialization of the BIOS driver on the emulator and
prints `Initialize SDCard: OK` when it succeeds; `sdcard_read 0` then reads a block through
block2mem and prints it. [Getting started](#getting-started) shows a recorded session.

The simulation SoC runs at 1 MHz, so the card clocks are much lower than on a board
([The BIOS driver](#sw-bios) gives the values). The timeouts scale with the system clock: the
1 s of `add_sdcard` is `1000000` cycles.

`add_sdcard` builds the emulator with its default store, one 512-byte buffer for every block
address, so `sdcardboot` does not work in simulation ([What the emulator does not
model](#emu-limits)). The simulation suits the initialization, the command and data engines and
the DMAs, not the boot path.

## Bench simulation {#sim-bench}

`bench/sim.py` adds to the simulation SoC a simulated SDRAM, Etherbone on a `tap0` network
interface at `192.168.1.50`, and the sampler of the hardware benches, which sends an 8-bit
counter through a DRAM FIFO and UDP to the host at `192.168.1.100`. The card is the emulator, as
with `litex_sim --with-sdcard`.

```sh
# Run from bench/: the build directory and csr.csv are written in the working directory;
# needs a tap0 interface
cd bench
python3 sim.py
python3 sim.py --trace --trace-start 0 --trace-end 1000000
```

The Ethernet module of the simulator opens `tap0`, which needs the rights to create it. The
script passes `--trace` to both `trace` and `trace_fst`, so a trace is always written in FST and
`--trace-fst` has no effect.

## Adding a test {#sim-adding}

A test of the core does not need the PHY. `test_core.py` replaces it with a fake object that has
the four stream endpoints the core uses (`cmdw`, `cmdr`, `dataw`, `datar`), with the layouts of
the PHY. One generator per endpoint plays the PHY, and one plays the software.

```python
class _FakePHY:
    def __init__(self):
        self.cmdw  = _EndpointPair(sink_layout=[("data", 8), ("cmd_type", 2)])
        self.cmdr  = _EndpointPair(
            sink_layout   = [("cmd_type", 2), ("data_type", 2), ("length", 8)],
            source_layout = [("data", 8), ("status", 3)])
        # [...] dataw and datar, with the layouts of the PHY

dut = SDCore(_FakePHY())
run_simulation(dut, [host_gen(), cmdw_gen(), cmdr_gen(), datar_gen()])
```

`host_gen` sets the registers of the core as the BIOS driver does: `block_length`,
`block_count`, the fields of `cmd_command`, then a write strobe on `cmd_send`. The generator of
`cmdr` sends the response bytes with a `status`, and `last` on the final byte. The generator of
`datar` sends data bytes with `status` and `drop`, as [PHY: command and data
engines](#phy-engines) describes.

A test of a PHY engine instantiates the engine alone with `_sdpads_layout(4)`, as
`test_phycmdr` does. It drives `pads_in.valid` and the pad inputs from a bit string, holds
`pads_out.ready` at 1 (one card clock per system clock cycle) and checks the stream outputs. Keep
each test under a second: the suite runs on every push.

## Where to go next {#sim-next}

[Debugging](#debugging) for the symptoms on hardware; [The SD card emulator](#emulator) for what
the emulator models; [Core: commands, responses, CRC](#core) for the registers a test drives.
