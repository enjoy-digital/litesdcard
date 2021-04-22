#
# This file is part of LiteSDCard.
#
# Copyright (c) 2020 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *

from litex.soc.interconnect.csr import *
from litex.soc.interconnect import stream

from litex.soc.cores.dma import WishboneDMAReader, WishboneDMAWriter

# SD Block2Mem DMA ---------------------------------------------------------------------------------

class SDBlock2MemDMA(Module, AutoCSR):
    """Block to Memory DMA

    Receive a stream of blocks and write it to memory through DMA.
    """
    def __init__(self, bus, endianness, fifo_depth=512):
        self.bus  = bus
        self.sink = stream.Endpoint([("data", 8)])
        self.irq  = Signal()

        # # #

        # Submodules
        fifo      = stream.SyncFIFO([("data", 8)], fifo_depth, buffered=True)
        converter = stream.Converter(8, bus.data_width, reverse=True)
        self.submodules += fifo, converter
        self.submodules.dma = WishboneDMAWriter(bus, with_csr=True, endianness=endianness)

        # Flow
        start   = Signal()
        connect = Signal()
        self.comb += start.eq(self.sink.valid & self.sink.first)
        self.sync += [
            If(~self.dma._enable.storage,
                connect.eq(0)
            ).Elif(start,
                connect.eq(1)
            )
        ]
        self.comb += [
            If(self.dma._enable.storage & (start | connect),
                self.sink.connect(fifo.sink)
            ).Else(
                self.sink.ready.eq(1)
            ),
            fifo.source.connect(converter.sink),
            converter.source.connect(self.dma.sink),
        ]

        # IRQ / Generate IRQ on DMA done rising edge
        done_d = Signal()
        self.sync += done_d.eq(self.dma._done.status)
        self.sync += self.irq.eq(self.dma._done.status & ~done_d)

# SD Mem2Block DMA ---------------------------------------------------------------------------------

class SDMem2BlockDMA(Module, AutoCSR):
    """Memory to Block DMA

    Read data from memory through DMA and generate a stream of blocks.
    """
    def __init__(self, bus, endianness, fifo_depth=512):
        self.bus    = bus
        self.source = stream.Endpoint([("data", 8)])
        self.irq    = Signal()

        # # #

        # Submodules
        self.submodules.dma = WishboneDMAReader(bus, with_csr=True, endianness=endianness)
        converter = stream.Converter(bus.data_width, 8, reverse=True)
        fifo      = stream.SyncFIFO([("data", 8)], fifo_depth, buffered=True)
        self.submodules += converter, fifo

        # Flow
        self.comb += [
            self.dma.source.connect(converter.sink),
            converter.source.connect(fifo.sink),
            fifo.source.connect(self.source),
        ]

        # Block delimiter
        count = Signal(9)
        self.sync += [
            If(self.source.valid & self.source.ready,
                count.eq(count + 1),
                If(self.source.last, count.eq(0))
            )
        ]
        self.comb += If(count == (512 - 1), self.source.last.eq(1))

        # IRQ / Generate IRQ on DMA done rising edge
        done_d = Signal()
        self.sync += done_d.eq(self.dma._done.status)
        self.sync += self.irq.eq(self.dma._done.status & ~done_d)
