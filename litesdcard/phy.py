#
# This file is part of LiteSDCard.
#
# Copyright (c) 2017-2023 Florent Kermarrec <florent@enjoy-digital.fr>
# Copyright (c) 2017 Pierre-Olivier Vauboin <po@lambdaconcept.com>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *
from migen.genlib.cdc import MultiReg
from migen.genlib.resetsync import AsyncResetSynchronizer

from litex.gen import *

from litex.build.io import SDROutput, SDRTristate

from litex.soc.interconnect.csr import *
from litex.soc.interconnect import stream

from litesdcard.common import *

# Pads ---------------------------------------------------------------------------------------------

_sdpads_layout = [
    ("clk", 1),
    ("cmd", [
        ("i",  1),
        ("o",  1),
        ("oe", 1)
    ]),
    ("data", [
        ("i",  4),
        ("o",  4),
        ("oe", 1)
    ]),
    ("data_i_ce", 1),
]

# SDCard PHY Clocker -------------------------------------------------------------------------------

class SDPHYClocker(LiteXModule):
    def __init__(self):
        self.divider = CSRStorage(9, reset=256)
        self.stop    = Signal()        # Stop input (for speed handling/backpressure).
        self.ce      = Signal()        # CE output  (for logic running in sys_clk domain).
        self.clk_en  = Signal(reset=1) # Clk enable input (from logic running in sys_clk domain).
        self.clk     = Signal()        # Clk output (for SDCard pads).

        # # #

        # SDCard Clk Divider Generation.
        clk   = Signal()
        count = Signal(10)
        self.sync += [
            If(~self.stop,
                count.eq(count + 1),
                If(count >= (self.divider.storage[1:] - 1),
                    clk.eq(~clk),
                    count.eq(0),
                )
            )
        ]

        # SDCard CE Generation.
        clk_d = Signal()
        self.sync += clk_d.eq(clk)
        self.comb += self.ce.eq(clk & ~clk_d)

        # Ensure we don't get short pulses on the SDCard Clk.
        ce_delayed = Signal()
        ce_latched = Signal()
        self.sync += If(clk_d, ce_delayed.eq(self.clk_en))
        self.comb += If(clk_d, ce_latched.eq(self.clk_en)).Else(ce_latched.eq(ce_delayed))
        self.comb += self.clk.eq(~clk & ce_latched)

# SDCard PHY Read ----------------------------------------------------------------------------------

@ResetInserter()
class SDPHYR(LiteXModule):
    def __init__(self, cmd=False, data=False, data_width=1, skip_start_bit=False):
        assert cmd or data
        self.pads_in  = pads_in = stream.Endpoint(_sdpads_layout)
        self.source   = source  = stream.Endpoint([("data", 8)])

        # # #

        pads_in_data = pads_in.cmd.i[:data_width] if cmd else pads_in.data.i[:data_width]

        # Xfer starts when data == 0
        start = Signal()
        run   = Signal()
        self.comb += start.eq(pads_in_data == 0)
        self.sync += If(pads_in.valid, run.eq(start | run))

        # Convert data to 8-bit stream
        converter = stream.Converter(data_width, 8, reverse=True)
        buf       = stream.Buffer([("data", 8)])
        self.submodules += converter, buf
        self.comb += [
            converter.sink.valid.eq(pads_in.valid & (run if skip_start_bit else (start | run))),
            converter.sink.data.eq(pads_in_data),
            converter.source.connect(buf.sink),
            buf.source.connect(source)
        ]

# SDCard PHY Init ----------------------------------------------------------------------------------

class SDPHYInit(LiteXModule):
    def __init__(self):
        self.initialize = CSR()
        self.pads_in  = pads_in  = stream.Endpoint(_sdpads_layout)
        self.pads_out = pads_out = stream.Endpoint(_sdpads_layout)

        # # #

        count = Signal(8)
        fsm = FSM(reset_state="IDLE")
        self.submodules += fsm
        fsm.act("IDLE",
            NextValue(count, 0),
            If(self.initialize.re,
                NextState("INITIALIZE")
            )
        )
        fsm.act("INITIALIZE",
            pads_out.clk.eq(1),
            pads_out.cmd.oe.eq(1),
            pads_out.cmd.o.eq(1),
            pads_out.data.oe.eq(1),
            pads_out.data.o.eq(0b1111),
            If(pads_out.ready,
                NextValue(count, count + 1),
                If(count == (80-1),
                    NextState("IDLE")
                )
            )
        )

# SDCard PHY Command Write -------------------------------------------------------------------------

