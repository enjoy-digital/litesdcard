# PHY: command and data engines {#phy-engines}

This chapter describes the blocks of the PHY that decide what happens on each card clock cycle:
the init block and the four engines. It covers their state machines, the bit order on the DAT
lines, busy and timeouts. Read it to understand a waveform or a timeout; the clock and the pins
are in [PHY: clocking and IO](#phy).

## At a glance {#eng-glance}

| Block | Class | From the core | To the core | Register |
|----------------|--------------------|---------------------|---------------------|--------------------|
| Init block | `SDPHYInit` | None | None | `initialize` |
| Command writer | `SDPHYCMDW` | Command bytes | None | None |
| Command reader | `SDPHYCMDR` | Response length, type | Response bytes, status | `timeout` |
| Data writer | `SDPHYDATAW` | Data bytes, last block | One status per block | `status`, `timeout` |
| Data reader | `SDPHYDATAR` | One request per block | Data and CRC bytes | `timeout` |

The init block and the command engines use CMD, the data engines the DAT lines. The command
reader also watches DAT0 for busy. The command reader and the data writer drive CMD high during
their CLK8 and CLK2 gaps.

The PHY adds one register of its own, `settings`, which selects the bus width for both data
engines ([Bus width](#eng-widths)).

## How an engine works {#eng-common}

Every engine is a state machine in the system clock domain. It steps on the `ce` pulse of the
clocker, which it receives as `pads_out.ready`. In each state it drives the internal pads: a clock
request, CMD and its enable, the DAT lines and their enable. An idle engine drives nothing.

The engines read CMD and DAT when `data_i_ce` is high, which they receive as `pads_in.valid`.
That cycle carries the value sampled at the rising edge of the card clock ([Timing at the
pins](#phy-timing)).

The receiving engines share one helper, `SDPHYR`, that turns bits into bytes. It waits until all
the lines it watches are low, which is the start bit, then packs the samples into bytes, first
bit in the most significant position. It either keeps the start bit as the first bit of the first
byte or skips it.

| User | Lines | Start bit |
|-------------------------------|--------------------|--------------|
| Command reader | CMD | Kept |
| Data writer, CRC status token | DAT0 | Skipped |
| Data reader | DAT0, DAT0-3, DAT0-7 | Skipped |

The core runs one command at a time, so at most two engines are active together: the command
reader and the data reader during the response of a read command. Both request the clock then,
and neither drives a line.

## Init block {#eng-init}

A card needs at least 74 clock cycles with CMD high before its first command
([Power-up](#primer-power)). The init block sends them when software writes the `initialize`
register; the core is not involved. The BIOS driver writes it before each CMD0 of its
initialization loop.

When the pads have a `rst` pin, the init block first runs a reset phase. It drives `rst`, CMD
and the DAT lines high, without a card clock, for 4096 periods of `ce`: about 10 ms with a
400 kHz card clock. It then sends 80 card clocks with CMD and the DAT lines high.

## Command writer {#eng-cmdw}

The command writer receives the six bytes of a command frame from the core and shifts them out on
CMD, most significant bit first, one bit per card clock. It drives CMD and requests the clock only
while it has a byte, and takes the next byte after the eighth bit.

For a command without a response, it adds 8 card clocks with CMD high after the frame (state
CLK8) before it accepts the last byte. The SD specification requires at least 8 clocks between
two commands, and the core only moves on once they are sent.

The command writer tells the command reader when it is idle (`done`). The reader starts to listen
only then, so it never mistakes the end of the frame for a response.

## Command reader {#eng-cmdr}

The command reader receives the response on CMD and, after an R1b response, waits for the end of
the busy signal on DAT0. The core gives it the response length (6 bytes, or 17 for R2), the
response type and the data type of the command. The figure below shows its state machine.

![Command reader state machine. Follow the three ways back to IDLE: directly after the last byte
when data follows, after 8 clocks otherwise, and through BUSY for R1b. WAIT, CMD and BUSY all
lead to TIMEOUT.](eng_cmdr_fsm.svg)

| State | Card clock | What happens |
|-----------|------------|--------------------------------------------------------------------------|
| IDLE | Off | Loads the timeout counter; leaves when the command writer is done |
| WAIT | On | Waits for the start bit on CMD |
| CMD | On | Forwards the response bytes; the start bit is bit 7 of the first byte |
| CLK8 | On | Drives CMD high for 8 clocks, holding the last byte back |
| BUSY | On | Waits for DAT0 high, then sends the last byte |
| TIMEOUT | Off | Sends one byte with status `TIMEOUT` and `last` |

The exit from CMD depends on the command. For an R1b response or a command without data, the
reader holds the last byte, sends the 8 clocks of CLK8, waits in BUSY for R1b, then delivers it.
For a command with data and a plain response, it delivers the last byte at once: the data reader
is already listening on the DAT lines.

The core sets `cmd_event.done` when the last byte arrives. For R1b this happens after the card
has released DAT0, so software sees the command done only when the card is ready again.

## Data writer {#eng-dataw}

The data writer sends the blocks of a write command and collects the answer of the card to each
of them. The figure below shows one block; the entry and the exit stand for its IDLE state.

![Data writer state machine. Follow one block along the top row (CLK2, START, DATA, CRC16), then
the card's answer along the bottom row (STOP, CRC status token, BUSY). CLK8 runs after the last
block only.](eng_dataw_fsm.svg)

| State | Clocks | Lines driven | What happens |
|---------|--------------|---------------|-------------------------------------------------------|
| CLK2 | 2 | CMD high | Gap after the response or the previous block |
| START | 1 | DAT low | Start bit on every DAT line; resets the CRC16 |
| DATA | Per width | DAT | Data bits; asserts `stop` while no byte is available |
| CRC16 | 16 | DAT | The CRC16 of each line on that line |
| STOP | 1 | DAT high | End bit; resets the token receiver |
| CRC | Start bit + 8 | None | Receives the CRC status token on DAT0 |
| CLK8 | 8 | CMD high | After the last block only |
| BUSY | Until DAT0 high | None | Waits for the card to finish programming |
| TIMEOUT | None | None | Reports a timeout and releases the block |

DATA takes 8 card clocks per byte on a 1-bit bus, 2 on a 4-bit bus and 1 on an 8-bit bus. The
CRC16 is computed on the bits as they leave, one CRC per DAT line, so the data writer needs no
buffer. [CRC generators](#core-crc) describes the CRC16 itself.

### CRC status token {#eng-dataw-token}

After the end bit, the card answers on DAT0 with a start bit, a three-bit CRC status token and an
end bit, then holds DAT0 low while it programs the block ([Writes](#primer-writes)). The data
writer reads 8 bits after the start bit and decodes the first three:

| Token | Meaning | Stream status | `status` field |
|--------|-----------------------|----------------|----------------|
| `010` | Data accepted | `DATAACCEPTED` | `accepted` |
| `101` | CRC error in the block | `CRCERROR` | `crc_error` |
| `110` | Write error | `WRITEERROR` | `write_error` |
| Other | Not decoded | `OK` | None |

The status goes to the core as one stream transfer per block and sets the error bits of
`data_event` ([Write data path](#core-write)). The token also sets a bit of the `status` register
of the data writer.

The three bits of `status` are cleared when a write transfer starts and never cleared between
blocks. After a multi-block write, they tell which tokens the whole transfer received.

### Busy and block hand-off {#eng-dataw-busy}

The data writer accepts the last byte of a block only when the card releases DAT0 at the end of
BUSY. The core counts blocks on that hand-off, so each block ends, and `data_event.done` rises,
only after the card has programmed the data. The card clock runs during BUSY.

CRC and BUSY share one write timeout per block. The data writer loads its `timeout` register at
the end bit of the block and counts it down, one per system clock cycle, while it waits for the
token and while the card is busy; it holds it during CLK8. When the count reaches 0, the data writer
enters TIMEOUT: it sends one status `TIMEOUT` to the core, accepts the byte it was holding back
and returns to IDLE. The core then ends the write with `data_event.timeout`
([Write data path](#core-write)). A card that never sends a token, or never releases DAT0, no
longer keeps the core in its write state.

The BIOS driver waits for `data_event.done` after each write command without a bound of its own
(`sdcard_wait_data_done`); the write timeout of the PHY is what ends that wait when the card does
not answer ([Software: BIOS, boot and Linux](#software)).

## Data reader {#eng-datar}

The data reader receives one block per request from the core. The core requests the first block
during the command response, so the data reader listens on the DAT lines from the start. The
figure below shows its state machine.

![Data reader state machine. Each block goes from IDLE through WAIT to DATA and back; CLK8 follows
the last block. WAIT and DATA lead to TIMEOUT when the counter expires.](eng_datar_fsm.svg)

| State | Card clock | What happens |
|-----------|------------|------------------------------------------------------------------------|
| IDLE | Off (on in the cycle that accepts a request) | Loads the timeout counter and resets the receivers for a new block |
| WAIT | On | Waits for the start bit on the DAT lines in use |
| DATA | On | Forwards the data bytes, then the CRC bytes marked `drop` |
| CLK8 | On | 8 more clocks after the last block |
| TIMEOUT | Off | Sends one byte with status `TIMEOUT` and `last` |

In DATA, each byte carries `first` on the first byte of the block and `last` on the last CRC
byte. The CRC of a block is 16 bits per line: 2 bytes on a 1-bit bus, 8 on a 4-bit bus and 16 on
an 8-bit bus. The data reader forwards them with `drop` set, and the core discards them.

The data reader checks the CRC16 while the bits arrive. It computes one CRC per line over the
data bits, then compares each of the next 16 bits on each line with the expected bit. A mismatch
sets an error flag for the block. The CRC bytes, sent after the check, carry the status
`CRCERROR`, and the core sets `data_event.crc` from them; the data bytes, forwarded earlier, carry
`OK`.

When the consumer is not ready, the data reader asserts `stop` and the card clock pauses
([Back-pressure](#arch-backpressure)). No bit is lost, because the card only moves on a clock
edge, and the read timeout does not count while the clock is stopped.

The data reader counts the bytes of a block, data and CRC, on 10 bits. A block whose length plus
its CRC bytes exceeds 1024 never reaches its last byte and ends on the read timeout: the longest
block that can be read is 1022 bytes on a 1-bit bus, 1016 bytes on a 4-bit bus and 1008 bytes on
an 8-bit bus. Cards use 512-byte blocks, so this only matters for other block lengths.

## Bus width {#eng-widths}

The `settings` register selects the bus width of both data engines with its `data_width` field.
The command engines always use CMD alone.

| `data_width` | Bus width | Available when |
|--------------|-----------|------------------------------|
| `0b00` | 1 bit | Always |
| `0b01` | 4 bits | 4 or 8 data pins; reset value |
| `0b10` | 8 bits | 8 data pins |

The register resets to 4 bits for compatibility with drivers written before the field existed.
The BIOS driver writes 1 bit before it initializes the card, then 4 or 8 bits once the card has
accepted the wider bus ([Software: BIOS, boot and Linux](#software)).

A value that the pins cannot support selects 1 bit, without any error. The engines contain only
the widths that the pads allow, and the 1-bit path is their default case. A PHY with 4 data pins
therefore runs on DAT0 alone if software writes `0b10` or `0b11`, and a PHY with 1 data pin runs on
DAT0 at the reset value `0b01`.

The figure below shows how one byte maps onto the lines. The most significant bit goes first in
time and, on a wide bus, on the highest line.

![Bit order of one byte on the DAT lines. On a 1-bit bus, bit 7 leaves first on DAT0; on a 4-bit
bus, bits 7 to 4 leave on DAT3 to DAT0 in the first clock; on an 8-bit bus, bit n is on DATn.](eng_widths.svg)

## Busy handling {#eng-busy}

A card signals busy by holding DAT0 low ([Writes](#primer-writes)). Two engines wait for it, with
different guards:

| After | Engine | State | Timeout |
|-----------------------------|----------------|-------|------------------------------------------|
| An R1b response | Command reader | BUSY | The command timeout, shared with the response |
| Each written block | Data writer | BUSY | The write timeout, shared with the CRC status token |

Both keep the card clock running while they wait and leave on the first sample of DAT0 high.

## Timeouts {#eng-timeouts}

The command reader and the two data engines count down a timeout in system clock cycles. Each has
a 32-bit register, reset to the value given to `SDPHY` multiplied by the system clock frequency.
The BIOS driver never writes them; a driver may change them at any time between commands.

| Timeout | Register | Default | `add_sdcard` | Counts in |
|-----------------|--------------------------------|---------|-------------------|----------------|
| Command response | `phy_cmdr_timeout` | 10 ms | 1 s | WAIT, CMD, BUSY |
| Data read | `phy_datar_timeout` | 10 ms | 1 s | WAIT, DATA |
| Data write | `phy_dataw_timeout` | 500 ms | 500 ms (not passed) | CRC, BUSY |

The command reader reloads its counter once per command, the data engines once per block.

`phy_dataw_timeout` sits between `phy_dataw_status` and `phy_datar_timeout` in the register bank,
so it moved `phy_datar_timeout` and `phy_settings` by one register. A Linux driver that writes the
bus width at a fixed offset of the PHY registers no longer reaches `phy_settings`
([Known issues](#debug-known)).

The command timeout covers the whole response in one budget: the wait for the start bit, the
response bytes and the busy time of an R1b response. A long busy, such as an erase, needs a larger
value. It does not count during the 8 clocks of CLK8.

The read timeout covers one block: the access time of the card, then the transfer of the block
and its CRC. It does not count while back-pressure stops the card clock, so a slow consumer
slows the read without ending it.

The write timeout covers the answer of the card to one block: the CRC status token and the busy
time while the card programs the block.

A slow card clock makes the block itself long. A 1-bit block takes 4114 card clocks (start bit,
4096 data bits, 16 CRC bits, end bit), which is about 10.3 ms at 400 kHz, longer than the 10 ms
class default. The BIOS driver switches to its operating clock before it reads any block.

A timeout reaches the core as a stream status and sets the timeout bit of `cmd_event` or
`data_event` ([Events and error reporting](#core-events)). The engine returns to IDLE. The data
reader is the exception after a failed read command: it was started during the response and
finishes its block, or its own timeout, on its own.

## In the code {#eng-code}

| Function | File | Classes |
|-------------------|------------------------------|--------------------------------------|
| Init and commands | `litesdcard/phy.py` | `SDPHYInit`, `SDPHYCMDW`, `SDPHYCMDR` |
| Data engines | `litesdcard/phy.py` | `SDPHYDATAW`, `SDPHYDATAR` |
| Bits to bytes | `litesdcard/phy.py` | `SDPHYR` |
| CRC16 per line | `litesdcard/crc.py` | `CRC16` |
| Constants | `litesdcard/common.py` | `SD_PHY_SPEED_*`, status codes |
| Tests | `test/test_phy.py` | Helper, init, command engines, data engine timeouts |

The unit tests cover the bit-to-byte helper, the init block and the two command engines. For the
data engines, `test_phydataw_busy_timeout` checks the write timeout on a card stuck in busy and
`test_phydatar_backpressure_no_timeout` checks that back-pressure does not end a read;
`test_phydataw` runs a write with a short busy. `test_phydatar` and `test_phycrc` are empty.

Where to go next: [Core: commands, responses, CRC](#core) for what the core does with the bytes
and statuses, [Debugging](#debugging) for timeouts and CRC errors on hardware.
