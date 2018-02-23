# Copyright (c) 2017 Micah Elizabeth Scott

from migen import *

from litex.soc.interconnect.csr import *
from litex.soc.interconnect.csr_eventmanager import *
from litex.soc.interconnect import wishbone

from litesdcard.emulator.linklayer import SDLinkLayer


class SDEmulator(Module, AutoCSR):
    """Core for emulating SD card memory a block at a time,
       with reads and writes backed by software.
       """

    # Read and write buffers, each a single 512 byte block
    mem_size = 1024

    def _connect_event(self, ev, act, done):
        # Event triggered on 'act' positive edge, pulses 'done' on clear
        prev_act = Signal()
        self.sync += prev_act.eq(act)
        self.comb += ev.trigger.eq(act & ~prev_act)
        self.comb += done.eq(ev.clear)

    def __init__(self, platform, pads):
        self.submodules.ll = ClockDomainsRenamer("local")(SDLinkLayer(platform, pads))

        # Event interrupts and acknowledgment
        self.submodules.ev = EventManager()
        self.ev.read = EventSourcePulse()
        self.ev.write = EventSourcePulse()
        self.ev.finalize()
        self._connect_event(self.ev.read, self.ll.block_read_act, self.ll.block_read_go)
        self._connect_event(self.ev.write, self.ll.block_write_act, self.ll.block_write_done)

        # Wishbone access to SRAM buffers
        self.bus = wishbone.Interface()
        self.submodules.wb_rd_buffer = wishbone.SRAM(self.ll.rd_buffer, read_only=False)
        self.submodules.wb_wr_buffer = wishbone.SRAM(self.ll.wr_buffer, read_only=False)
        wb_slaves = [
            (lambda a: a[9] == 0, self.wb_rd_buffer.bus),
            (lambda a: a[9] == 1, self.wb_wr_buffer.bus)
        ]
        self.submodules.wb_decoder = wishbone.Decoder(self.bus, wb_slaves, register=True)

        # Local reset domain
        self._reset = CSRStorage()
        self.clock_domains.cd_local = ClockDomain()
        self.comb += self.cd_local.clk.eq(ClockSignal())
        self.comb += self.cd_local.rst.eq(ResetSignal() | self._reset.storage)

        # Current data operation
        self._read_act = CSRStatus()
        self._read_addr = CSRStatus(32)
        self._read_byteaddr = CSRStatus(32)
        self._read_num = CSRStatus(32)
        self._read_stop = CSRStatus()
        self._write_act = CSRStatus()
        self._write_addr = CSRStatus(32)
        self._write_byteaddr = CSRStatus(32)
        self._write_num = CSRStatus(32)
        self._preerase_num = CSRStatus(23)
        self._erase_start = CSRStatus(32)
        self._erase_end = CSRStatus(32)
        self.comb += [
            self._read_act.status.eq(self.ll.block_read_act),
            self._read_addr.status.eq(self.ll.block_read_addr),
            self._read_byteaddr.status.eq(self.ll.block_read_byteaddr),
            self._read_num.status.eq(self.ll.block_read_num),
            self._read_stop.status.eq(self.ll.block_read_stop),
            self._write_act.status.eq(self.ll.block_write_act),
            self._write_addr.status.eq(self.ll.block_write_addr),
            self._write_byteaddr.status.eq(self.ll.block_write_byteaddr),
            self._write_num.status.eq(self.ll.block_write_num),
            self._preerase_num.status.eq(self.ll.block_preerase_num),
            self._erase_start.status.eq(self.ll.block_erase_start),
            self._erase_end.status.eq(self.ll.block_erase_end),
        ]

        # Informational registers, not needed for data transfer
        self._info_bits = CSRStatus(16)
        self.comb += self._info_bits.status.eq(Cat(
            self.ll.mode_4bit,
            self.ll.mode_spi,
            self.ll.host_hc_support,
            Constant(False),             # Reserved bit 3
            Constant(False),             # Reserved bit 4
            Constant(False),             # Reserved bit 5
            Constant(False),             # Reserved bit 6
            Constant(False),             # Reserved bit 7
            self.ll.info_card_desel,
            self.ll.err_op_out_range,
            self.ll.err_unhandled_cmd,
            self.ll.err_cmd_crc,
        ))
        self._most_recent_cmd = CSRStatus(len(self.ll.cmd_in_cmd))
        self.comb += self._most_recent_cmd.status.eq(self.ll.cmd_in_cmd)
        self._card_status = CSRStatus(len(self.ll.card_status))
        self.comb += self._card_status.status.eq(self.ll.card_status)