class SDPHYCMDW(LiteXModule):
    def __init__(self):
        self.pads_in  = pads_in  = stream.Endpoint(_sdpads_layout)
        self.pads_out = pads_out = stream.Endpoint(_sdpads_layout)
        self.sink     = sink     = stream.Endpoint([("data", 8), ("cmd_type", 2)])

        self.done = Signal()

        # # #

        count = Signal(8)
        fsm   = FSM(reset_state="IDLE")
        self.submodules += fsm
        fsm.act("IDLE",
            NextValue(count, 0),
            If(sink.valid & pads_out.ready,
                NextState("WRITE")
            ).Else(
                self.done.eq(1),
            )
        )
        fsm.act("WRITE",
            pads_out.clk.eq(1),
            pads_out.cmd.oe.eq(1),
            Case(count, {i: pads_out.cmd.o.eq(sink.data[8-1-i]) for i in range(8)}),
            If(pads_out.ready,
                NextValue(count, count + 1),
                If(count == (8-1),
                    If(sink.last & (sink.cmd_type == SDCARD_CTRL_RESPONSE_NONE),
                        NextState("CLK8")
                    ).Else(
                        sink.ready.eq(1),
                        NextState("IDLE")
                    )
                )
            )
        )
        fsm.act("CLK8",
            pads_out.clk.eq(1),
            pads_out.cmd.oe.eq(1),
            pads_out.cmd.o.eq(1),
            If(pads_out.ready,
                NextValue(count, count + 1),
                If(count == (8-1),
                    sink.ready.eq(1),
                    NextState("IDLE")
                )
            )
        )

# SDCard PHY Command Read --------------------------------------------------------------------------

class SDPHYCMDR(LiteXModule):
    def __init__(self, sys_clk_freq, cmd_timeout, cmdw, busy_timeout=1):
        self.pads_in  = pads_in  = stream.Endpoint(_sdpads_layout)
        self.pads_out = pads_out = stream.Endpoint(_sdpads_layout)
        self.sink     = sink     = stream.Endpoint([("cmd_type", 2), ("data_type", 2), ("length", 8)])
        self.source   = source   = stream.Endpoint([("data", 8), ("status", 3)])

        # # #

        timeout = Signal(32, reset=int(cmd_timeout*sys_clk_freq))
        count   = Signal(8)
        busy    = Signal()

        cmdr = SDPHYR(cmd=True, data_width=1, skip_start_bit=False)
        self.comb += pads_in.connect(cmdr.pads_in)
        fsm  = FSM(reset_state="IDLE")
        self.submodules += cmdr, fsm
        fsm.act("IDLE",
            # Preload Timeout with Cmd Timeout.
            NextValue(timeout, int(cmd_timeout*sys_clk_freq)),
            # Reset Count/Busy flags.
            NextValue(count, 0),
            NextValue(busy, 1),
            # When the Cmd has been sent to the SDCard, get the response.
            If(sink.valid & pads_out.ready & cmdw.done,
                NextValue(cmdr.reset, 1),
                NextState("WAIT"),
            )
        )
        fsm.act("WAIT",
            # Drive Clk.
            pads_out.clk.eq(1),
            # Reset CMDR.
            NextValue(cmdr.reset, 0),
            # Change state on Cmd response start.
            If(cmdr.source.valid,
                NextState("CMD")
            ),
            # Timeout.
            NextValue(timeout, timeout - 1),
            If(timeout == 0,
                NextState("TIMEOUT")
            )
        )
        fsm.act("CMD",
            pads_out.clk.eq(1),
            source.valid.eq(cmdr.source.valid),
            source.status.eq(SDCARD_STREAM_STATUS_OK),
            source.last.eq(count == (sink.length - 1)),
            source.data.eq(cmdr.source.data),
            If(cmdr.source.valid & source.ready,
                cmdr.source.ready.eq(1),
                NextValue(count, count + 1),
                If(source.last,
                    sink.ready.eq(1),
                    If(sink.cmd_type == SDCARD_CTRL_RESPONSE_SHORT_BUSY,
                        # Generate the last valid cycle in BUSY state.
                        source.valid.eq(0),
                        # Preload Timeout with Busy Timeout.
                        NextValue(timeout, int(busy_timeout*sys_clk_freq)),
                        NextState("BUSY")
                    ).Elif(sink.data_type == SDCARD_CTRL_DATA_TRANSFER_NONE,
                        NextValue(count, 0),
                        NextState("CLK8")
                    ).Else(
                        NextState("IDLE")
                    )
                )
            ),
            # Timeout.
            NextValue(timeout, timeout - 1),
            If(timeout == 0,
                NextState("TIMEOUT")
            ),
        )
        fsm.act("BUSY",
            pads_out.clk.eq(1),
            # D0 is kept low by the SDCard while busy.
            If(pads_in.valid & pads_in.data.i[0],
                NextValue(busy, 0),
            ),
            # Generate the last cycle of the Cmd Response when no longer busy.
            If(~busy,
                source.valid.eq(1),
                source.last.eq(1),
                source.status.eq(SDCARD_STREAM_STATUS_OK),
                If(source.ready,
                    NextValue(count, 0),
                    NextState("CLK8")
                )
            ),
            # Timeout.
            NextValue(timeout, timeout - 1),
            If(timeout == 0,
                NextState("TIMEOUT")
            )
        )
        fsm.act("CLK8",
            pads_out.clk.eq(1),
            pads_out.cmd.oe.eq(1),
            pads_out.cmd.o.eq(1),
            If(pads_out.ready,
                NextValue(count, count + 1),
                If(count == (8-1),
                    NextState("IDLE")
                )
            )
        )
        fsm.act("TIMEOUT",
            sink.ready.eq(1), # Ack Cmd.
            source.valid.eq(1),
            source.last.eq(1),
            source.status.eq(SDCARD_STREAM_STATUS_TIMEOUT),
            If(source.ready,
                NextState("IDLE")
            )
        )

