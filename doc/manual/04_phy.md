# PHY: clocking and IO {#phy}

This chapter describes the part of the PHY that touches the pins: the pads, the clocker, the
timing at the pins and the IO registers that LiteX generates for each FPGA family. Read it to
choose a card clock, to write a platform resource or to debug signal integrity. The engines that
move the bits are in [PHY: command and data engines](#phy-engines).

## At a glance {#phy-glance}

| Item | Value |
|------------------------|--------------------------------------------------------------------------|
| Class | `SDPHY` (`litesdcard/phy.py`), signature below |
| Pads | `clk`, `cmd`, `data` (1, 4 or 8 lines); optional `cd`, `rst`, direction pins |
| Card clock | System clock divided by an even number from 2 to 512 |
| Fastest card clock | Half the system clock |
| Clock control | `divider` register; the clock runs only while an engine needs it |
| Outputs | Registered on the system clock, change 1 system clock cycle after the card clock rises |
| Inputs | Registered on the system clock edge that drives the card clock high |
| IO primitives | `SDROutput` and `SDRTristate` of LiteX, lowered per FPGA family |
| Clock domains | System clock only |

```python
SDPHY(pads, device, sys_clk_freq, cmd_timeout=10e-3, data_timeout=10e-3, write_timeout=500e-3)
```

The `device` parameter is not used by the class. `add_sdcard` passes the device name of the
platform and response and read timeouts of 1 s instead of the 10 ms defaults; it does not pass
`write_timeout`, so the write timeout keeps its default of 500 ms ([Timeouts](#eng-timeouts)).

## Pads {#phy-pads}

The PHY takes the pads of a platform resource, usually named `sdcard`. The table below lists the
subsignals it looks for. Only `clk`, `cmd` and `data` are required; the PHY checks for the others
with `hasattr` and adds the matching logic when they exist.

| Subsignal | Width | Direction | Use |
|-----------------|----------|-------------|--------------------------------------------------------|
| `clk` | 1 | Output | Card clock |
| `cmd` | 1 | Inout | CMD line |
| `data` | 1, 4, 8 | Inout | DAT lines; the width sets the widest bus the PHY supports |
| `cd` | 1 | Input | Card detect, read as is in `card_detect` |
| `rst` | 1 | Output | Card reset, high during the reset phase of the init block |
| `cmd_dir` | 1 | Output | Direction of an external buffer on CMD |
| `dat0_dir` | 1 | Output | Direction of an external buffer on DAT0 |
| `dat13_dir` | 1 | Output | Direction of an external buffer on DAT1 to DAT3 |

The PHY sizes everything from `len(pads.data)`. With 8 data pins it also adds the constant
`support_8x`, which LiteX exports as `SDCARD_PHY_SUPPORT_8X` for the BIOS driver. Pads that have
`cmd_t` and `dat_t` fields are those of the emulator: the PHY then uses its emulator IO
([Emulator IO](#phy-emulator-io)).

CMD and the DAT lines need pull-ups, internal or on the board, as the comments of `gen.py` state.
The platform resource sets them with the IO standard. LiteX-Boards does it for instance with
`Misc("PULLMODE=UP")` on ECP5 and `Misc("PULLUP True")` on Xilinx, and the `PmodSDCard`
extension requests the pull-up setting of the platform on CMD and DAT.

The PHY does not know the IO voltage. Standard SD cards in default and high speed signal at
3.3 V; the platform chooses the IO standard. The eMMC resource of the Efinix Ti375 C529 Dev Kit,
for example, uses `1.8_V_LVCMOS`.

### Card detect {#phy-card-detect}

The `card_detect` register reads the level of the `cd` pin, with no inversion. Without a `cd`
pin it reads 0. The polarity depends on the slot and the board, so software must know which
level means "card present" ([Debugging](#debugging)).

On each change of the level, the PHY pulses `card_detect_irq` for one system clock cycle.
`add_sdcard` connects it to the `card_detect` event of its interrupt controller.

## The internal pads and the engines {#phy-sdpads}

Between the engines and the IO sits an internal record, `sdpads`. It has a clock request, an
output and an output enable for CMD, an output for each DAT line with one output enable for all of
them, the two inputs, and `data_i_ce`, which marks when the inputs are valid.

Five sub-blocks drive this record: the init block and the four engines. The PHY ORs their outputs.
An idle block drives zeros, and the core runs one phase at a time, so the OR selects the active
block. The one overlap is a read command: the command reader and the data reader are both active,
the first on CMD and the second listening on the DAT lines. Every block receives the inputs, and the
`ce` pulse of the clocker as `ready`.

The single output enable of the DAT lines means that all of them change direction together. The
IO layer replicates it to each pin.

## Clocker {#phy-clocker}

The clocker turns the system clock into the card clock. It counts system clock cycles, toggles
an internal clock every half period, and gates that clock so that it only reaches the pin while
an engine asks for it. The figure below shows its parts.

![The clocker. Follow the clock from the divider register through the counter to the gate and the
IO register; `ce` goes to the engines, and the engines answer with `stop` and with their clock
request.](phy_clocker.svg)

### Divider {#phy-divider}

The `divider` register is 9 bits wide and resets to 256. The half period, in system clock cycles,
is `(divider + 1) >> 1`; the values 0 and 1 give the same half period of one cycle, since the
counter reloads when it reaches 1 or less. The card clock is therefore the system clock divided by
the even number at or above `divider`, and by 2 for the values 0 to 2:

| `divider` | Division | Card clock |
|-----------|----------|------------------------------|
| 0, 1, 2 | 2 | f~sys~ / 2, the fastest |
| 3, 4 | 4 | f~sys~ / 4 |
| 5, 6 | 6 | f~sys~ / 6 |
| 2n - 1, 2n | 2n | f~sys~ / 2n |
| 256 (reset) | 256 | f~sys~ / 256 |
| 511 | 512 | f~sys~ / 512, the slowest |

Only even divisions exist, so the duty cycle is always 50 %. The step between two card clock
frequencies is coarse near the top: with a 100 MHz system clock the choices are 50 MHz, 25 MHz,
16.7 MHz and so on. The unit tests check the divisions for the dividers 0 to 5 and 8
(`test/test_phy.py`).

The BIOS driver computes the divider from a target frequency, rounding up, and clamps it to the
range 2 to 511 ([Software: BIOS, boot and Linux](#software)). A custom driver writes the register
directly.

### Clock enable and back-pressure {#phy-clock-enable}

The clocker pulses `ce` for one system clock cycle at each rising edge of its internal clock. The
engines step on `ce`: they change their outputs and count clock cycles there. `ce` runs all the
time, even when the card clock is gated, so the init block can count during its reset phase with
the card clock stopped.

The card clock reaches the pin only while one of the five blocks asserts its clock request. The
request goes through an enable latch, sampled once per period while the internal clock is high.
A change of the request therefore never produces a short pulse: the card sees whole periods or
none. When gated, the clock pin stays high.

The `stop` input freezes the counter. The data writer asserts it while it has no byte to send,
and the data reader while its consumer is not ready. The card clock then holds its level until
`stop` falls ([Back-pressure](#arch-backpressure)).

The internal clock is a register toggled by the counter. `ce` and the gated clock are
combinational, derived from that register and its delayed copy, not extra registers. The
repository history records that this keeps the PHY working at the low end of the system clock
range, such as a 50 MHz system clock.

## Timing at the pins {#phy-timing}

Outputs and inputs pass through IO registers clocked by the system clock, including the card
clock itself. The figure below shows the pins with a divider of 4, from a simulation of the PHY
sending one command byte: the card clock, the CMD output, and `data_i_ce`, which tells the engines
that the registered inputs are valid.

![Card clock, CMD output and input sampling with a divider of 4. Look at the dotted lines: the
input register samples at the system clock edge that drives the card clock high, and CMD changes
one system clock cycle later.](phy_timing.svg)

The card clock leaves through an output register fed with the inverted gated clock, so it rises
one system clock cycle after `ce`. The engine outputs change at `ce` too and pass through their
own registers. The net result is that CMD and the DAT outputs change one system clock cycle after
the card clock rising edge.

The card samples on the rising edge. Each bit is therefore stable during the whole period minus
one system clock cycle before that edge, and one system clock cycle after it. With a divider of
2, the outputs change on the falling edge of the card clock.

The inputs are sampled by the input registers at every system clock edge. `data_i_ce` is the
rising edge of a copy of the card clock delayed like the clock pin, so it selects the sample taken
at the system clock edge that drives the card clock high. The engines read CMD and DAT only in
that cycle.

From the card's point of view, the host samples just before the next rising edge arrives at the
card. The clock path to the card, the card output delay and the path back to the input register
must fit between the edge on which the card changes its output and that sample.

That window is half a card clock period when the card drives after the falling edge, as in
default speed. It is a full period when the card drives after the rising edge, as in high
speed.

## IO {#phy-io}

The IO block, `SDPHYIOGen`, connects the internal pads to the pins with three LiteX primitives.
The figure below shows the CMD and DAT path.

- The card clock goes through an `SDROutput` (an output register).
- CMD goes through an `SDRTristate`: registers for the output, the output enable and the input,
  around a tristate buffer.
- The DAT lines go through a second `SDRTristate`, with the single output enable replicated to
  every line.
- The direction pins, when present, are `SDROutput` copies of the output enables: `cmd_dir`
  follows the CMD enable, `dat0_dir` and `dat13_dir` both follow the DAT enable.
- `rst`, when present, is driven by the init block without a register.

![IO of CMD and DAT. The engine outputs are registered with their output enable before the
tristate buffer; the input is registered on the way back. A registered copy of the output enable
drives the direction pins of an external level shifter.](phy_io.svg)

The direction pins serve boards that connect the card through a buffer or a level shifter, which
must know which way to drive. They are registered like the data, so the buffer turns around in
the same system clock cycle as the FPGA pin. LiteX-Boards uses them on the ECPIX-5.

### Per-family IO {#phy-io-families}

LiteSDCard contains no vendor primitive. `SDROutput`, `SDRInput` and `SDRTristate` are generic
LiteX specials, and each LiteX platform replaces them with the primitives of its family when it
generates the Verilog. The table below gives what the PHY becomes on each family, as LiteX
lowers it in `litex/build/<vendor>/common.py`.

| Family (toolchain) | Tristate buffer | Output register | Input register |
|------------------------------|-------------------------|------------------------|--------------------|
| Xilinx 7-Series | `IOBUF` | `FDCE` | `IDDR` |
| Xilinx UltraScale(+) | `IOBUF` | `FDCE` | `FDCE` |
| Xilinx Spartan-6 | `IOBUF` | `ODDR2` | `IDDR2` |
| Altera (Cyclone and others) | Generic | `ALTDDIO_OUT` | `ALTDDIO_IN` |
| Altera MAX 10 | Generic | Fabric | Fabric |
| Altera Agilex 3 and 5 | `tennm_ph2_io_*` | Fabric (clock pin: DDIO cell) | Fabric |
| Lattice ECP5 (Trellis) | `TRELLIS_IO` | `OFS1P3BX` | `IFS1P3BX` |
| Lattice ECP5 (Diamond) | `BB` | `OFS1P3BX` | `IFS1P3BX` |
| Lattice NX (Radiant) | Generic | `OFD1P3BX` | `IFD1P3BX` |
| Lattice NX (Oxide) | Generic | `FD1P3BX` | `FD1P3BX` |
| Lattice iCE40 | `SB_IO` | `SB_IO` | `SB_IO` |
| Gowin GW5A | `IOBUF` | `DFFSE` | `DFFSE` |
| Gowin, other families | `IOBUF` | Fabric | Fabric |
| Efinix | GPIO block | GPIO block | GPIO block |
| Cologne Chip GateMate | `CC_IOBUF` | `CC_DFF` | `CC_DFF` |
| Any other platform | Generic | Fabric | Fabric |

Notes on the table:

- *Generic* is the Migen tristate, which the vendor tool infers. *Fabric* is a plain register
  clocked by the system clock, which the tool may or may not pack into the IO cell; on MAX 10
  the LiteX comments rely on the Quartus fast input and output register settings for that.
- The output enable register is in the IO cell on Xilinx, ECP5 with Trellis, Gowin GW5A, iCE40,
  Efinix and GateMate. Elsewhere LiteX uses its generic SDR tristate, whose output enable is a
  fabric register even when the buffer and the data registers are vendor primitives (ECP5 with
  Diamond, Altera, Lattice NX, other Gowin families). On Agilex, CMD and DAT use fabric registers
  for the output, the output enable and the input; only the card clock and the direction pins,
  which are plain `SDROutput`, use a DDIO output cell.
- The Xilinx and Altera input registers are DDR input cells with one output used. The Spartan-6
  and Altera output registers are DDR output cells fed with the same bit on both edges.
- The LiteX comments of `litex/build/altera/common.py` state that `ALTDDIO_IN` re-registers its
  rising edge output, one clock more than the `SDRInput` contract, while `SDPHYIO` compensates one
  register only. If that holds on the Altera families other than MAX 10, the engines read the
  sample taken one system clock cycle before the edge described in
  [Timing at the pins](#phy-timing), which shortens the input window by one system clock cycle.
  This has not been checked in simulation or on hardware.
- Efinix places the input, output and enable registers in the GPIO block of the Efinity
  interface; iCE40 places all three in `SB_IO`.

Registers in the IO cells give the same clock-to-pin delay on every pin, which the sampling scheme
of [Timing at the pins](#phy-timing) assumes. Where the table says *Fabric*, the delays depend on
placement; check the timing report or the IO register settings of the tool.

### Emulator IO {#phy-emulator-io}

With the pads of the emulator, the PHY uses `SDPHYIOEmulator` instead. It connects the internal
pads to the emulator ports without tristate, on four DAT lines, but with the timing of the hardware
IO: the card clock is the inverted clocker output through a register, so it idles high when gated,
and CMD and DAT go through one register in each direction, as the `SDROutput` and `SDRTristate` of
`SDPHYIOGen`. The edges the emulator sees relative to CMD and DAT are therefore those of
[Timing at the pins](#phy-timing), and `data_i_ce` comes from the same logic and the same delay as
on hardware. [The SD card emulator](#emulator) describes the other side.

## Limits {#phy-limits}

- The card clock is at most half the system clock. A 50 MHz high speed clock needs a system clock
  of 100 MHz or more; a 25 MHz default speed clock, 50 MHz or more.
- Only even divisions of the system clock exist. The BIOS driver rounds the divider up, so the
  card clock is at or below the target.
- The PHY drives single data rate signals at 3.3 V or 1.8 V levels as the platform sets them. It
  has no voltage switch, no DDR mode and no tuning, so the UHS-I modes are out of reach
  ([What it is not](#intro-limits)).
- The board decides the rest: trace lengths, level shifters and pull-ups all count in the input
  timing budget of [Timing at the pins](#phy-timing).

The hardware that has been tested is listed in the [status table](#intro-status).

## In the code {#phy-code}

| Function | File | Classes |
|------------------------|----------------------------------------|----------------------------------|
| PHY top level | `litesdcard/phy.py` | `SDPHY` |
| Card clock | `litesdcard/phy.py` | `SDPHYClocker` |
| IO | `litesdcard/phy.py` | `SDPHYIOGen`, `SDPHYIOEmulator` |
| IO primitives | LiteX `litex/build/io.py` | `SDROutput`, `SDRTristate` |
| Per-family lowering | LiteX `litex/build/*/common.py` | Special overrides |
| Divider tests | `test/test_phy.py` | `test_clocker_*` |

Where to go next: [PHY: command and data engines](#phy-engines) for what happens on each card clock
cycle, [Adding LiteSDCard to a SoC](#integration) for the platform resource, [Debugging](#debugging)
for CRC errors and timeouts.
