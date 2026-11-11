# Performance and resources {#performance}

This appendix gives the throughput limits of the card bus for each bus width and card clock, the
card clocks that the divider can make from a system clock, the public records of real transfers, and
the memories the core declares.

The bounds and the clock tables are computed from the code and labelled so; the records are quoted
from their public sources. The manual gives no measured logic utilization or timing, since both
depend on the device, the toolchain and the design.

## Bus bounds {#perf-bounds}

A block of 512 bytes travels on the DAT lines as a start bit, the data, 16 CRC16 bits and an end
bit, on every line at once ([Data blocks](#primer-blocks)).

A 4-bit bus moves a byte in 2 card clocks, so a read block takes 1 + 1024 + 16 + 1 = 1042 card
clocks. The bound of a read is 512 bytes per block time; the card adds its access time before each
block.

For a write, the PHY also spends 2 clocks before the start bit, then receives the CRC status
token, which it reads as a start bit and 8 bits ([PHY: command and data
engines](#phy-engines)): 11 more clocks per block. The card then holds DAT0 low while it
programs the block, for a time that only the card sets.

| Bus width | Card clocks per read block | Read at 25 MHz (computed) | Read at 50 MHz (computed) | Write at 25 MHz, no busy (computed) | Write at 50 MHz, no busy (computed) |
|-------|--------|----------|----------|----------|----------|
| 1-bit | 4114 | 3.11 MB/s | 6.22 MB/s | 3.10 MB/s | 6.21 MB/s |
| 4-bit | 1042 | 12.28 MB/s | 24.57 MB/s | 12.16 MB/s | 24.31 MB/s |
| 8-bit | 530 | 24.15 MB/s | 48.30 MB/s | 23.66 MB/s | 47.32 MB/s |

The bounds leave out the command and its response, sent once per multi-block request by the BIOS
driver, the access time of the card before each read block, and its busy time after each written
block. They are upper limits: a real transfer is slower.

## Card clock and divider {#perf-divider}

The clocker divides the system clock by the divider rounded up to the next even value, and by 2 at
least, so the card clock is at most half the system clock ([PHY: clocking and IO](#phy)).

The BIOS driver computes the divider as `ceil(f_sys / f)` for a target clock `f`, and keeps it
between 2 and 511, the range of the 9-bit register. The table gives the clock it obtains for its
three default targets.

| System clock | 400 kHz target (computed) | 25 MHz target (computed) | 50 MHz target (computed) |
|------------------|------------------------|------------------------|------------------------|
| 1 MHz (simulation) | 250 kHz | 500 kHz | 500 kHz |
| 50 MHz | 396.8 kHz | 25 MHz | 25 MHz |
| 75 MHz | 398.9 kHz | 18.75 MHz | 37.5 MHz |
| 100 MHz | 400 kHz | 25 MHz | 50 MHz |
| 125 MHz | 398.1 kHz | 20.83 MHz | 31.25 MHz |
| 150 MHz | 398.9 kHz | 25 MHz | 37.5 MHz |
| 200 MHz | 400 kHz | 25 MHz | 50 MHz |

The identification clock stays at 400 kHz or below up to a system clock of 204.8 MHz; above it,
the cap of 511 lifts it above 400 kHz (computed).

The rounding of the divider up to an even value can lose a large part of the target, 37.5 % of 50
MHz at a 125 MHz system clock: a system clock that is an even multiple of the card clock loses nothing.

## Recorded results {#perf-records}

The public records of LiteSDCard transfers are few. The table quotes them; the configuration
column gives what the source states, and nothing more.

| Source | Configuration | Recorded |
|----------------------------|----------------------------------------|------------------------------------------|
| LiteX commit `c07703124` | BIOS driver, multi-block read | ">10MB/s read speed with a 25MHz clock." |
| LiteSDCard commit `19c854f` | Arty A7-100, Microwatt CPU, 100 MHz system clock, an earlier version of the receive sampling | "operate at 50MHz SD card clock" |
| LiteX commit `df3428be0` | Rocket CPU, Nexys4 DDR, 75 MHz system clock; block2mem (card reads) | "unable to route DMA writes from LiteSDCard at frequencies above 25MHz" |
| Enjoy-Digital blog, TriXium part 2 | Efinix Ti375 C529 Dev Kit, microSD 1-bit, eMMC 8-bit high speed | Quoted below |

The 50 MHz record predates the present sampling logic of `SDPHYIO` ([PHY: clocking and
IO](#phy)). The DMA writes of the `df3428be0` record are the writes of block2mem into memory,
that is card reads.

The last record comes from the Enjoy-Digital blog post "TriXium, part 2"
(<https://enjoy-digital.github.io/posts/trixium-ti375/>), which loads a 436 MB model from the
card of the kit:

```text
The microSD slot worked first, but only in 1-bit mode on our kit (one data line never goes low,
somewhere between the FPGA ball and the card): 436 MB in 74 s. The eMMC then took over: LiteX's
SD card library learned eMMC (CMD1 init, 8-bit bus, high speed, [...]). The 2B model and
its tokenizer now load in **9.6 s**, 46 MB/s, close to the eMMC's cap at 8 bits and high speed.
```

The records agree with the bounds. More than 10 MB/s at 25 MHz is under the 12.28 MB/s of a 4-bit
read. 46 MB/s on the eMMC is under the 48.30 MB/s of an 8-bit read at 50 MHz, the clock of
`SDCARD_MMC_CLK_FREQ`.

The 1-bit microSD load, 436 MB in 74 s or about 5.9 MB/s (computed), is above the 1-bit bound
at 25 MHz (3.11 MB/s). The source does not give the card clock. As an inference only, the rate
implies a card clock of about 47 MHz or more, so the loader of that run did not use the 25 MHz
default of the BIOS driver.

## What limits a real card {#perf-limits}

The card, not the core, sets most of the gap to the bounds:

- Before each read block, the card needs an access time that depends on the card and its
  state. The BIOS driver sends one CMD18 for a whole request, which saves a command and its
  response per block, not the access time.
- After each written block, the card holds DAT0 low while it programs the flash; write rates
  are therefore lower than read rates and vary much more between cards.
- The BIOS driver switches an SD card to high speed with CMD6, then keeps `SDCARD_CLK_FREQ` at
  25 MHz. A design can define `SDCARD_CLK_FREQ` as `50000000` to use the high-speed clock, if
  the board holds it ([CRC errors and wrong data at speed](#debug-crc)).
- Clocks above 50 MHz need the UHS-I modes, 1.8 V signalling and tuning, which LiteSDCard does
  not implement ([What it is not](#intro-limits)).

The bus side does not limit a transfer at usual system clocks. A 32-bit DMA carries 4 bytes per bus
word, so 48.30 MB/s needs about 12.1 million words per second, one word every 8 cycles of a 100 MHz
system clock (computed).

When the DMA does fall behind, the PHY stops the card clock until the FIFO has room, so no data is
lost and the transfer is only slower; the read timeout does not count while the card clock is
stopped ([PHY: command and data engines](#phy-engines)).

## Memories {#perf-resources}

The core declares four memories, all LiteX stream FIFOs. Each entry carries the payload plus two
framing bits (`first` and `last`). The generator of the register appendix
(`litesdcard_gen --vendor lattice`, in an empty directory) declares them in
`build/gateware/litesdcard_core.v`:

```verilog
reg [13:0] storage[0:63];    // core read FIFO: 64 x (8 data + 3 status + drop + 2)
reg [9:0] storage_1[0:511];  // block2mem FIFO: 512 x (8 + 2)
reg [33:0] storage_2[0:15];  // mem2block, LiteX DMA reader FIFO: 16 x (32 + 2)
reg [9:0] storage_3[0:511];  // mem2block FIFO: 512 x (8 + 2)
```

The comments are added here. The two 512-entry FIFOs, 5 120 bits each (computed), hold one block
each and are the ones that map to block RAM; the read FIFO of the core holds 896 bits (computed)
and usually maps to distributed RAM.

A design with `mode="read"` or `mode="write"` keeps only the FIFOs of its DMA. The emulator, in
simulation or in an FPGA, adds its 512-byte buffer ([The SD card emulator](#emulator)).
