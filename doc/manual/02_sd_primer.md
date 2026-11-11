# SD cards in a nutshell {#sd-primer}

This chapter explains the SD bus to an FPGA engineer who has never read the SD specification. It
starts from the pins, builds up the commands and the responses, follows a card through its
initialization, then gives the format of the data blocks. It ends with the bus widths, the speed
modes and what changes on an eMMC device.

Each section starts with the idea, gives the mechanism, and ends with the part of LiteSDCard or of
the BIOS driver that implements it. The chapter covers what the code uses; the rest of the
specification is named only to say what is not implemented.

The references are the SD Physical Layer Simplified Specification of the SD Association (cited as
"section 4.7") and, for eMMC, the JEDEC standard JESD84. The repository notes in `MEMO` refer to
version 6.00 of the SD specification.

## Cards and form factors {#primer-cards}

An SD card is a flash memory with a small controller inside. The controller hides the flash: the
host sees a flat array of 512-byte blocks and talks to the controller with commands. Wear
levelling, bad blocks and erase cycles are the card's business.

The same protocol comes in several packages:

- SD cards (full size), with a write-protect switch that only the slot can read;
- microSD cards, the most common on FPGA boards, with eight pins and no switch;
- eMMC devices, the same kind of memory and controller in a BGA package soldered on the board.