# SDCard PHY Data Write ----------------------------------------------------------------------------

class SDPHYDATAW(LiteXModule):
    def __init__(self):
        self.pads_in  = pads_in  = stream.Endpoint(_sdpads_layout)
        self.pads_out = pads_out = stream.Endpoint(_sdpads_layout)
        self.sink     = sink     = stream.Endpoint([("data", 8)])
        self.stop     = Signal()

        self.status   = CSRStatus(fields=[
            CSRField("accepted",    size=1, offset=0),
            CSRField("crc_error",   size=1, offset=1),
            CSRField("write_error", size=1, offset=2),
        ])

        # # #

        count = Signal(8)

        accepted    = Signal()
        crc_error   = Signal()
        write_error = Signal()
        self.comb += self.status.fields.accepted.eq(accepted)
        self.comb += self.status.fields.crc_error.eq(crc_error)
        self.comb += self.status.fields.write_error.eq(write_error)

        self.crc = SDPHYR(data=True, data_width=1, skip_start_bit=True)
        self.comb += self.crc.pads_in.eq(pads_in)

        self.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            NextValue(accepted,    0),
            NextValue(crc_error,   0),
            NextValue(write_error, 0),
            NextValue(count, 0),
            If(sink.valid & pads_out.ready,
                NextState("CLK8")
            )
        )
        # CHECKME: Understand why this is needed.
        fsm.act("CLK8",
            pads_out.clk.eq(1),
            pads_out.cmd.oe.eq(1),
            pads_out.cmd.o.eq(1),
            If(pads_out.ready,
                NextValue(count, count + 1),
                If(count == (8-1),
                    NextValue(count, 0),
                    NextState("START")
                )
            )
        )
        fsm.act("START",
            pads_out.clk.eq(1),
            pads_out.data.oe.eq(1),
            pads_out.data.o.eq(0),
            If(pads_out.ready,
                NextState("DATA")
            )
        )
        fsm.act("DATA",
            self.stop.eq(~sink.valid),
            pads_out.clk.eq(1),
            pads_out.data.oe.eq(1),
            Case(count, {
                0: pads_out.data.o.eq(sink.data[4:8]),
                1: pads_out.data.o.eq(sink.data[0:4]),
            }),
            If(pads_out.ready,
                NextValue(count, count + 1),
                If(count == (2-1),
                    NextValue(count, 0),
                    If(sink.last,
                        NextState("STOP")
                    ).Else(
                        sink.ready.eq(1)
                    )
                )
            )
        )
        fsm.act("STOP",
            pads_out.clk.eq(1),
            pads_out.data.oe.eq(1),
            pads_out.data.o.eq(0b1111),
            If(pads_out.ready,
                self.crc.reset.eq(1),
                NextState("CRC")
            )
        )
        fsm.act("CRC",
            pads_out.clk.eq(1),
            If(self.crc.source.valid,
                NextValue(accepted,    self.crc.source.data[5:] == 0b010),
                NextValue(crc_error,   self.crc.source.data[5:] == 0b101),
                NextValue(write_error, self.crc.source.data[5:] == 0b110),
                NextState("BUSY")
            )
        )
        fsm.act("BUSY",
            pads_out.clk.eq(1),
            If(pads_in.valid & pads_in.data.i[0],
                sink.ready.eq(1),
                NextState("IDLE")
            )
        )

