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

from litesdcard.crc import CRC16

from litesdcard.common import *

# Pads ---------------------------------------------------------------------------------------------

def _sdpads_layout(data_width=4):
    return [
        ("clk", 1),
        ("cmd", [
            ("i",  1),
            ("o",  1),
            ("oe", 1)
        ]),
        ("data", [
            ("i",  data_width),
            ("o",  data_width),
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
        half  = Signal(10) # >= 1 : half-period in sys-clk cycles.
        count = Signal(10)

        # half = max(1, ceil((storage + 1) / 2)).
        self.comb += half.eq((self.divider.storage + 1) >> 1)

        self.sync += [
            If(~self.stop,
                If(count <= 1,
                    clk.eq(~clk),       # 50 % duty-cycle toggle.
                    count.eq(half)      # reload count.
                ).Else(
                    count.eq(count - 1) # simple down-count.
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
    def __init__(self, sdpads_layout, cmd=False, data=False, data_width=1, skip_start_bit=False):
        assert cmd or data
        self.pads_in  = pads_in = stream.Endpoint(sdpads_layout)
        self.source   = source  = stream.Endpoint([("data", 8)])

        # # #

        pads_in_data = pads_in.cmd.i[:data_width] if cmd else pads_in.data.i[:data_width]

        # Xfer starts when data == 0
        start = Signal()
        run   = Signal()
        self.comb += start.eq(pads_in_data == 0)
        self.sync += If(pads_in.valid, run.eq(start | run))

        # Convert data to 8-bit stream
        self.converter = converter = stream.Converter(data_width, 8, reverse=True)
        self.buf       = buf       = stream.Buffer([("data", 8)])
        self.comb += [
            converter.sink.valid.eq(pads_in.valid & (run if skip_start_bit else (start | run))),
            converter.sink.data.eq(pads_in_data),
            converter.source.connect(buf.sink),
            buf.source.connect(source)
        ]

# SDCard PHY Init ----------------------------------------------------------------------------------

class SDPHYInit(LiteXModule):
    def __init__(self, sdpads_layout):
        self.initialize = CSR()
        self.pads_in  = pads_in  = stream.Endpoint(sdpads_layout)
        self.pads_out = pads_out = stream.Endpoint(sdpads_layout)

        # # #

        count = Signal(8)

        self.fsm = fsm = FSM(reset_state="IDLE")
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
            pads_out.data.o.eq(Replicate(C(1), len(pads_out.data.o))),
            If(pads_out.ready,
                NextValue(count, count + 1),
                If(count == (80-1),
                    NextState("IDLE")
                )
            )
        )

# SDCard PHY Command Write -------------------------------------------------------------------------

class SDPHYCMDW(LiteXModule):
    def __init__(self, sdpads_layout):
        self.pads_in  = pads_in  = stream.Endpoint(sdpads_layout)
        self.pads_out = pads_out = stream.Endpoint(sdpads_layout)
        self.sink     = sink     = stream.Endpoint([("data", 8), ("cmd_type", 2)])

        self.done = Signal()

        # # #

        count = Signal(8)

        self.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            NextValue(count, 0),
            If(sink.valid & pads_out.ready,
                NextState("WRITE")
            ).Else(
                self.done.eq(1),
            )
        )
        fsm.act("WRITE",
            If(sink.valid,
                pads_out.clk.eq(1),
                pads_out.cmd.oe.eq(1),
                Case(count, {i: pads_out.cmd.o.eq(sink.data[8-1-i]) for i in range(8)}),
                If(pads_out.ready,
                    NextValue(count, count + 1),
                    If(count == (8-1),
                        NextValue(count, 0),
                        sink.ready.eq(1),
                        If(sink.last,
                            If(sink.cmd_type == SDCARD_CTRL_RESPONSE_NONE,
                                sink.ready.eq(0),
                                NextState("CLK8")
                            ).Else(
                                NextState("IDLE")
                            )
                        )
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
    def __init__(self, sdpads_layout, sys_clk_freq, cmd_timeout, cmdw):
        self.pads_in  = pads_in  = stream.Endpoint(sdpads_layout)
        self.pads_out = pads_out = stream.Endpoint(sdpads_layout)
        self.sink     = sink     = stream.Endpoint([("cmd_type", 2), ("data_type", 2), ("length", 8)])
        self.source   = source   = stream.Endpoint([("data", 8), ("status", 3)])

        self.timeout  = CSRStorage(32, reset=int(cmd_timeout*sys_clk_freq))

        # # #

        timeout = Signal(32)
        count   = Signal(8)
        last_data = Signal(len(source.data))

        self.cmdr = cmdr = SDPHYR(sdpads_layout, cmd=True, data_width=1, skip_start_bit=False)
        self.comb += pads_in.connect(cmdr.pads_in)

        self.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            # Preload Timeout with Cmd Timeout.
            NextValue(timeout, self.timeout.storage),
            # Reset Count flag.
            NextValue(count, 0),
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
                    If((sink.cmd_type == SDCARD_CTRL_RESPONSE_SHORT_BUSY) |
                       (sink.data_type == SDCARD_CTRL_DATA_TRANSFER_NONE),
                       # Generate the last valid cycle in BUSY or CLK8 state.
                        source.valid.eq(0),
                        NextValue(last_data, source.data),
                        NextValue(count, 0),
                        NextState("CLK8")
                    ).Else(
                        sink.ready.eq(1),
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
                source.valid.eq(1),
                source.last.eq(1),
                source.status.eq(SDCARD_STREAM_STATUS_OK),
                source.data.eq(last_data),
                NextState("IDLE")
            ),
            # Timeout.
            NextValue(timeout, timeout - 1),
            If(timeout == 0,
                NextState("TIMEOUT")
            )
        )
        # 8 clk cycles before shutting the clk down,
        # also 8 clk cycles before the next cmd can be sent.
        fsm.act("CLK8",
            pads_out.clk.eq(1),
            pads_out.cmd.oe.eq(1),
            pads_out.cmd.o.eq(1),
            If(pads_out.ready,
                NextValue(count, count + 1),
                If(count == (8-1),
                    sink.ready.eq(1),
                    If(sink.cmd_type == SDCARD_CTRL_RESPONSE_SHORT_BUSY,
                        NextState("BUSY")
                    ).Else(
                        source.valid.eq(1),
                        source.last.eq(1),
                        source.status.eq(SDCARD_STREAM_STATUS_OK),
                        source.data.eq(last_data),
                        NextState("IDLE"),
                    )                    
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
    def __init__(self, sdpads_layout, data_width):
        self.pads_in  = pads_in  = stream.Endpoint(sdpads_layout)
        self.pads_out = pads_out = stream.Endpoint(sdpads_layout)
        self.sink     = sink     = stream.Endpoint([("data", 8), ("last_block", 1)])
        self.source   = source   = stream.Endpoint([("status", 3)])
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

        self.crc = SDPHYR(sdpads_layout, data=True, data_width=1, skip_start_bit=True)
        self.comb += self.crc.pads_in.eq(pads_in)

        self.crc16 = crc16 = CRC16(pads_out.data.o, count)

        self.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            NextValue(count, 0),
            If(sink.valid & pads_out.ready,
                NextValue(accepted, 0),
                NextValue(crc_error, 0),
                NextValue(write_error, 0),
                NextState("CLK2")
            )
        )
        # after card respose on cmd, we need to wait 2 clk cycles before sending data
        fsm.act("CLK2",
            pads_out.clk.eq(1),
            pads_out.cmd.oe.eq(1),
            pads_out.cmd.o.eq(1),
            If(pads_out.ready,
                NextValue(count, count + 1),
                If(count == (2-1),
                    NextValue(count, 0),
                    NextState("START")
                )
            )
        )
        fsm.act("START",
            pads_out.clk.eq(1),
            pads_out.data.oe.eq(1),
            pads_out.data.o.eq(0),
            crc16.reset.eq(1),
            If(pads_out.ready,
                NextState("DATA")
            )
        )

        data_cases = {}
        # SD_PHY_SPEED_1X.
        data_cases["default"] = [
            Case(count, {
                0 : pads_out.data.o[0].eq(sink.data[7]),
                1 : pads_out.data.o[0].eq(sink.data[6]),
                2 : pads_out.data.o[0].eq(sink.data[5]),
                3 : pads_out.data.o[0].eq(sink.data[4]),
                4 : pads_out.data.o[0].eq(sink.data[3]),
                5 : pads_out.data.o[0].eq(sink.data[2]),
                6 : pads_out.data.o[0].eq(sink.data[1]),
                7 : pads_out.data.o[0].eq(sink.data[0]),
            }),
            If(pads_out.ready,
                If(count == (8-1),
                    NextValue(count, 0),
                    If(sink.last,
                        NextState("CRC16")
                    ).Else(
                        sink.ready.eq(1)
                    )
                ).Else(
                    NextValue(count, count + 1),
                )
            )
        ]

        # SD_PHY_SPEED_4X.
        if len(pads_out.data.o) >= 4:
            data_cases[SD_PHY_SPEED_4X] = [
                Case(count, {
                    0: pads_out.data.o[:4].eq(sink.data[4:8]),
                    1: pads_out.data.o[:4].eq(sink.data[0:4]),
                }),
                If(pads_out.ready,
                    If(count == (2-1),
                        NextValue(count, 0),
                        If(sink.last,
                            NextState("CRC16")
                        ).Else(
                            sink.ready.eq(1)
                        )
                    ).Else(
                        NextValue(count, count + 1),
                    )
                )
            ]

        # SD_PHY_SPEED_8X.
        if len(pads_out.data.o) >= 8:
            data_cases[SD_PHY_SPEED_8X] = [
                pads_out.data.o[:8].eq(sink.data[:8]),
                If(pads_out.ready,
                    If(sink.last,
                        NextState("CRC16")
                    ).Else(
                        sink.ready.eq(1)
                    )
                )
            ]

        fsm.act("DATA",
            self.stop.eq(~sink.valid),
            pads_out.clk.eq(1),
            pads_out.data.oe.eq(1),
            Case(data_width, data_cases),
            crc16.enable.eq(pads_out.ready),
        )
        fsm.act("CRC16",
            pads_out.clk.eq(1),
            pads_out.data.oe.eq(1),
            pads_out.data.o.eq(crc16.data_pads_out),
            If(pads_out.ready,
                NextValue(count, count + 1),
                If(count == (16-1),
                    NextValue(count, 0),
                    NextState("STOP")
                )
            )
        )
        fsm.act("STOP",
            pads_out.clk.eq(1),
            pads_out.data.oe.eq(1),
            pads_out.data.o.eq(Replicate(C(1), len(pads_out.data.o))),
            If(pads_out.ready,
                self.crc.reset.eq(1),
                NextState("CRC")
            )
        )
        fsm.act("CRC",
            pads_out.clk.eq(1),
            If(self.crc.source.valid,
                source.valid.eq(1),
                Case(self.crc.source.data[5:], {
                    0b010: [NextValue(accepted, 1), source.status.eq(SDCARD_STREAM_STATUS_DATAACCEPTED)],
                    0b101: [NextValue(crc_error, 1), source.status.eq(SDCARD_STREAM_STATUS_CRCERROR)],
                    0b110: [NextValue(write_error, 1), source.status.eq(SDCARD_STREAM_STATUS_WRITEERROR)],
                }),
                If(sink.last_block,
                    NextState("CLK8"),
                ).Else(
                    NextState("BUSY"),
                )
            )
        )
        # Required 8 clk cycles before shutting down the clk.
        fsm.act("CLK8",
            pads_out.clk.eq(1),
            pads_out.cmd.oe.eq(1),
            pads_out.cmd.o.eq(1),
            If(pads_out.ready,
                NextValue(count, count + 1),
                If(count == (8-1),
                    NextValue(count, 0),
                    NextState("BUSY")
                )
            )
        )
        fsm.act("BUSY",
            pads_out.clk.eq(1),
            NextValue(count, 0),
            If(pads_in.valid & pads_in.data.i[0],
                sink.ready.eq(1),
                If(sink.last_block,
                    NextState("IDLE"),
                ).Else(
                    NextState("CLK2"),
                )
            )
        )

# SDCard PHY Data Read -----------------------------------------------------------------------------

class SDPHYDATAR(LiteXModule):
    def __init__(self, sdpads_layout, data_width, sys_clk_freq, data_timeout):
        self.pads_in  = pads_in  = stream.Endpoint(sdpads_layout)
        self.pads_out = pads_out = stream.Endpoint(sdpads_layout)
        self.sink     = sink     = stream.Endpoint([("block_length", 10)])
        self.source   = source   = stream.Endpoint([("data", 8), ("status", 3), ("drop", 1)])
        self.stop     = Signal()

        self.timeout  = CSRStorage(32, reset=int(data_timeout*sys_clk_freq))

        # # #

        timeout     = Signal(32)
        count       = Signal(10)
        crc_count   = Signal(max=17)
        crc_len     = Signal(max=17)
        crc_correct = Signal()
        crc_error   = Signal()
        data_done   = Signal()
        data_len    = Signal(max=9)
        data_count  = Signal(16)

        datar_source  = stream.Endpoint([("data", 8)])
        datar_reset   = Signal()
        datar_valid   = Signal()

        self.crc16 = crc16 = CRC16(pads_in.data.i, crc_count)

        self.comb += [
            crc16.reset.eq(datar_reset),
            data_done.eq(data_count == 0),
            crc16.enable.eq(datar_valid & ~data_done),
        ]

        self.sync += [
            If(crc16.reset,
                data_count.eq(sink.block_length * 8),
            ).Elif(crc16.enable,
                data_count.eq(data_count - data_len),
            )
        ]

        datar_cases = {}

        # SD_PHY_SPEED_1X.
        self.datar_1x = datar_1x = SDPHYR(sdpads_layout, data=True, data_width=1, skip_start_bit=True)
        self.comb += [
            datar_1x.reset.eq(datar_reset),
            pads_in.connect(datar_1x.pads_in),
        ]
        datar_cases["default"] = [
            datar_1x.source.connect(datar_source),
            crc_len.eq(2),
            data_len.eq(1),
            datar_valid.eq(datar_1x.converter.sink.valid),
            crc_correct.eq(crc16.data_pads_out[0] == pads_in.data.i[0]),
        ]

        # SD_PHY_SPEED_4X.
        if len(pads_in.data.i) >= 4:
            self.datar_4x = datar_4x = SDPHYR(sdpads_layout, data=True, data_width=4, skip_start_bit=True)
            self.comb += [
                datar_4x.reset.eq(datar_reset),
                pads_in.connect(datar_4x.pads_in),
            ]
            datar_cases[SD_PHY_SPEED_4X] = [
                datar_4x.source.connect(datar_source),
                crc_len.eq(8),
                data_len.eq(4),
                datar_valid.eq(datar_4x.converter.sink.valid),
                crc_correct.eq(crc16.data_pads_out[:4] == pads_in.data.i[:4]),
            ]

        # SD_PHY_SPEED_8X.
        if len(pads_in.data.i) >= 8:
            self.datar_8x = datar_8x = SDPHYR(sdpads_layout, data=True, data_width=8, skip_start_bit=True)
            self.comb += [
                datar_8x.reset.eq(datar_reset),
                pads_in.connect(datar_8x.pads_in),
            ]
            datar_cases[SD_PHY_SPEED_8X] = [
                datar_8x.source.connect(datar_source),
                crc_len.eq(16),
                data_len.eq(8),
                datar_valid.eq(datar_8x.converter.sink.valid),
                crc_correct.eq(crc16.data_pads_out[:8] == pads_in.data.i[:8]),
            ]

        self.comb += Case(data_width, datar_cases)

        self.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            NextValue(count, 0),
            NextValue(crc_count, 0),
            If(sink.valid & pads_out.ready,
                pads_out.clk.eq(1),
                NextValue(timeout, self.timeout.storage),
                NextValue(crc_error, 0),
                NextValue(datar_reset, 1),
                NextState("WAIT")
            )
        )
        fsm.act("WAIT",
            pads_out.clk.eq(1),
            NextValue(datar_reset, 0),
            If(datar_source.valid,
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
            source.valid.eq(datar_source.valid),
            source.status.eq(Mux(crc_error, SDCARD_STREAM_STATUS_CRCERROR, SDCARD_STREAM_STATUS_OK)),
            source.first.eq(count == 0),
            source.last.eq(count == (sink.block_length + crc_len - 1)), # 1 block + CRC
            source.drop.eq(count > (sink.block_length - 1)), # Drop CRC
            source.data.eq(datar_source.data),
            If(source.valid,
                If(source.ready,
                    datar_source.ready.eq(1),
                    NextValue(count, count + 1),
                    If(source.last,
                        sink.ready.eq(1),
                        If(sink.last,
                            NextValue(count, 0),
                            NextState("CLK8")
                        ).Else(
                            NextState("IDLE")
                        )
                    )
                ).Else(
                     self.stop.eq(1)
                )
            ),
            If(pads_in.valid & data_done & (crc_count < 16),
                NextValue(crc_count, crc_count + 1),
                If(~crc_correct,
                    NextValue(crc_error, 1),
                )
            ),
            NextValue(timeout, timeout - 1),
            If(timeout == 0,
                sink.ready.eq(1),
                NextState("TIMEOUT")
            )
        )
        fsm.act("CLK8",
            pads_out.clk.eq(1),
            If(pads_out.ready,
                NextValue(count, count + 1),
                If(count == (8-1),
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
        self.specials += SDRTristate(
            clk = ClockSignal("sys"),
            io  = pads.data,
            o   = sdpads.data.o,
            oe  = Replicate(sdpads.data.oe, len(pads.data)),
            i   = sdpads.data.i,
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
        self.add_data_i_ce(clocker, sdpads)
        for i in range(4):
            self.comb += If(~pads.dat_t[i], sdpads.data.i[i].eq(pads.dat_o[i]))

# SDCard PHY ---------------------------------------------------------------------------------------

class SDPHY(LiteXModule):
    def __init__(self, pads, device, sys_clk_freq, cmd_timeout=10e-3, data_timeout=10e-3):
        use_emulator = hasattr(pads, "cmd_t") and hasattr(pads, "dat_t")
        self.card_detect = CSRStatus() # Assume SDCard is present if no cd pin.
        self.comb += self.card_detect.status.eq(getattr(pads, "cd", 0))

        pads_data_width = len(pads.dat_t) if use_emulator else len(pads.data)
        sdpads_layout = _sdpads_layout(pads_data_width)

        data_width = Signal(2)

        self.clocker = clocker = SDPHYClocker()
        self.init    = init    = SDPHYInit(sdpads_layout)
        self.cmdw    = cmdw    = SDPHYCMDW(sdpads_layout)
        self.cmdr    = cmdr    = SDPHYCMDR(sdpads_layout, sys_clk_freq, cmd_timeout, cmdw)
        self.dataw   = dataw   = SDPHYDATAW(sdpads_layout, data_width)
        self.datar   = datar   = SDPHYDATAR(sdpads_layout, data_width, sys_clk_freq, data_timeout)

        self.settings = CSRStorage(fields=[
            CSRField("data_width", size=2, offset=0, values=[
                ("0b00", "1-bit"),
                ("0b01", "4-bit"),
                ("0b10", "8-bit"),
            ], reset=SD_PHY_SPEED_4X), # Defaults to 4x speed for retro-compatibility.
        ])

        self.comb += data_width.eq(self.settings.fields.data_width)

        self.sdpads = sdpads = Record(sdpads_layout)

        if len(sdpads.data.i) >= 8:
            self.support_8x = CSRConstant(1)

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
