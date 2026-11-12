# Core: commands, responses, CRC {#core}

This chapter describes the core (`SDCore`): the registers that software writes to run a command,
the frame it builds, the response it captures, its CRC generators and the state machine that
sequences a command and its data. Read it to write a driver, to connect a custom datapath, or to
interpret the event registers.

The protocol itself is explained in [SD cards in a nutshell](#sd-primer); the validation status
of each configuration is in the [status table](#intro-status).

## At a glance {#core-glance}

| Item | Value |
|-----------------------|--------------------------------------------------------------------------|
| Class | `SDCore(phy)` in `litesdcard/core.py` |
| Clock domain | `sys`, the same as the PHY |
| Data interfaces | 8-bit `sink` (write data) and 8-bit `source` (read data) streams |
| Command frame | 48 bits built by the core: start, direction, index, argument, CRC7, end |
| Responses | 48 bits (6 bytes) or 136 bits (17 bytes), CRC7 checked on request |
| Read buffer | `SyncFIFO` of 64 bytes between the PHY and `source` |
| Block size | `block_length` up to 1023 bytes, on read and write |
| Events | `cmd_event` and `data_event`: done, error, timeout, crc |
| Interrupt | `irq`, a pulse when a command completes (not used by `add_sdcard`) |

## Registers {#core-registers}

Software drives the core through eight registers. It writes the argument, the command word and,
for a data command, the block length and count; then it writes `cmd_send` and polls the two event
registers. With `add_sdcard`, the registers are named `sdcard_core_` followed by the names below.

| Register | Bits | Access | Content |
|----------------------|------|--------|-------------------------------------------------------|
| `cmd_argument` | 32 | rw | Argument of the command, sent MSB first |
| `cmd_command` | 32 | rw | Command index, response type, data type, CRC check enable |
| `cmd_send` | 1 | rw | Any write starts the command |
| `cmd_response` | 128 | ro | Last response, see [Receiving the response](#core-response) |
| `cmd_event` | 4 | ro | Command done, error, timeout, crc |
| `data_event` | 4 | ro | Data done, error, timeout, crc |
| `block_length` | 10 | rw | Bytes per block |
| `block_count` | 32 | rw | Blocks of the data phase; 0 skips the data phase |

The figure below shows the fields of `cmd_command` and of the two event registers. The command
index goes in bits 13:8, so a driver writes the index shifted left by 8, ORed with the other
fields.

![Fields of `cmd_command`, `cmd_event` and `data_event`. Read each register from bit 0: `done` is
the bit to poll, the others tell why a command or its data phase failed
([Events and error reporting](#core-events)).](core_cmd_reg.svg)

The two type fields take the values of `litesdcard/common.py`, named
`SDCARD_CTRL_RESPONSE_*` for `cmd_type` and `SDCARD_CTRL_DATA_TRANSFER_*` for `data_type`. The
BIOS repeats them in `sdcard.h`.

| Field | Value | Name suffix | Meaning |
|---------------|-------|----------------|-----------------------------------------------|
| `cmd_type` | 0 | `NONE` | No response (CMD0) |
| `cmd_type` | 1 | `SHORT` | 48-bit response (R1, R3, R6, R7) |
| `cmd_type` | 2 | `LONG` | 136-bit response (R2) |
| `cmd_type` | 3 | `SHORT_BUSY` | 48-bit response, then busy on DAT0 (R1b) |
| `data_type` | 0 | `NONE` | No data phase |
| `data_type` | 1 | `READ` | Blocks from the card |
| `data_type` | 2 | `WRITE` | Blocks to the card |

The `crc` field (bit 2, `SDCARD_CTRL_RESPONSE_CRC` in the BIOS) enables the CRC7 check of the
response. It must stay clear for R3, the response to ACMD41 and CMD1, whose CRC field is all
ones ([SD cards in a nutshell](#sd-primer)).

The core reads `cmd_argument`, `cmd_command`, `block_length` and `block_count` while the command
runs, not only when `cmd_send` is written. Software must leave them unchanged until the done bits
are set again.

## Sending a command {#core-command}

On a write of `cmd_send`, the core builds the 48-bit command frame and hands it to the PHY, one
byte at a time.

The first byte holds the start bit (0), the direction bit (1, host to card) and the 6-bit
index. The next four bytes are the argument, MSB first; the last byte is the CRC7
of the first five, followed by the end bit (1).

The CRC7 generator (`crc7_inserter`) absorbs a whole byte in the cycle the PHY accepts it, so
the CRC is ready when the sixth byte is due. Software never computes a CRC. The PHY serializes
the bytes on the CMD line, MSB first, at the card clock
([PHY: command and data engines](#phy-engines)).

## Receiving the response {#core-response}

When `cmd_type` is not 0, the core asks the PHY for a response of 6 bytes, or 17 bytes for a long
response. The PHY waits for the start bit on the CMD line and returns the bytes. If no start bit
comes within the PHY command timeout (`cmdr_timeout`), it returns a timeout status instead, which
sets `cmd_event.timeout` and `cmd_event.error`.

The core shifts each byte into `cmd_response` from the bottom, so the last bytes received end in
the low bits. It keeps all 17 bytes of a long response, which leaves the last 16 in the 128-bit
register. For a short response it keeps the first five bytes and drops the CRC byte. The table
below gives the resulting layout.

| Response | `cmd_response` bits | Content |
|-----------------|---------------------|----------------------------------------------------|
| Short (R1, R1b) | 31:0 | Card status |
| Short (R3) | 31:0 | OCR |
| Short (R6) | 31:16, 15:0 | New RCA, status bits |
| Short (R7) | 11:0 | Voltage accepted and check pattern echo |
| Short (all) | 37:32 | Command index echoed by the card (63 for R3) |
| Long (R2) | 127:1 | CID or CSD, with its internal CRC7 in bits 7:1 |

The register is not cleared between commands: after a short response, bits 127:40 hold
bytes of earlier responses. Read with the LiteX helper `csr_rd_buf_uint32`, element 0 of the
buffer holds bits 31:0, which is why the BIOS reads the OCR and the RCA from `r[0]`.

With the `crc` field set, the core runs the received bytes through the same CRC7 generator and
compares the result with bits 7:1 of the last byte. A short response is checked over its first
five bytes. A long response is checked over bytes 1 to 15, skipping the first byte as the
specification defines the CRC of R2. A mismatch sets `cmd_event.crc` and `cmd_event.error`.

For a command without data, the PHY holds back the last response byte until it has given the card
8 more clocks, and for R1b until the card releases DAT0. `cmd_event.done` therefore means that
the CMD line is idle and the card is no longer busy. The busy wait counts against the same
`cmdr_timeout`.

## CRC generators {#core-crc}

Both CRCs come from one parallel LFSR class, `CRC(polynom, taps, dw)`, which advances `dw` bits
per cycle when `enable` is set and returns to its initial value (0) on `reset`. The core uses it
once for CRC7; the PHY uses one bit-serial copy per DAT line for CRC16 (`CRC16`), as the figure
below shows.

![CRC generators. Look at the two widths: CRC7 takes a whole byte per cycle in the core, while
each DAT line has its own CRC16 fed one bit per card clock and read back MSB
first.](core_crc.svg)

| CRC | Polynomial | Generator | Where |
|--------|---------------------------|---------------------------------------|----------------------|
| CRC7 | x^7 + x^3 + 1 (`0x09`) | `CRC(0x9, 7, dw=8)` | `SDCore`, command, response |
| CRC16 | x^16 + x^12 + x^5 + 1 (`0x1021`) | `CRC(0x1021, 16, dw=1)` | PHY, one per DAT line |

On a write, the data engine computes the CRC16 of each line while it sends the block, then
shifts the 16 bits out on every line at once, bit 15 first.

On a read, the engine freezes the CRC16 after the data and compares it bit by bit with the CRC
that arrives on each line. A mismatch on any line marks the block as a CRC error.

The unit tests check the CRC16 against known values (`test/test_crc.py`): 512 bytes of `0xff`
give `0x7fa1` on 1, 4 and 8 lines, and the tuning block of `common.py`, split on 4 lines (high
nibble first), gives `0xc59f`, `0xa2e5`, `0x8d06` and `0xe946` on DAT3 to DAT0.

## Main state machine {#core-fsm}

A state machine of five states sequences a command and its data phase. The figure below shows
it. IDLE waits for `cmd_send`, CMD-SEND sends the frame, CMD-RESPONSE collects the response, and
the two data states move the blocks.

![Main state machine of the core. Follow a read: IDLE, CMD-SEND, CMD-RESPONSE, DATA-READ, back
to IDLE after the last block. The dotted path returns to IDLE without a data
phase.](core_fsm.svg)

| State | Leaves when | Goes to |
|----------------|-----------------------------------------------------|------------------------------|
| IDLE | `cmd_send` is written | CMD-SEND |
| CMD-SEND | Sixth byte accepted by the PHY | CMD-RESPONSE, or IDLE |
| CMD-RESPONSE | Last response byte, timeout, or CRC7 mismatch | DATA-WRITE, DATA-READ, or IDLE (no data, a failure, or `block_count` 0) |
| DATA-WRITE | Last byte of the last block accepted by the PHY | IDLE |
| DATA-READ | Last block delivered, or a timeout | IDLE |

IDLE holds `cmd_event.done` and `data_event.done` at 1 and keeps the read FIFO in reset. Leaving
IDLE clears both done bits and every error flag. `cmd_event.done` rises again at the last
response byte, `data_event.done` when the state machine is back in IDLE.

The core accepts `cmd_send` only in IDLE and has no abort: a write of `cmd_send` during a command
is ignored. A write whose data source runs dry keeps the core busy until the SoC is reset (see
[Limitations](#core-limitations)).

## Read data path {#core-read}

The PHY delivers each block as bytes with extra fields: `first` and `last` delimit the block,
`drop` marks the CRC bytes, and `status` carries OK, CRC error or timeout. A 64-byte FIFO
(`data_read_fifo`) takes them. The core forwards the data bytes to `source`, discards the CRC
bytes and counts blocks on `last`.

The core requests the blocks from the PHY in CMD-RESPONSE already, not in DATA-READ. Some cards
start the data on DAT before the response on CMD has ended, and the PHY must be listening then
(`test/test_core.py` covers this case). The FIFO holds the early bytes until the state machine
reaches DATA-READ. When the command fails instead (response timeout or CRC7 mismatch), the core
pulses the `abort` input of the data reader, which returns to IDLE and releases the card clock, so
the next command starts with a data reader that is not armed.

Reads have back-pressure all the way to the card. When `source` is not ready, the FIFO fills, the
PHY stops the card clock, and the card waits ([PHY: clocking and IO](#phy)). A slow consumer
slows the transfer but loses no data; the read timeout does not count while the card clock is
stopped ([Timeouts](#eng-timeouts)).

Bytes received with a CRC error are forwarded to `source`: the error only sets
`data_event.crc`. A timeout from the PHY sets `data_event.timeout` and ends the data phase at
once.

## Write data path {#core-write}

In DATA-WRITE, the core connects `sink` to the PHY write engine. It marks the end of each block
itself, without relying on the data source: a byte counter asserts `last` on byte
`block_length - 1`. The PHY then appends the CRC16 and the end bit, reads the CRC status token
and waits for the card to release DAT0.

The PHY returns one status per block from the CRC status token. A CRC error token (`101`) sets
`data_event.crc`; any other token than "data accepted" (`010`), including a write error token
(`110`) or an unknown token, sets `data_event.error`. The core does not stop on a bad token: it
sends every block of `block_count`.

The state machine leaves DATA-WRITE when the PHY takes the last byte of the last block. The PHY
takes that byte only once the card has released DAT0, so `data_event.done` means that the card
has finished programming the data. When the card sends no token, or stays busy, beyond the write
timeout of the PHY, the PHY returns the status `TIMEOUT`: the core sets `data_event.timeout` and
returns to IDLE without sending the remaining blocks ([Data writer](#eng-dataw)).

The byte counter that delimits the blocks is as wide as `block_length` (10 bits), so write blocks
can be up to 1023 bytes long.

## Events and error reporting {#core-events}

Software learns the outcome of a command from the two event registers. It polls bit 0 of
`cmd_event`, then, for a data command, bit 0 of `data_event`, and reads the other bits once done
is set. The table below gives what sets each bit in the code.

| Bit | `cmd_event` | `data_event` |
|-------------|-----------------------------------------|-------------------------------------------|
| 0 `done` | Last response byte, or end of the frame without response | Return to IDLE |
| 1 `error` | Response timeout or CRC7 mismatch | Data phase skipped after a failed command; write: token other than "data accepted" or CRC error |
| 2 `timeout` | No response, or busy beyond the timeout | Read: no block, or block beyond the timeout; write: no token or busy beyond the write timeout |
| 3 `crc` | CRC7 mismatch, with the `crc` field set | Read: CRC16 mismatch; write: CRC error token |

A response timeout reads as `0x7` in `cmd_event` (done, error and timeout), a CRC7 mismatch as
`0xb` (done, error and crc). After either on a data command, the state machine skips the data
phase and `data_event` reads `0x3`, done with the error bit, so a driver that only polls
`data_event` also sees the failure.

A `block_count` of 0 with a data type skips the data phase too: the core returns to IDLE after the
response, and `data_event` reads `0x1`.

### Limitations {#core-limitations}

A driver must know the following limits:

- The write timeout covers the card. If the data source runs dry, the data writer stops the card
  clock and waits for the next byte without a timeout, and the core stays in DATA-WRITE.
- `phy_dataw_status` sums up the tokens of every block of a write; the per-block result is only in
  `data_event` ([CRC status token](#eng-dataw-token)).

The BIOS checks the timeout and crc bits of `cmd_event`, and the timeout, crc and error bits of
`data_event`; its retries and DMA timeouts are described in [Software](#software).

## Interrupt {#core-irq}

The core produces `irq`, a one-cycle pulse on the rising edge of `cmd_event.done`. `add_sdcard`
does not use it; it builds its own event manager from the done bits and the DMA interrupts
([Interrupts](#dma-irq) and [Adding LiteSDCard to a SoC](#integration)).

## A command from software {#core-sequence}

The sequence below reads one block with CMD17, as the BIOS does it. The accessor names are those
LiteX generates for `add_sdcard` with the default name. The DMA is set up first, as
[Programming the DMAs](#dma-sequence) describes.

```c
/* One 512-byte block with CMD17: short response, CRC check, read data. */
sdcard_core_block_length_write(512);
sdcard_core_block_count_write(1);
sdcard_core_cmd_argument_write(block_address);
sdcard_core_cmd_command_write((17 << 8) |
    (SDCARD_CTRL_DATA_TRANSFER_READ << 5) |
    SDCARD_CTRL_RESPONSE_CRC |
    SDCARD_CTRL_RESPONSE_SHORT);
sdcard_core_cmd_send_write(1);
/* Command done, then data done. */
while ((sdcard_core_cmd_event_read() & 0x1) == 0);
while ((sdcard_core_data_event_read() & 0x1) == 0);
```

After each wait, the driver reads the timeout and crc bits of the register it polled. A custom
datapath that consumes `source` or feeds `sink` directly, without the DMAs, follows the same
sequence ([Adding LiteSDCard to a SoC](#integration)).

## In the code {#core-code}

| Function | File | Classes, signals |
|----------------------|----------------------------------|--------------------------------------|
| Registers, state machine | `litesdcard/core.py` | `SDCore`, `fsm`, `data_read_fifo` |
| CRC7, CRC16 | `litesdcard/crc.py` | `CRC`, `CRC16` |
| Field values, status codes | `litesdcard/common.py` | `SDCARD_CTRL_*`, `SDCARD_STREAM_STATUS_*` |
| Tests | `test/test_core.py`, `test/test_crc.py` | Early read start, events, write delimiter and timeout, zero block count, CRC16 values |

Where to go next: [DMAs](#dma) for the memory side of `source` and `sink`,
[PHY: command and data engines](#phy-engines) for the bit level, [Software](#software) for the
BIOS driver built on these registers.