An eMMC speaks a close relative of the SD protocol, inherited from the MultiMediaCard. It has up
to eight data lines and is always present, so it has no card detect.
[eMMC differences](#primer-emmc) lists what changes for the host.

In LiteSDCard, nothing depends on the form factor. A slot only adds an optional card detect pin,
which the PHY exposes as a register and an interrupt ([PHY: clocking and IO](#phy)).

## The bus {#primer-bus}

The SD bus is a synchronous bus with one master, the host. The figure below shows its lines. The
host drives the clock; the command line and the data lines are bidirectional, driven by the host
or by the card in turn.

![The SD bus. The host drives CLK; CMD carries commands to the card and responses back; DAT0 to
DAT3 (DAT0 to DAT7 on an eMMC) carry data blocks in both directions. Pull-up resistors hold CMD and
the DAT lines high when nobody drives them.](primer_bus.svg)

| Line | Direction | Role |
|-----------|------------------|------------------------------------------------------------|
| CLK | Host to card | Card clock; every bit on CMD and DAT is sampled on its rising edge |
| CMD | Both | Commands from the host, responses from the card, one bit per clock |
| DAT0 | Both | Data; also the busy signal of the card and the CRC status token on writes |
| DAT1-DAT3 | Both | Data in 4-bit mode; DAT3 is also the SPI chip select, sampled at CMD0 |
| DAT4-DAT7 | Both | Data in 8-bit mode, eMMC only |

Both sides sample on the rising edge. At default speed the host and the card change their outputs
on the falling edge, half a period before the next sample. At high speed the card changes its
outputs after the rising edge, within an output delay bounded by the specification, and the host
samples them on the following rising edge.

The lines idle high. A pull-up resistor on CMD and on each DAT line keeps them high while neither
side drives them, between a command and its response for example; a floating line could look like
a start bit. A card also has an internal pull-up on DAT3, which the host can use to detect it.

The specification lets the host stop the clock between bits (section 4.4). The card simply
waits, which lets a host pause a transfer when its buffer is full or empty.

In LiteSDCard, the PHY drives the clock and the tristate buffers of CMD and DAT, with one output
enable for all the DAT lines. It runs the card clock only during a transfer, and stops it when a
FIFO cannot follow ([PHY: clocking and IO](#phy)).

The pull-ups are resistors on the board or the internal pull-ups of the FPGA IO, which the
platform file can enable (`PmodSDCard` does).

## SD mode and SPI mode {#primer-modes}

A card speaks two protocols on the same pins. *SD mode* is the native one, with a command line,
1 to 4 data lines and CRCs on everything. *SPI mode* turns the card into an SPI slave: one data
line in each direction, a chip select, optional CRCs and a single data bit per clock.

| Pin | SD mode | SPI mode | `PmodSDCard` pin |
|------|-----------------------|--------------------------------|------------------|
| CLK | Card clock | SCLK | `pmod:3` |
| CMD | Command and response | MOSI (data in to the card) | `pmod:1` |
| DAT0 | Data bit 0 | MISO (data out of the card) | `pmod:2` |
| DAT3 | Data bit 3 | CS_N (chip select, active low) | `pmod:0` |
| DAT1, DAT2 | Data bits 1 and 2 | Unused | `pmod:4`, `pmod:5` |
| CD | Card detect (slot switch) | Unused | `pmod:6` |

The card chooses the mode when it receives CMD0: if the host holds DAT3, the chip select, low at
that moment, the card enters SPI mode until the next power cycle. Otherwise it stays in SD mode.

SPI mode needs only a plain SPI master and four pins, but it is slower: one bit per clock instead
of four, and every transfer goes through a byte stream that the CPU usually handles. SD mode needs
a dedicated controller and carries four or eight bits per clock.

In LiteX, the two modes are two separate controllers on the same slot. `add_sdcard` adds
LiteSDCard, in SD mode; `add_spi_sdcard` adds the LiteX SPI master and its BIOS driver in SPI
mode. The last column of the table shows how the Digilent Pmod MicroSD extension of LiteX-Boards
declares both resources on the same pins.

## Power-up {#primer-power}

A card powers up at 3.3 V and starts in the *idle* state. Before the first command, the host must
send at least 74 clock cycles with CMD high, so that the card controller can finish its own
power-up. The host then sends CMD0 to reset the card into idle, whatever it was doing.

During the identification, the card clock must stay at 400 kHz or below (the identification
clock of the specification). The host raises the clock once the card has an address.

In LiteSDCard, writing the `initialize` register of the init block sends 80 clock cycles with CMD
and DAT high. When the platform declares a card reset pin, the init block first asserts it for
the time of 4096 card clock periods, with the clock stopped. The BIOS driver sets the card clock
to `SDCARD_CLK_FREQ_INIT`, 400 kHz by default, before it; the clock divider goes up to 511, so
the init clock stays at 400 kHz or below up to a system clock of 204.8 MHz.

## Commands {#primer-commands}

Every exchange starts with a command from the host on CMD. A command is a 48-bit frame, shown in
the figure below: a start bit, a direction bit, a 6-bit command index, a 32-bit argument, a CRC7
over the first 40 bits and an end bit. The bits leave most significant first.

![A command frame. Start bit 0, transmission bit 1 (from the host), index, 32-bit argument (here
the data address of CMD17: a block number, or a byte address on SDSC cards), CRC7 of the first 40
bits and end bit 1.](primer_command.svg)

The CRC7 uses the polynomial x^7 + x^3 + 1. The card ignores a command whose CRC is wrong and
does not answer it, so a bad CRC shows up on the host as a missing response; the card reports it
with the COM_CRC_ERROR bit of the next response (section 4.6 of the specification).

Some commands exist only as *application commands*: the host first sends CMD55 with the card
address, and the next command is interpreted in the application set. ACMD41 is CMD55 followed by
command index 41. The table below lists the commands that the BIOS driver sends.

| Command | Name | Response | Use |
|-------------|----------------------------|----------|---------------------------------------|
| CMD0 | GO_IDLE_STATE | None | Reset the card into idle |
| CMD2 | ALL_SEND_CID | R2 | Read the identification register (CID) |
| CMD3 | SEND_RELATIVE_ADDR | R6 | Ask the card for its address (RCA) |
| CMD6 | SWITCH_FUNC | R1 | Select high speed; 64-byte status block on DAT |
| CMD7 | SELECT_CARD | R1b | Select the card for data transfers |
| CMD8 | SEND_IF_COND | R7 | Check the voltage, detect a version 2.00 card |
| CMD9 | SEND_CSD | R2 | Read the capacity and timing register (CSD) |
| CMD10 | SEND_CID | R2 | Read the CID of the selected card |
| CMD12 | STOP_TRANSMISSION | R1b | End a multiple-block transfer |
| CMD16 | SET_BLOCKLEN | R1 | Set the block length (512 bytes) |
| CMD17, CMD18 | READ_SINGLE_BLOCK, READ_MULTIPLE_BLOCK | R1 | Read one or several blocks |
| CMD23 | SET_BLOCK_COUNT | R1 | Announce the number of blocks of the next transfer |
| CMD24, CMD25 | WRITE_BLOCK, WRITE_MULTIPLE_BLOCK | R1 | Write one or several blocks |
| CMD55 | APP_CMD | R1 | Prefix of an application command |
| ACMD6 | SET_BUS_WIDTH | R1 | Switch to the 4-bit bus |
| ACMD41 | SD_SEND_OP_COND | R3 | Start the card and read its OCR |
| ACMD51 | SEND_SCR | R1 | Read the configuration register (SCR), 8 bytes on DAT |

eMMC devices add CMD1 and give CMD6 and CMD8 another meaning ([eMMC differences](#primer-emmc)).

In LiteSDCard, the CPU writes the argument in `cmd_argument`, then the index and the expected
response type in `cmd_command`, and starts the command with `cmd_send`. The core adds the start,
direction, CRC7 and end bits, and the command writer of the PHY shifts the six bytes onto CMD
([Core: commands, responses, CRC](#core)).

## Responses {#primer-responses}

Most commands get a response from the card on CMD, a few clock cycles after the end of the
command. A response starts with a 0 start bit and a 0 direction bit (from the card). The
specification names the response formats R1 to R7; the figure below shows the three layouts.

![Response layouts. R1 carries the command index and the 32-bit card status with a CRC7. R3
carries the OCR with all ones in place of the index and the CRC. R2 is 136 bits long and carries
the 128-bit CID or CSD, whose last byte holds its own CRC7.](primer_responses.svg)

| Response | Length | Content | CRC7 checked |
|----------|----------|-------------------------------------------------------------|--------------|
| R1 | 48 bits | Index and card status | Yes |
| R1b | 48 bits | R1, then the card holds DAT0 low while it is busy | Yes |
| R2 | 136 bits | CID or CSD (127 bits and an end bit) | Yes, inside the register |
| R3 | 48 bits | OCR; index and CRC fields are all ones | No |
| R6 | 48 bits | New RCA and part of the card status | Yes |
| R7 | 48 bits | Echo of the voltage and of the check pattern of CMD8 | Yes |

R3 carries no CRC: the specification fills the index and CRC fields with ones, so the host must
not check it. For R1b, the end of the response is not the
end of the command: the card keeps DAT0 low until it has finished, for example after CMD7 or
CMD12.

In LiteSDCard, the response type of `cmd_command` tells the PHY how many bytes to read: 6 for a
short response, 17 for a long one, then waits for DAT0 to go high after R1b. The `crc` field of
`cmd_command` enables the CRC7 check of the response; a mismatch sets the `crc` and `error` flags
of `cmd_event`. The BIOS driver leaves it off for R3. The response lands in the 128-bit
`cmd_response` register.

## Card registers {#primer-registers}

A card describes itself with a few registers, read with dedicated commands. The host reads them
once, during the initialization, and keeps what it needs.

| Register | Size | Read with | Content used by the host |
|----------|----------|-------------------|------------------------------------------------------|
| OCR | 32 bits | ACMD41 (R3) | Voltage window, power-up done (bit 31), CCS (bit 30) |
| CID | 128 bits | CMD2, CMD10 (R2) | Manufacturer, product name, serial number, date |
| CSD | 128 bits | CMD9 (R2) | Capacity, maximum transfer rate, block length, access times |
| RCA | 16 bits | CMD3 (R6) | Address of the card on the bus |
| SCR | 64 bits | ACMD51 (data) | Supported bus widths, CMD23 support, specification version |
| Card status | 32 bits | Every R1 | Errors of the last command, current state, ready for data |

The CSD has two layouts. Version 1.0 (SDSC cards) encodes the capacity in three fields; version
2.0 (SDHC and SDXC) uses one 22-bit C_SIZE field, and the capacity is (C_SIZE + 1) x 512 KiB.
ACMD51 answers with R1 on CMD, and the card sends the 8-byte SCR as a data block on the DAT
lines.

The card status of R1 reports what went wrong with the previous command and where the card is.
The table below lists the bits a host looks at first (section 4.10 of the specification).

| Bits | Field | Meaning |
|-------|--------------------|-----------------------------------------------------------|
| 31 | OUT_OF_RANGE | The address argument is beyond the capacity |
| 30 | ADDRESS_ERROR | The address is misaligned for the block length |
| 23 | COM_CRC_ERROR | The CRC of the previous command was wrong |
| 22 | ILLEGAL_COMMAND | The command is not legal in the current state |
| 12:9 | CURRENT_STATE | State of the card: 0 idle to 8, see [Card states](#primer-states) |
| 8 | READY_FOR_DATA | The card can accept a new data block |
| 5 | APP_CMD | The card expects an application command next |

In LiteSDCard, the core does not decode any card register: it hands the raw response to software.
The BIOS driver reads the RCA from the response of CMD3, the CCS bit from the OCR and the bus
widths and CMD23 support from the SCR; with `SDCARD_DEBUG` it also decodes the CID and a version
2.0 CSD.

## Capacity and addressing {#primer-capacity}

SD cards come in capacity classes, and the class changes how a block is addressed. The OCR tells
which one the card is with its CCS bit (card capacity status), valid once the power-up is done.

| Class | Capacity | CSD version | CCS | Address in CMD17, CMD18, CMD24, CMD25 |
|-------|-------------------|-------------|-----|---------------------------------------|
| SDSC | Up to 2 GB | 1.0 | 0 | Byte address (block number x 512) |
| SDHC | 2 GB to 32 GB | 2.0 | 1 | Block number |
| SDXC | 32 GB to 2 TB | 2.0 | 1 | Block number |

A host announces that it supports block addressing with the HCS bit of ACMD41. A host that does
not set HCS cannot use an SDHC or SDXC card: the card stays busy.

In LiteSDCard, addressing is a software matter. The BIOS driver sets HCS, reads CCS from the OCR
and multiplies the block number by 512 when CCS is 0. The core puts the argument on the bus as the
CPU wrote it.

## Initialization {#primer-init}

The initialization takes the card from power-up to a state where it accepts block transfers. The
figure below shows the sequence that the BIOS driver runs for an SD card, with the card state
after each step (sections 4.2 and 4.3 of the specification).

![Initialization of an SD card by the BIOS driver. The host sends the commands on the left lane;
the card answers on the right lane, and its state is written on the right. ACMD41 repeats until
the card reports that its power-up is done.](primer_init.svg)

1. **Clocks and reset.** At least 74 clock cycles, then CMD0, which takes the card to idle.
2. **Voltage check.** CMD8 with argument `0x1aa`: `0x1` asks for 2.7 V to 3.6 V and `0xaa` is a
   check pattern. A version 2.00 card echoes both in R7; an older card does not answer.
3. **Power-up.** CMD55 then ACMD41 with the voltage window and HCS, repeated until bit 31 of the
   OCR is set. The OCR then holds CCS. The card is *ready*.
4. **Identification.** CMD2 reads the CID (*ident*); CMD3 makes the card publish its RCA in R6
   (*stby*). From now on, commands to this card carry the RCA in bits 31:16 of their argument.
5. **Card registers.** CMD10 and CMD9 read the CID and the CSD of the addressed card.
6. **Selection.** CMD7 with the RCA selects the card, which enters *tran*, the state where it
   accepts data commands. The response is R1b.
7. **Configuration.** CMD6 selects high speed; ACMD51 reads the SCR; ACMD6 switches to the 4-bit
   bus if the SCR allows it; CMD16 sets 512-byte blocks.

In LiteSDCard, the whole sequence is software: `sdcard_init()` of the BIOS driver
(`litex/soc/software/liblitesdcard/sdcard.c`) runs it with the registers of the core.

The BIOS driver keeps the init clock until the card has its address, then raises the card clock
to `SDCARD_CLK_FREQ`, 25 MHz by default, once CMD3 is answered.

The driver sends ACMD41 with argument `0x70ff8000`: the voltage window `0x00ff8000` (2.7 V to
3.6 V), HCS (bit 30) and the XPC bit (bit 28); it also sets bit 29, which the SD specification
reserves. A card that does not answer CMD8 but answers CMD1 is handled as an eMMC. The driver has
no path for SD cards older than version 2.00 (no answer to CMD8): they are not supported.

## Card states {#primer-states}

A card is a state machine, and every command is legal only in some states. The states fall in two
groups, shown in the figure below: the identification mode, until the card has an address, and
the data transfer mode, once it has one.

![Card states. Identification mode on the top row, data transfer mode on the bottom row. A
selected card waits in tran; a read takes it to data, a write to rcv then prg while it programs
the flash. Each arrow is labelled with the command that causes it.](primer_states.svg)

| State | Value | Meaning |
|-------|-------|------------------------------------------------------|
| idle | 0 | After power-up or CMD0 |
| ready | 1 | Power-up done (ACMD41 not busy), waiting for CMD2 |
| ident | 2 | CID sent, waiting for CMD3 |
| stby | 3 | Has an RCA, not selected |
| tran | 4 | Selected, waiting for a data command |
| data | 5 | Sending data to the host |
| rcv | 6 | Receiving data from the host |
| prg | 7 | Programming the flash after a write |
| dis | 8 | Deselected while programming |

A card in stby that receives CMD7 with another RCA stays in stby: CMD7 selects one card and
deselects the others. LiteSDCard drives one card per PHY, so the host selects it once and
leaves it in tran.

In LiteSDCard, the card state is visible only through bits 12:9 of an R1 response; neither the
core nor the BIOS driver tracks it. The BIOS driver defines CMD13 (SEND_STATUS) to read the
status but does not call it.

## Data blocks {#primer-blocks}

Data travels on the DAT lines in blocks. Each line carries its own frame, as the figure below
shows for the 4-bit bus: a start bit 0, its share of the data, a 16-bit CRC of what it carried,
and an end bit 1. All lines start and end on the same clock.

![A 512-byte block on the 4-bit bus. Each byte takes two clocks: DAT3 to DAT0 carry bits 7 to 4,
then bits 3 to 0. Each line ends with its own CRC16 and an end bit.](primer_block.svg)

| Bus width | Clocks per byte | Data clocks per 512-byte block | Clocks per block on the bus |
|-----------|-----------------|--------------------------------|-----------------------------|
| 1 bit | 8 | 4096 | 4114 |
| 4 bits | 2 | 1024 | 1042 |
| 8 bits | 1 | 512 | 530 |

The last column adds the start bit, the 16 CRC bits and the end bit to the data clocks. The CRC16
uses the polynomial x^16 + x^12 + x^5 + 1 and is computed separately for each line, so a 4-bit
block carries four CRCs. The same per-line framing applies on the 8-bit bus of an eMMC.

For a read, the card sends the block after an *access time*: the time its controller needs to
fetch the data from the flash. The specification bounds it in the CSD and in its timing
section, but a host only knows that a start bit will come, or that it gives up after a timeout.

In LiteSDCard, the data reader of the PHY waits for the start bit with a timeout, checks one CRC16
per line and marks the CRC bytes to be dropped by the core. The data writer inserts the CRC16 of
each line. Both take the bus width from the `settings` register of the PHY
([PHY: command and data engines](#phy-engines)).

## Writes {#primer-writes}

A write adds two steps after the block, shown in the figure below. The card first checks the CRCs
and answers on DAT0 with a *CRC status token*. It then holds DAT0 low while it programs the flash:
the *busy*. The host waits for DAT0 to go high before it sends the next block.

![A single-block write. CMD24 and its R1 response on CMD; the host sends the block on DAT; two
clocks later the card sends the CRC status token on DAT0, then holds DAT0 low while
busy.](primer_write.svg)

| Token on DAT0 | Status code | Meaning |
|---------------|-------------|-------------------------------------------|
| 0 `010` 1 | `0b010` | Data accepted |
| 0 `101` 1 | `0b101` | CRC error, data rejected |
| 0 `110` 1 | `0b110` | Write error, data rejected |

The busy lasts as long as the flash needs, often much longer than the block itself. The host
has no way to shorten it; it can only wait, or give up after a timeout of its own.

In LiteSDCard, the data writer reads the token after the end bit, reports it in its `status`
register and to the core, then waits in a busy state, with the card clock running, until DAT0 is
high. The wait for the token and the busy share a write timeout, the `dataw_timeout` register,
500 ms by default; when it expires, the core reports a data timeout ([PHY: command and data
engines](#phy-engines)).

The codes of the second column are the `SDCARD_STREAM_STATUS_*` constants of
`litesdcard/common.py`.

## Multiple blocks {#primer-multiblock}

A file is many blocks long, and one command per block wastes time. CMD18 and CMD25 transfer
consecutive blocks with a single command, and the host ends the transfer in one of two ways, shown
in the figure below.

![Two ways to end a multiple-block read. Top: CMD18 alone, the card sends blocks until the host
sends CMD12. Bottom: CMD23 announces the count first, and the card stops by itself after the last
block.](primer_multiblock.svg)

- **Open-ended**: the card sends or accepts blocks until the host sends CMD12. CMD12 is an R1b
  command: after a write, the card stays busy until it has programmed the last block.
- **Pre-defined**: CMD23 gives the number of blocks before CMD18 or CMD25, and the card stops
  after that count. A card that supports CMD23 says so in its SCR; every eMMC supports it.

In LiteSDCard, the `block_count` register of the core tells the engines how many blocks to expect,
whichever way the card is told. The BIOS driver sends a whole request as one multiple-block
command, preceded by CMD23 when the SCR allows it and followed by CMD12 otherwise.

## Bus width and speed modes {#primer-speed}

A card starts in 1-bit mode at default speed. The host widens the bus and raises the clock only
after reading what the card supports. The throughput on the bus is the bus width times the card
clock: 4 bits at 25 MHz move 12.5 MB/s, before the start, CRC and end bits and the access times.

| Mode | Card clock | Signalling | How to enter | In LiteSDCard |
|---------------|---------------|--------------|-----------------------------------|--------------|
| Default speed | Up to 25 MHz | 3.3 V | After the initialization | Yes |
| High speed | Up to 50 MHz | 3.3 V | CMD6, function group 1, function 1 | Yes |
| UHS-I | Up to 208 MHz | 1.8 V | ACMD41 request, CMD11, tuning with CMD19 | No |

The bus width is switched by ACMD6 with argument 2 (4 bits) on an SD card, once the SCR says the
card supports it. The host must change its own width at the same time.

High speed is a function of the *switch function* command, CMD6. The card answers with a 64-byte
status block on DAT, which tells whether the function is now selected.

UHS-I needs much more: a switch of the signalling to 1.8 V with CMD11, a regulator on the board,
and the tuning of the sampling point with CMD19 for the fastest modes. The repository notes in `MEMO` list these steps.

In LiteSDCard, the bus width is the `data_width` field of the PHY `settings` register: `0b00` for
1 bit, `0b01` for 4 bits and `0b10` for 8 bits. The card clock is the system clock divided by an
even number set in the clocker `divider` register.

The BIOS driver selects high speed with CMD6 and checks the status block, but keeps the card
clock at `SDCARD_CLK_FREQ`, 25 MHz by default.

## eMMC differences {#primer-emmc}

An eMMC uses the same bus, frames, CRCs and data blocks. The initialization differs, because it
comes from the MultiMediaCard side of the family. The table below lists what changes for the host.

| Topic | SD card | eMMC |
|-------------------|-----------------------------------------|---------------------------------------------------|
| Power-up | CMD8, then CMD55 and ACMD41 | CMD1 (SEND_OP_COND), no CMD8 in idle |
| Addressing | CCS bit of the OCR | Access mode bits 30:29 of the OCR (sector or byte) |
| RCA | Chosen by the card, read from R6 | Chosen by the host, sent with CMD3 |
| Configuration | Card registers SCR and switch function | 512-byte EXT_CSD, written with CMD6 (SWITCH) |
| Bus width | ACMD6, up to 4 bits | EXT_CSD BUS_WIDTH (index 183), up to 8 bits |
| Speed | CMD6 switch function | EXT_CSD HS_TIMING (index 185); high speed up to 52 MHz, HS200/HS400 not implemented |
| Multiple blocks | CMD23 if the SCR says so | CMD23 always |
| CMD8 | SEND_IF_COND | SEND_EXT_CSD, legal only once selected |

An eMMC is soldered and always powered with the board. Some boards wire its reset pin to the FPGA,
and some run its IO at 1.8 V; the FPGA bank must then use the same voltage.

In LiteSDCard, the PHY supports the 8-bit bus when the platform resource has eight data pins, and
then exports `SDCARD_PHY_SUPPORT_8X`.

The BIOS driver recognizes an eMMC when CMD8 gets no answer and CMD1 does. It then assigns RCA 1,
raises the card clock to `SDCARD_CLK_FREQ` once selected, switches BUS_WIDTH to 8 bits if the PHY
supports them (else 4 bits), and sets HS_TIMING; when the device accepts it, the card clock goes to
`SDCARD_MMC_CLK_FREQ`, 50 MHz by default.

## Where to go next {#primer-next}

[Architecture overview](#architecture) shows how LiteSDCard maps these mechanisms onto its blocks;
[Software: BIOS, boot and Linux](#software) follows the initialization in the BIOS driver; the
[Glossary](#glossary) lists the acronyms.
