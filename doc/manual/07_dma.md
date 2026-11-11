# DMAs {#dma}

This chapter describes the two DMA frontends that connect the core to memory: block2mem writes
the blocks read from the card into memory, mem2block reads memory and feeds the blocks to write.
Read it to program a transfer, to choose the bus they sit on, or to replace them with a datapath
of your own.

## At a glance {#dma-glance}

| Item | block2mem | mem2block |
|------------------|-------------------------------------------|-------------------------------------------|
| Class | `SDBlock2MemDMA` | `SDMem2BlockDMA` |
| Direction | Card to memory (`SDCore.source`) | Memory to card (`SDCore.sink`) |
| Bus master | `WishboneDMAWriter` (LiteX) | `WishboneDMAReader` (LiteX) |
| FIFO | 512 bytes (`fifo_depth`) | 512 bytes (`fifo_depth`) |
| Width converter | 8 bits to bus width | Bus width to 8 bits |
| Start | First byte of a block while enabled | As soon as enabled |
| Interrupt | `irq`, pulse when done rises | `irq`, pulse when done rises |
| Created by | `add_sdcard`, mode `read` or `read+write` | `add_sdcard`, mode `write` or `read+write` |

## Overview {#dma-overview}

Each DMA is a short chain: a FIFO, a width converter and a LiteX Wishbone DMA engine, as the
figure below shows. The core works on 8-bit streams; the converters adapt them to the data width
of the bus, 32 bits on most SoCs. The DMA engines come from LiteX (`litex/soc/cores/dma.py`) and
bring their own registers.

![DMA frontends. Look at the two chains: block2mem carries the read blocks from the core to
memory, mem2block carries the data to write from memory to the core.](dma_paths.svg)

