# This file is Copyright (c) 2020 Florent Kermarrec <florent@enjoy-digital.fr>
# License: BSD

from migen import *

from litex.soc.interconnect.csr import *
from litex.soc.interconnect import stream

from litex.soc.cores.dma import WishboneDMAReader, WishboneDMAWriter

# SD Block2Mem DMA ---------------------------------------------------------------------------------

class SDBlock2MemDMA(Module, AutoCSR):
    """Block to Memory DMA

    Receive a stream of blocks and write it to memory through DMA.
    """
    def __init__(self, bus, endianness):
        self.sink = stream.Endpoint([("data", 8)])

        # # #

        # Submodules
        fifo      = stream.SyncFIFO([("data", 8)], 512)
        converter = stream.Converter(8, bus.data_width, reverse=True)
        self.submodules += fifo, converter
        self.submodules.dma  = WishboneDMAWriter(bus, with_csr=True, endianness=endianness)

        # Flow
        self.comb += [
            self.sink.connect(fifo.sink),
            fifo.source.connect(converter.sink),
            converter.source.connect(self.dma.sink),
        ]

# SD Mem2Block DMA ---------------------------------------------------------------------------------

class SDMem2BlockDMA(Module, AutoCSR):
    """Memory to Block DMA

    Read data from memory through DMA and generate a stream of blocks.
    """
    def __init__(self, bus, endianness):
        self.source = stream.Endpoint([("data", 8)])

        # # #

        # Submodules
        self.submodules.dma = WishboneDMAReader(bus, with_csr=True, endianness=endianness)
        converter = stream.Converter(bus.data_width, 8, reverse=True)
        fifo      = stream.SyncFIFO([("data", 8)], 512)
        self.submodules += converter, fifo

        # Flow
        self.comb += [
            self.dma.source.connect(converter.sink),
            converter.source.connect(fifo.sink),
            fifo.source.connect(self.source),
        ]
