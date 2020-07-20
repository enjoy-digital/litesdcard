# This file is Copyright (c) 2017-2020 Florent Kermarrec <florent@enjoy-digital.fr>
# This file is Copyright (c) 2017 Pierre-Olivier Vauboin <po@lambdaconcept.com>
# License: BSD

from functools import reduce
from operator import or_

from migen import *
from migen.genlib.resetsync import AsyncResetSynchronizer

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
]

# SDCard PHY Clocker -------------------------------------------------------------------------------

class SDPHYClocker(Module, AutoCSR):
    def __init__(self):
        self.divider = CSRStorage(8)
        self.clk     = Signal()
        self.clk2x   = Signal()
        self.ce      = Signal()

        # # #

        clks = Signal(8)
        self.sync += clks.eq(clks + 1)

        cases = {}
        cases["default"] = [
            self.clk2x.eq(ClockSignal("sys")),
            self.clk.eq(clks[0]),
        ]
        for i in range(2, 8):
            cases[2**i] = [
                self.clk2x.eq(clks[i-2]),
                self.clk.eq(clks[i-1]),
            ]
        self.comb += Case(self.divider.storage, cases)

        clk_d = Signal(2)
        self.sync += clk_d.eq(self.clk)
        self.comb += self.ce.eq(self.clk & ~clk_d)

# SDCard PHY Read ----------------------------------------------------------------------------------

@ResetInserter()
class SDPHYR(Module):
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

class SDPHYInit(Module, AutoCSR):
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