# SDCard PHY Data Read -----------------------------------------------------------------------------

class SDPHYDATAR(LiteXModule):
    def __init__(self, sys_clk_freq, data_timeout):
        self.pads_in  = pads_in  = stream.Endpoint(_sdpads_layout)
        self.pads_out = pads_out = stream.Endpoint(_sdpads_layout)
        self.sink     = sink     = stream.Endpoint([("block_length", 10)])
        self.source   = source   = stream.Endpoint([("data", 8), ("status", 3)])
        self.stop     = Signal()

        # # #

        timeout = Signal(32, reset=int(data_timeout*sys_clk_freq))
        count   = Signal(10)

        datar = SDPHYR(data=True, data_width=4, skip_start_bit=True)
        self.comb += pads_in.connect(datar.pads_in)
        fsm = FSM(reset_state="IDLE")
        self.submodules += datar, fsm
        fsm.act("IDLE",
            NextValue(count, 0),
            If(sink.valid & pads_out.ready,
                pads_out.clk.eq(1),
                NextValue(timeout, timeout.reset),
                NextValue(count, 0),
                NextValue(datar.reset, 1),
                NextState("WAIT")
            )
        )
        fsm.act("WAIT",
            pads_out.clk.eq(1),
            NextValue(datar.reset, 0),
            NextValue(timeout, timeout - 1),
            If(datar.source.valid,
                NextState("DATA")
            ),
            NextValue(timeout, timeout - 1),
            If(timeout == 0,
                sink.ready.eq(1),
                NextState("TIMEOUT")
            )
        )
        fsm.act("DATA",
            pads_out.clk.eq(1),
            source.valid.eq(datar.source.valid),
            source.status.eq(SDCARD_STREAM_STATUS_OK),
            source.first.eq(count == 0),
            source.last.eq(count == (sink.block_length + 8 - 1)), # 1 block + 64-bit CRC
            source.data.eq(datar.source.data),
            If(source.valid,
                If(source.ready,
                    datar.source.ready.eq(1),
                    NextValue(count, count + 1),
                    If(source.last,
                        sink.ready.eq(1),
                        If(sink.last,
                            NextValue(count, 0),
                            NextState("CLK40")
                        ).Else(
                            NextState("IDLE")
                        )
                    )
                ).Else(
                     self.stop.eq(1)
                )
            ),
            NextValue(timeout, timeout - 1),
            If(timeout == 0,
                sink.ready.eq(1),
                NextState("TIMEOUT")
            )
        )
        fsm.act("CLK40",
            pads_out.clk.eq(1),
            If(pads_out.ready,
                NextValue(count, count + 1),
                If(count == (40-1),
                    NextState("IDLE")
                )
            )
        )
        fsm.act("TIMEOUT",
            source.valid.eq(1),
            source.status.eq(SDCARD_STREAM_STATUS_TIMEOUT),
            source.last.eq(1),
            If(source.ready,
                NextState("IDLE")
            )
        )

# SDCard PHY IO ------------------------------------------------------------------------------------

class SDPHYIO(LiteXModule):
    def add_data_i_ce(self, clocker, sdpads):
        # Sample Data on Sys Clk before SDCard Clk rising edge.
        clk_i   = Signal()
        clk_i_d = Signal()
        self.specials += MultiReg(~clocker.clk, clk_i, n=1, odomain="sys") # n = 1 = SDROutput / SDRTristate delay.
        self.sync += clk_i_d.eq(clk_i)
        self.comb += sdpads.data_i_ce.eq(clk_i & ~clk_i_d) # Rising Edge.

class SDPHYIOGen(SDPHYIO):
    def __init__(self, clocker, sdpads, pads):
        # Rst
        if hasattr(pads, "rst"):
            self.comb += pads.rst.eq(0)

        # Clk
        self.specials += SDROutput(
            clk = ClockSignal("sys"),
            i   = ~clocker.clk,
            o   = pads.clk
        )

        # Cmd
        self.specials += SDRTristate(
            clk = ClockSignal("sys"),
            io  = pads.cmd,
            o   = sdpads.cmd.o,
            oe  = sdpads.cmd.oe,
            i   = sdpads.cmd.i,
        )

        # Data
        for i in range(4):
            self.specials += SDRTristate(
                clk = ClockSignal("sys"),
                io  = pads.data[i],
                o   = sdpads.data.o[i],
                oe  = sdpads.data.oe,
                i   = sdpads.data.i[i],
            )
        self.add_data_i_ce(clocker, sdpads)

        # Direction (optional)
        if hasattr(pads, "cmd_dir"):
            self.specials += [
                SDROutput(
                    clk = ClockSignal("sys"),
                    i   = sdpads.cmd.oe,
                    o   = pads.cmd_dir,
                ),
                SDROutput(
                    clk = ClockSignal("sys"),
                    i   = sdpads.data.oe,
                    o   = pads.dat0_dir,
                ),
                SDROutput(
                    clk = ClockSignal("sys"),
                    i   = sdpads.data.oe,
                    o   = pads.dat13_dir,
                )
            ]

