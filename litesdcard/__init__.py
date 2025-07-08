#
# This file is part of LiteSDCard.
#
# Copyright (c) 2025 Fin Maaß <f.maass@vogl-electronic.com>
#
# Based on the former add_sdcard() function of the SoC class
# of soc.py in LiteX, which was:
# Copyright (c) 2014-2022 Florent Kermarrec <florent@enjoy-digital.fr>
# Copyright (c) 2013-2014 Sebastien Bourdeauducq <sb@m-labs.hk>
# Copyright (c) 2019 Gabriel L. Somlo <somlo@cmu.edu>

# SPDX-License-Identifier: BSD-2-Clause

from migen import *

from litex.gen import *

from litex.soc.interconnect import wishbone
from litex.soc.interconnect.csr_eventmanager import *

from litesdcard.emulator import SDEmulator
from litesdcard.phy import SDPHY
from litesdcard.core import SDCore
from litesdcard.frontend.dma import SDBlock2MemDMA, SDMem2BlockDMA

class LiteSDCard(LiteXModule):
    def __init__(self, soc, name="sdcard", mode="read+write", use_emulator=False):
        # Checks.
        assert mode in ["read", "write", "read+write"]

        # Emulator / Pads.
        if use_emulator:
            self.sdemulator = SDEmulator(soc.platform)
            pads = self.sdemulator.pads
        else:
            pads = soc.platform.request(name)

        # Core.
        self.phy = phy = SDPHY(pads, soc.platform.device, soc.sys_clk_freq, cmd_timeout=10e-1, data_timeout=10e-1)
        self.core = core = SDCore(phy)

        # Block2Mem DMA.
        if "read" in mode:
            bus = wishbone.Interface(
                data_width = soc.bus.data_width,
                adr_width  = soc.bus.get_address_width(standard="wishbone"),
                addressing = "word",
            )
            self.block2mem = block2mem = SDBlock2MemDMA(bus=bus, endianness=soc.cpu.endianness)
            self.comb += core.source.connect(block2mem.sink)
            dma_bus = getattr(soc, "dma_bus", soc.bus)
            dma_bus.add_master(master=bus)

        # Mem2Block DMA.
        if "write" in mode:
            bus = wishbone.Interface(
                data_width = soc.bus.data_width,
                adr_width  = soc.bus.get_address_width(standard="wishbone"),
                addressing = "word",
            )
            self.mem2block = mem2block = SDMem2BlockDMA(bus=bus, endianness=soc.cpu.endianness)
            self.comb += mem2block.source.connect(core.sink)
            dma_bus = getattr(soc, "dma_bus", soc.bus)
            dma_bus.add_master(master=bus)

        # Interrupts.
        self.ev = ev = EventManager()
        ev.card_detect = EventSourcePulse(description="SDCard has been ejected/inserted.")
        if "read" in mode:
            ev.block2mem_dma = EventSourcePulse(description="Block2Mem DMA terminated.")
        if "write" in mode:
            ev.mem2block_dma = EventSourcePulse(description="Mem2Block DMA terminated.")
        ev.cmd_done  = EventSourceLevel(description="Command completed.")
        ev.finalize()
        if "read" in mode:
            self.comb += ev.block2mem_dma.trigger.eq(block2mem.irq)
        if "write" in mode:
            self.comb += ev.mem2block_dma.trigger.eq(mem2block.irq)
        self.comb += [
            ev.card_detect.trigger.eq(phy.card_detect_irq),
            ev.cmd_done.trigger.eq(core.cmd_event.fields.done)
        ]