class SDPHYCMDW(Module):
    def __init__(self):
        self.pads_in  = pads_in  = stream.Endpoint(_sdpads_layout)
        self.pads_out = pads_out = stream.Endpoint(_sdpads_layout)
        self.sink     = sink     = stream.Endpoint([("data", 8)])

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
                    If(sink.last,
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

class SDPHYCMDR(Module):
    def __init__(self, sys_clk_freq, cmd_timeout, cmdw):
        self.pads_in  = pads_in  = stream.Endpoint(_sdpads_layout)
        self.pads_out = pads_out = stream.Endpoint(_sdpads_layout)
        self.sink     = sink     = stream.Endpoint([("length", 8)])
        self.source   = source   = stream.Endpoint([("data", 8), ("status", 3)])

        # # #

        timeout = Signal(32, reset=int(cmd_timeout*sys_clk_freq))
        count   = Signal(8)

        cmdr = SDPHYR(cmd=True, data_width=1, skip_start_bit=False)
        self.comb += pads_in.connect(cmdr.pads_in)
        fsm  = FSM(reset_state="IDLE")
        self.submodules += cmdr, fsm
        fsm.act("IDLE",
            NextValue(count,   0),
            NextValue(timeout, timeout.reset),
            If(sink.valid & pads_out.ready & cmdw.done,
                NextValue(cmdr.reset, 1),
                NextState("WAIT"),
            )
        )
        fsm.act("WAIT",
            pads_out.clk.eq(1),
            NextValue(cmdr.reset, 0),
            If(cmdr.source.valid,
                NextState("CMD")
            ),
            NextValue(timeout, timeout - 1),
            If(timeout == 0,
                sink.ready.eq(1),
                NextState("TIMEOUT")
            )
        )
        fsm.act("CMD",
            pads_out.clk.eq(1),
            source.valid.eq(cmdr.source.valid),
            source.status.eq(SDCARD_STREAM_STATUS_OK),
            source.last.eq(count == (sink.length - 1)),
            source.data.eq(cmdr.source.data),
            If(source.valid & source.ready,
                cmdr.source.ready.eq(1),
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
            ),
            NextValue(timeout, timeout - 1),
            If(timeout == 0,
                sink.ready.eq(1),
                NextState("TIMEOUT")
            ),
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
            source.valid.eq(1),
            source.status.eq(SDCARD_STREAM_STATUS_TIMEOUT),
            source.last.eq(1),
            If(source.valid & source.ready,
                NextState("IDLE")
            )
        )

# SDCard PHY CRC Response --------------------------------------------------------------------------

class SDPHYCRCR(Module):
    def __init__(self):
        self.pads_in  = pads_in  = stream.Endpoint(_sdpads_layout)
        self.start = Signal()
        self.valid = Signal()
        self.error = Signal()

        # # #

        crcr = SDPHYR(data=True, data_width=1, skip_start_bit=True)
        self.comb += pads_in.connect(crcr.pads_in)
        fsm = FSM(reset_state="IDLE")
        self.submodules += crcr, fsm
        fsm.act("IDLE",
            If(self.start,
                NextValue(crcr.reset, 1),
                NextState("WAIT-CHECK")
            )
        )
        fsm.act("WAIT-CHECK",
            NextValue(crcr.reset, 0),
            crcr.source.ready.eq(1),
            If(crcr.source.valid,
                self.valid.eq(crcr.source.data != 0b101),
                self.error.eq(crcr.source.data == 0b101),
                NextState("IDLE")
            )
        )

# SDCard PHY Data Write ----------------------------------------------------------------------------

class SDPHYDATAW(Module):
    def __init__(self):
        self.pads_in  = pads_in  = stream.Endpoint(_sdpads_layout)
        self.pads_out = pads_out = stream.Endpoint(_sdpads_layout)
        self.sink     = sink     = stream.Endpoint([("data", 8)])

        # # #

        count = Signal(8)

        crc = SDPHYCRCR() # FIXME: Report valid/errors to software.
        fsm = FSM(reset_state="IDLE")
        self.submodules += crc, fsm
        fsm.act("IDLE",
            NextValue(count, 0),
            If(sink.valid & pads_out.ready,
                NextState("START")
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
                crc.start.eq(1),
                NextState("RESPONSE")
            )
        )
        fsm.act("RESPONSE",
            pads_out.clk.eq(1),
            If(pads_out.ready,
                If(pads_in.data.i[0],
                    sink.ready.eq(1),
                    NextState("IDLE")
                )
            )
        )

# SDCard PHY Data Read -----------------------------------------------------------------------------

class SDPHYDATAR(Module):
    def __init__(self, sys_clk_freq, data_timeout):
        self.pads_in  = pads_in  = stream.Endpoint(_sdpads_layout)
        self.pads_out = pads_out = stream.Endpoint(_sdpads_layout)
        self.sink     = sink     = stream.Endpoint([("block_length", 10)])
        self.source   = source   = stream.Endpoint([("data", 8), ("status", 3)])

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
                If(pads_out.ready,
                    NextValue(timeout, timeout.reset),
                    NextValue(count, 0),
                    NextValue(datar.reset, 1),
                    NextState("WAIT")
                )
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
            source.last.eq(count == (sink.block_length + 8 - 1)), # 1 block + 64-bit CRC
            source.data.eq(datar.source.data),
            If(source.valid & source.ready,
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
            If(source.valid & source.ready,
                NextState("IDLE")
            )
        )

# SDCard PHY IO ------------------------------------------------------------------------------------

class SDPHYIOGen(Module):
    def __init__(self, clocker, sdpads, pads, register_clk=False):
        # Rst
        if hasattr(sdpads, "rst"):
            self.comb += pads.rst.eq(0)

        # Clk
        self.clock_domains.cd_sd = ClockDomain()
        self.comb += self.cd_sd.clk.eq(clocker.clk)
        sdpads_clk = Signal()
        self.sync.sd += sdpads_clk.eq(sdpads.clk)
        self.specials += SDROutput(
            clk = clocker.clk2x,
            i   = (sdpads_clk if register_clk else sdpads.clk) & ~clocker.clk,
            o   = pads.clk
        )

        # Cmd
        self.specials += SDRTristate(
            clk = clocker.clk,
            io  = pads.cmd,
            o   = sdpads.cmd.o,
            oe  = sdpads.cmd.oe,
            i   = sdpads.cmd.i,
        )

        # Data
        for i in range(4):
            self.specials += SDRTristate(
                clk = clocker.clk,
                io  = pads.data[i],
                o   = sdpads.data.o[i],
                oe  = sdpads.data.oe,
                i   = sdpads.data.i[i],
            )

# SDCard PHY Emulator ------------------------------------------------------------------------------

class SDPHYIOEmulator(Module):
    def __init__(self, clocker, sdpads, pads, register_clk=False):
        # Clk
        self.comb += If(sdpads.clk, pads.clk.eq(~clocker.clk))

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
        for i in range(4):
            self.comb += If(~pads.dat_t[i], sdpads.data.i[i].eq(pads.dat_o[i]))

# SDCard PHY ---------------------------------------------------------------------------------------

class SDPHY(Module, AutoCSR):
    def __init__(self, pads, device, sys_clk_freq, cmd_timeout=5e-3, data_timeout=5e-3):
        use_emulator = hasattr(pads, "cmd_t") and hasattr(pads, "dat_t")
        self.card_detect = CSRStatus() # Assume SDCard is present if no cd pin.
        self.comb += self.card_detect.status.eq(getattr(pads, "cd", 0))

        self.submodules.clocker = clocker = SDPHYClocker()
        self.submodules.init    = init    = SDPHYInit()
        self.submodules.cmdw    = cmdw    = SDPHYCMDW()
        self.submodules.cmdr    = cmdr    = SDPHYCMDR(sys_clk_freq, cmd_timeout, cmdw)
        self.submodules.dataw   = dataw   = SDPHYDATAW()
        self.submodules.datar   = datar   = SDPHYDATAR(sys_clk_freq, data_timeout)

        # # #

        self.sdpads = sdpads = Record(_sdpads_layout)

        # IOs
        sdphy_io_cls = SDPHYIOEmulator if use_emulator else SDPHYIOGen
        self.submodules.io = sdphy_io_cls(clocker, sdpads, pads, register_clk="LFE5" in device)

        # Connect pads_out of submodules to physical pads ----------------------------------------
        self.comb += [
            sdpads.clk.eq(    reduce(or_, [m.pads_out.clk     for m in [init, cmdw, cmdr, dataw, datar]])),
            sdpads.cmd.oe.eq( reduce(or_, [m.pads_out.cmd.oe  for m in [init, cmdw, cmdr, dataw, datar]])),
            sdpads.cmd.o.eq(  reduce(or_, [m.pads_out.cmd.o   for m in [init, cmdw, cmdr, dataw, datar]])),
            sdpads.data.oe.eq(reduce(or_, [m.pads_out.data.oe for m in [init, cmdw, cmdr, dataw, datar]])),
            sdpads.data.o.eq( reduce(or_, [m.pads_out.data.o  for m in [init, cmdw, cmdr, dataw, datar]])),
        ]
        for m in [init, cmdw, cmdr, dataw, datar]:
            self.comb += m.pads_out.ready.eq(self.clocker.ce)

        # Connect physical pads to pads_in of submodules -------------------------------------------
        for m in [init, cmdw, cmdr, dataw, datar]:
            self.comb += m.pads_in.valid.eq(self.clocker.ce)
            self.comb += m.pads_in.cmd.i.eq(sdpads.cmd.i)
            self.comb += m.pads_in.data.i.eq(sdpads.data.i)
