```{=latex}
\part{The core}
```

```{=html}
<h1 class="part">Part II. The core</h1>
```

# Architecture overview {#architecture}

This chapter shows how the parts of LiteSDCard fit together: the blocks, the clock, the streams
between them, the registers and one read from start to end. Read it before the detailed chapters
of Part II, or before you connect the core to something other than the DMAs. The protocol itself
is explained in [SD cards in a nutshell](#sd-primer).

## At a glance {#arch-glance}

| Item | Value |
|------------------|----------------------------------------------------------------------------------|
| PHY | `SDPHY` (`litesdcard/phy.py`): clocker, init block, four engines, IO |
| Core | `SDCore` (`litesdcard/core.py`): command frames, responses, CRC7, read FIFO, events |
| CRC | `CRC` and `CRC16` (`litesdcard/crc.py`), used by the core and the PHY |
| DMAs | `SDBlock2MemDMA`, `SDMem2BlockDMA` (`litesdcard/frontend/dma.py`), Wishbone masters |
| Integration | `add_sdcard` of LiteX, or the standalone generator `litesdcard_gen` |
| Clock | The system clock (`sys`) for every block; the card clock is divided from it |
| Streams | 8 bits between the PHY, the core and the DMAs |
| Control | Registers on the CSR bus; done bits polled or turned into interrupts |
| Bus widths | 1 and 4 bits, 8 bits when the platform gives 8 data pins |

## Blocks {#arch-blocks}

LiteSDCard is a chain of four blocks between the card and the system memory, as the figure below
shows. The PHY drives the card pins. The core turns register writes into command frames and
frames the data blocks. The DMAs move the data between the core and the memory over the DMA bus,
so the CPU never copies data bytes.

![Blocks of LiteSDCard as `add_sdcard` builds them. Follow the data from the card through the IO
and the engines of the PHY to the core, then to block2mem on a read or from mem2block on a write.
The CSR bus reaches the PHY, the core and the DMAs.](arch_blocks.svg)

Inside the PHY, the engines decide what happens on each card clock cycle. The init block sends
the power-up clocks, the command engines handle the CMD line and the data engines the DAT lines.
The clocker makes the card clock and tells the engines when it ticks (`ce`); the engines can
pause it (`stop`).

The core never touches a pin. It sends the six bytes of a command to the command writer, receives
the response bytes from the command reader, and passes data bytes to and from the data engines.
[Core: commands, responses, CRC](#core) describes it; [PHY: clocking and IO](#phy) and [PHY:
command and data engines](#phy-engines) describe the PHY.

The DMAs are LiteX Wishbone DMAs with a FIFO and a width converter in front. They are optional:
`add_sdcard` builds one or both depending on its `mode`, and a design can consume the core
streams with its own logic instead ([DMAs](#dma)).

## One clock domain {#arch-clock}

Every block of LiteSDCard runs in the system clock domain. The card clock is not a clock domain
of the design: the clocker toggles it with a counter, and the engines move one bit when the
clocker pulses `ce`. The design has no clock domain crossing and needs no timing constraint
beyond those of the IO registers.

The IO registers that drive and sample the pins also run on the system clock. A divided card
clock gives the card several system clock cycles of setup on each bit, and the PHY samples the
inputs at a fixed system clock edge ([Timing at the pins](#phy-timing)).

The emulator is the one exception. It models a card, so it runs from the card clock it receives
([The SD card emulator](#emulator)).

## Streams between the blocks {#arch-streams}

The blocks talk through LiteX streams: `valid`, `ready`, `first` and `last` plus payload fields.
Every data stream carries one byte per transfer. The table below lists them with their extra
fields; the PHY streams are attributes of its engines (`phy.cmdw`, `phy.cmdr`, `phy.dataw`,
`phy.datar`).

| Stream | Direction | Payload |
|----------------------------|------------------------|------------------------------------------------|
| `phy.cmdw.sink` | Core to command writer | `data` (8), `cmd_type` (2) |
| `phy.cmdr.sink` | Core to command reader | `cmd_type` (2), `data_type` (2), `length` (8) |
| `phy.cmdr.source` | Command reader to core | `data` (8), `status` (3) |
| `phy.dataw.sink` | Core to data writer | `data` (8), `last_block` (1) |
| `phy.dataw.source` | Data writer to core | `status` (3), one per block |
| `phy.datar.sink` | Core to data reader | `block_length` (10), one per block |
| `phy.datar.source` | Data reader to core | `data` (8), `status` (3), `drop` (1) |
| `core.source` | Core to block2mem | `data` (8), blocks delimited by `first` and `last` |
| `core.sink` | mem2block to core | `data` (8) |

The command reader sets `last` on the last byte of a response. The data reader sets `first` and
`last` around each block including its CRC bytes, and `drop` on the CRC bytes, which the core
discards. The write side carries no block marks: the core counts `block_length` bytes and marks
the last byte of each block itself.

The `status` field carries the same codes in every stream. They are the constants
`SDCARD_STREAM_STATUS_<name>` of `litesdcard/common.py`:

| Code | Name | Meaning |
|---------|----------------|-----------------------------------------------------|
| `0b000` | `OK` | Byte received, no error known |
| `0b001` | `TIMEOUT` | No start bit, or not all bytes, in time |
| `0b010` | `DATAACCEPTED` | CRC status token "data accepted" |
| `0b101` | `CRCERROR` | Bad CRC16 on read, CRC error token on write |
| `0b110` | `WRITEERROR` | Write error token |

### Back-pressure {#arch-backpressure}

Data never overflows inside LiteSDCard, because the card clock waits for the slowest consumer,
whether a DMA or a consumer of the core stream that applies back-pressure. A disabled block2mem is
the exception: it accepts and drops the bytes ([DMAs](#dma)). On a read, when block2mem stops
accepting bytes, the 64-byte read FIFO of the core fills, the data reader sees `ready` low and
asserts `stop`, and the clocker freezes the card clock until a byte leaves. The read timeout does
not count while the card clock is frozen ([Timeouts](#eng-timeouts)).

On a write, the data writer asserts `stop` while no byte is available on its sink, so the card
clock also waits for mem2block. The card only sees a longer clock period: in SD mode the host may
slow down or pause the clock to throttle a transfer.

## Registers {#arch-registers}

Software controls everything through registers. With `add_sdcard` and the default name, their
names start with `sdcard_` followed by the block, as the table below groups them. The
[Register reference](#registers) gives the addresses and the bit fields.

| Block | Registers | Role |
|---------------|---------------------------------------------------------|--------------------------------|
| PHY | `phy_card_detect`, `phy_clocker_divider`, `phy_settings` | Card presence, card clock, bus width |
| PHY | `phy_init_initialize` | Power-up clocks (and card reset) |
| PHY | `phy_cmdr_timeout`, `phy_dataw_timeout`, `phy_datar_timeout` | Timeouts in system clock cycles |
| PHY | `phy_dataw_status` | CRC status tokens of a write |
| Core | `core_cmd_argument`, `core_cmd_command`, `core_cmd_send` | Command to send |
| Core | `core_cmd_response`, `core_cmd_event`, `core_data_event` | Response and outcome |
| Core | `core_block_length`, `core_block_count` | Data phase size |
| DMAs | `block2mem_dma_*`, `mem2block_dma_*` | Base, length, enable, done |
| Events | `ev_status`, `ev_pending`, `ev_enable` | Interrupts built by `add_sdcard` |

The PHY registers are written at initialization and when the bus width or the clock changes. The
core and DMA registers are written for every command. The event registers exist only with
`add_sdcard`, which builds them from the done bits, the card detect change and the DMA ends
([Adding LiteSDCard to a SoC](#integration)).

## A read, end to end {#arch-transaction}

The figure below follows a single block read (CMD17) through the blocks, as the BIOS driver runs
it. The exact register writes are in [A command from software](#core-sequence); this section
names the block that acts at each step.

![A single block read with CMD17. Read the arrows from top to bottom: the block2mem setup, the
register writes, the command frame, the R1 response and its done event, then the data block and
its CRC bytes, which the core drops, before the data done event.](arch_transaction.svg)

1. Software programs block2mem with the destination address and the length, then enables it.
2. Software writes the block length and count, the argument and the command fields, then
   `cmd_send`. The core leaves IDLE and clears both event registers.
3. The core builds the six bytes of the frame and computes the CRC7 on the fly. The command
   writer shifts them out on CMD, most significant bit first, one bit per card clock.
4. The command reader waits for the start bit of the response and returns six bytes. Because
   CMD17 reads data, the core asks the data reader for a block at the same time: some cards start
   the data before the response ends.
5. At the last response byte, the core sets `cmd_event.done` and enters DATA-READ.
6. The data reader receives the block on the DAT lines, checks the CRC16 of each line and
   forwards 512 data bytes followed by the CRC bytes marked `drop`. The core drops them and passes
   the data to block2mem, which writes the memory.
7. After the last block, the core returns to IDLE and sets `data_event.done`. Software then waits
   for the done bit of block2mem before it reads the buffer.

A write follows the same steps with mem2block and the data writer. The data writer adds the CRC16
and the end bit, reads the CRC status token and waits while the card is busy, so
`data_event.done` comes only after the card has stored the block, or with `data_event.timeout`
when the card does not answer within the write timeout.

## In the code {#arch-code}

| Block | File | Classes |
|---------------|---------------------------------------------|-----------------------------------------|
| PHY | `litesdcard/phy.py` | `SDPHY` and its sub-blocks |
| Core | `litesdcard/core.py` | `SDCore` |
| CRC | `litesdcard/crc.py` | `CRC`, `CRC16` |
| Constants | `litesdcard/common.py` | Status codes, transfer and response types |
| DMAs | `litesdcard/frontend/dma.py` | `SDBlock2MemDMA`, `SDMem2BlockDMA` |
| Integration | LiteX `soc.py` | `add_sdcard` |

Where to go next: [PHY: clocking and IO](#phy) for the card clock and the pins, [Core: commands,
responses, CRC](#core) for the command path, [DMAs](#dma) for the memory side.