# SDCard PHY Emulator ------------------------------------------------------------------------------

class SDPHYIOEmulator(SDPHYIO):
    def __init__(self, clocker, sdpads, pads):
        # Clk
        self.comb += pads.clk.eq(clocker.clk)

        # Cmd
        self.comb += [
            pads.cmd_i.eq(1),
            If(sdpads.cmd.oe, pads.cmd_i.eq(sdpads.cmd.o)),
            sdpads.cmd.i.eq(1),
            If(~pads.cmd_t, sdpads.cmd.i.eq(pads.cmd_o)),
        ]

        # Data
        self.comb += [
            pads.dat_i.eq(0b1111),
            If(sdpads.data.oe, pads.dat_i.eq(sdpads.data.o)),
            sdpads.data.i.eq(0b1111),
        ]
        self.data_i_ce(clocker, sdpads)
        for i in range(4):
            self.comb += If(~pads.dat_t[i], sdpads.data.i[i].eq(pads.dat_o[i]))

# SDCard PHY ---------------------------------------------------------------------------------------

class SDPHY(LiteXModule):
    def __init__(self, pads, device, sys_clk_freq, cmd_timeout=10e-3, data_timeout=10e-3):
        use_emulator = hasattr(pads, "cmd_t") and hasattr(pads, "dat_t")
        self.card_detect = CSRStatus() # Assume SDCard is present if no cd pin.
        self.comb += self.card_detect.status.eq(getattr(pads, "cd", 0))

        self.clocker = clocker = SDPHYClocker()
        self.init    = init    = SDPHYInit()
        self.cmdw    = cmdw    = SDPHYCMDW()
        self.cmdr    = cmdr    = SDPHYCMDR(sys_clk_freq, cmd_timeout, cmdw)
        self.dataw   = dataw   = SDPHYDATAW()
        self.datar   = datar   = SDPHYDATAR(sys_clk_freq, data_timeout)

        # # #

        self.sdpads = sdpads = Record(_sdpads_layout)

        # IOs
        sdphy_cls = SDPHYIOEmulator if use_emulator else SDPHYIOGen
        self.io = sdphy_cls(clocker, sdpads, pads)

        # Connect pads_out of submodules to physical pads ----------------------------------------
        self.comb += [
            sdpads.clk.eq(    Reduce("OR", [m.pads_out.clk     for m in [init, cmdw, cmdr, dataw, datar]])),
            sdpads.cmd.oe.eq( Reduce("OR", [m.pads_out.cmd.oe  for m in [init, cmdw, cmdr, dataw, datar]])),
            sdpads.cmd.o.eq(  Reduce("OR", [m.pads_out.cmd.o   for m in [init, cmdw, cmdr, dataw, datar]])),
            sdpads.data.oe.eq(Reduce("OR", [m.pads_out.data.oe for m in [init, cmdw, cmdr, dataw, datar]])),
            sdpads.data.o.eq( Reduce("OR", [m.pads_out.data.o  for m in [init, cmdw, cmdr, dataw, datar]])),
        ]
        for m in [init, cmdw, cmdr, dataw, datar]:
            self.comb += m.pads_out.ready.eq(self.clocker.ce)
        self.comb += self.clocker.clk_en.eq(sdpads.clk)

        # Connect physical pads to pads_in of submodules -------------------------------------------
        for m in [init, cmdw, cmdr, dataw, datar]:
            self.comb += m.pads_in.valid.eq(sdpads.data_i_ce)
            self.comb += m.pads_in.cmd.i.eq(sdpads.cmd.i)
            self.comb += m.pads_in.data.i.eq(sdpads.data.i)


        # Speed Throttling -------------------------------------------------------------------------
        self.comb += clocker.stop.eq(dataw.stop | datar.stop)

        # IRQs -------------------------------------------------------------------------------------
        self.card_detect_irq = Signal() # Generate Card Detect IRQ on level change.
        card_detect_d = Signal()
        self.sync += card_detect_d.eq(self.card_detect.status)
        self.sync += self.card_detect_irq.eq(self.card_detect.status ^ card_detect_d)