`add_sdcard` builds one Wishbone master per DMA, with the data width of the SoC bus and word
addressing. It connects them to the DMA bus of the SoC when the CPU has one (`soc.dma_bus`), and
to the main bus otherwise ([Adding LiteSDCard to a SoC](#integration)).

## Block2mem {#dma-block2mem}

Block2mem receives the bytes that the core forwards from the card. When its DMA is enabled, it
waits for the first byte of a block (`first`), then passes every byte to the FIFO until the DMA is
disabled. A disabled block2mem accepts and drops the bytes, so a read never stalls without a DMA.

The FIFO holds 512 bytes, one block, which absorbs the latency of the bus. The converter packs
the bytes into bus words, and the DMA writer stores each word at the next address. The DMA counts
in bus words and sets `done` after `length` bytes.

`length` must equal `block_length` times `block_count`. A longer length never completes: `done`
stays low, and the BIOS gives up after its DMA timeout. With a shorter length, the DMA writer
stops accepting words once done; the FIFO fills, the core stops, and the PHY stops the card clock
until the DMA is disabled. Disabling the DMA resets the FIFO and the converter: the bytes left in
them, a partial bus word included, are dropped.

## Mem2block {#dma-mem2block}

Mem2block starts reading memory as soon as its DMA is enabled, before the write command is sent.
The words go through the converter into the 512-byte FIFO, which fills and waits. The core takes
the bytes only in its DATA-WRITE state and marks the block boundaries itself
([Write data path](#core-write)).

Here too `length` must equal `block_length` times `block_count`. A shorter length leaves the core
waiting for data in DATA-WRITE, with the card clock stopped. With a longer length, the extra bytes
stay in the FIFO when the write ends. Disabling the DMA resets the FIFOs (of the DMA reader and of
mem2block) and the converter, so they do not lead the next write.

## Registers {#dma-registers}

Each DMA engine brings seven registers. With `add_sdcard`, their names start with
`sdcard_block2mem_dma_` and `sdcard_mem2block_dma_`.

| Register | Bits | Access | Content |
|------------|------|--------|------------------------------------------------------------------|
| `base` | 64 | rw | Byte address of the buffer, aligned to a bus word |
| `length` | 32 | rw | Bytes to transfer, a multiple of the bus word size |
| `enable` | 1 | rw | 1 starts the transfer, 0 stops it and resets the engine |
| `done` | 1 | ro | Transfer complete, or rejected (with `error`) |
| `loop` | 1 | rw | 1 restarts at `base` after `length` bytes instead of completing |
| `offset` | 32 | ro | Bus words transferred since the start |
| `error` | 1 | ro | `base` or `length` not aligned to a bus word |

A transfer runs while `enable` is 1, so software writes 0 first, then `base` and `length`, then
1. A misaligned `base` or `length` completes at once with `done` and `error` set. A `length` of 0
completes at once without bus activity. `base` takes two 32-bit words on a 32-bit CSR bus.

## Byte order {#dma-endianness}

The converters take the first byte of the stream as the most significant byte of the word
(`reverse=True`). The DMA engines then swap the bytes of each word on a little-endian CPU and
leave them on a big-endian one; `add_sdcard` passes the CPU endianness to both DMAs.

In both cases the first byte of a block lands at the lowest address: a buffer holds the bytes in
the order of the card.

## Caches {#dma-caches}

On a SoC without a DMA bus, the DMAs reach memory behind the caches of the CPU. After a read,
the BIOS flushes the CPU data cache and the L2 cache before it uses the buffer, unless the CPU
has a DMA bus (`CONFIG_CPU_HAS_DMA_BUS`).

A driver for a CPU with a write-back data cache must also write the buffer back to memory
before a mem2block transfer.

## Interrupts {#dma-irq}

Each DMA produces `irq`, a one-cycle pulse on the rising edge of its `done` register.
`add_sdcard` turns them into two pulse events of its event manager, `block2mem_dma` and
`mem2block_dma`, next to the pulse event `card_detect` and the level events `cmd_done` and
`data_done`. The event manager gets an
interrupt line when the SoC has an interrupt controller; the BIOS polls instead
([Adding LiteSDCard to a SoC](#integration)).

## Programming the DMAs {#dma-sequence}

The BIOS reads blocks in this order (`sdcard_read` in LiteX `liblitesdcard/sdcard.c`):

1. Write 0 to `block2mem_dma_enable`, the buffer address to `base`, `512` times the number of
   blocks to `length`, then 1 to `enable`.
2. Send the read command (CMD17 for one block, CMD18 for several, with CMD23 before or CMD12
   after) and wait for `cmd_event.done` and `data_event.done` ([A command from
   software](#core-sequence)).
3. If the command fails after the retries of the BIOS (`SDCARD_CMD_RETRIES`, 16), write 0
   to `enable` and stop: no data will arrive.
4. Poll `block2mem_dma_done` with a timeout (`SDCARD_DMA_TIMEOUT_US`, 1 s by default).
5. Without a DMA bus, flush the caches before reading the buffer.

Writes follow the same order with mem2block and CMD24 or CMD25. Because mem2block fetches data as
soon as it is enabled, the buffer must be in memory before step 1.

## Without the DMAs {#dma-custom}

The DMAs are optional. A design can connect its own stream to `SDCore.source` and `SDCore.sink`,
8 bits wide with the usual LiteX `valid`/`ready` handshake, and keep the core registers for
control. `add_sdcard` builds only the DMA of each enabled direction, from its `mode` argument.

The repository also has a BIST frontend (`litesdcard/frontend/bist.py`): a block generator and a
block checker with counter or LFSR data. It works on 32-bit streams, while the core streams are
8 bits wide, and no LiteX integration, bench or LiteX-Boards target instantiates it.

## In the code {#dma-code}

| Function | File | Classes |
|--------------|------------------------------------------------|-------------------------------------|
| DMA frontends | `litesdcard/frontend/dma.py` | `SDBlock2MemDMA`, `SDMem2BlockDMA` |
| DMA engines | LiteX `litex/soc/cores/dma.py` | `WishboneDMAWriter`, `WishboneDMAReader` |
| Integration | LiteX `litex/soc/integration/soc.py` | `add_sdcard` |
| BIST frontend | `litesdcard/frontend/bist.py` | `BISTBlockGenerator`, `BISTBlockChecker` |

Where to go next: [Core: commands, responses, CRC](#core) for the streams the DMAs connect to,
[Adding LiteSDCard to a SoC](#integration) for the bus and interrupt wiring,
[Software](#software) for the BIOS read and write functions.
