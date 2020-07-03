# This file is Copyright (c) 2017-2020 Florent Kermarrec <florent@enjoy-digital.fr>
# This file is Copyright (c) 2017 Pierre-Olivier Vauboin <po@lambdaconcept.com>
# License: BSD

from functools import reduce
from operator import or_

from migen import *
from migen.genlib.cdc import MultiReg

from litex.build.io import SDRInput, SDROutput

from litex.soc.interconnect import stream
from litex.soc.interconnect.csr import *

from litesdcard.common import *

# Pads ---------------------------------------------------------------------------------------------

_sdpads_out_layout = [
    ("clk", 1),
    ("cmd", [
        ("o",  1),
        ("oe", 1)
    ]),
    ("data", [
        ("o",  4),
        ("oe", 1)
    ]),
]

_sdpads_in_layout = [
    ("cmd", [
        ("i",  1)
    ]),
    ("data", [
        ("i",  4)
    ]),
]

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

# Configuration ------------------------------------------------------------------------------------

class SDPHYCFG(Module):
    def __init__(self):
        self.timeout   = Signal(32)
        self.blocksize = Signal(16)

# SDCard PHY Command Write -------------------------------------------------------------------------

class SDPHYCMDW(Module):
    def __init__(self):
        self.pads_in  = pads_in  = stream.Endpoint(_sdpads_in_layout)
        self.pads_out = pads_out = stream.Endpoint(_sdpads_out_layout)
        self.sink     = sink     = stream.Endpoint([("data", 8)])

        # # #

        initialized = Signal() # FIXME: should be controlled by software.
        count       = Signal(8)
        fsm = FSM(reset_state="IDLE")
        fsm = ClockDomainsRenamer("sd")(fsm)
        self.submodules += fsm
        fsm.act("IDLE",
            NextValue(count, 0),
            If(sink.valid,
                If(~initialized,
                    NextState("INIT")
                ).Else(
                    NextState("WRITE")
                )
            )
        )
        fsm.act("INIT",
            pads_out.clk.eq(1),
            pads_out.cmd.oe.eq(1),
            pads_out.cmd.o.eq(1),
            pads_out.data.oe.eq(1),
            pads_out.data.o.eq(0b1111),
            NextValue(count, count + 1),
            If(count == (80-1),
                NextValue(initialized, 1),
                NextState("IDLE")
            )
        )
        fsm.act("WRITE",
            pads_out.clk.eq(1),
            pads_out.cmd.oe.eq(1),
            Case(count, {i: pads_out.cmd.o.eq(sink.data[8-1-i]) for i in range(8)}),
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
        fsm.act("CLK8",
            pads_out.clk.eq(1),
            pads_out.cmd.oe.eq(1),
            pads_out.cmd.o.eq(1),
            NextValue(count, count + 1),
            If(count == (8-1),
                sink.ready.eq(1),
                NextState("IDLE")
            )
        )

# SDCard PHY Read ----------------------------------------------------------------------------------

@ResetInserter()
class SDPHYR(Module):
    def __init__(self, cmd=False, data=False, data_width=1, skip_start_bit=False):
        assert cmd or data
        self.pads_in  = pads_in = stream.Endpoint(_sdpads_in_layout)
        self.source   = source  = stream.Endpoint([("data", 8)])

        # # #

        pads_in_data = pads_in.cmd.i[:data_width] if cmd else pads_in.data.i[:data_width]

        # Xfer starts when data == 0
        start = Signal()
        run   = Signal()
        self.comb += start.eq(pads_in_data == 0)
        self.sync.sd += run.eq(start | run)

        # Convert data to 8-bit stream
        converter = stream.Converter(data_width, 8, reverse=True)
        converter = ClockDomainsRenamer("sd")(converter)
        buf       = stream.Buffer([("data", 8)])
        buf       = ClockDomainsRenamer("sd")(buf)
        self.submodules += converter, buf
        self.comb += [
            converter.sink.valid.eq(run if skip_start_bit else (start | run)),
            converter.sink.data.eq(pads_in_data),
            converter.source.connect(buf.sink),
            buf.source.connect(source)
        ]

# SDCard PHY Command Read --------------------------------------------------------------------------

class SDPHYCMDR(Module):
    def __init__(self, cfg):
        self.pads_in  = pads_in  = stream.Endpoint(_sdpads_in_layout)
        self.pads_out = pads_out = stream.Endpoint(_sdpads_out_layout)
        self.sink    = sink   = stream.Endpoint([("length", 8)])
        self.source  = source = stream.Endpoint([("data", 8), ("status", 3)])

        # # #

        timeout = Signal(32)
        count   = Signal(8)

        cmdr = SDPHYR(cmd=True, data_width=1, skip_start_bit=False)
        cmdr = ClockDomainsRenamer("sd")(cmdr)
        self.comb += pads_in.connect(cmdr.pads_in)
        fsm  = FSM(reset_state="IDLE")
        fsm  = ClockDomainsRenamer("sd")(fsm)
        self.submodules += cmdr, fsm
        fsm.act("IDLE",
            NextValue(count,   0),
            NextValue(timeout, 0),
            If(sink.valid,
                NextValue(cmdr.reset, 1),
                NextState("WAIT"),
            )
        )
        fsm.act("WAIT",
            pads_out.clk.eq(1),
            NextValue(cmdr.reset, 0),
            NextValue(timeout, timeout + 1),
            If(cmdr.source.valid,
                NextState("CMD")
            ).Elif(timeout > cfg.timeout,
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
                    If(sink.last,
                        NextValue(count, 0),
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
            NextValue(count, count + 1),
            If(count == (8-1),
                sink.ready.eq(1),
                NextState("IDLE")
            )
        )
        fsm.act("TIMEOUT",
            source.valid.eq(1),
            source.status.eq(SDCARD_STREAM_STATUS_TIMEOUT),
            source.last.eq(1),
            If(source.valid & source.ready,
                sink.ready.eq(1),
                NextState("IDLE")
            )
        )

# SDCard PHY CRC Response --------------------------------------------------------------------------

class SDPHYCRCR(Module):
    def __init__(self):
        self.pads_in  = pads_in  = stream.Endpoint(_sdpads_in_layout)
        self.start = Signal()
        self.valid = Signal()
        self.error = Signal()

        # # #

        crcr = SDPHYR(data=True, data_width=1, skip_start_bit=True)
        crcr = ClockDomainsRenamer("sd")(crcr)
        self.comb += pads_in.connect(crcr.pads_in)
        fsm = FSM(reset_state="IDLE")
        fsm = ClockDomainsRenamer("sd")(fsm)
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
        self.pads_in  = pads_in  = stream.Endpoint(_sdpads_in_layout)
        self.pads_out = pads_out = stream.Endpoint(_sdpads_out_layout)
        self.sink = sink = stream.Endpoint([("data", 8)])

        # # #

        wrstarted = Signal()
        count     = Signal(8)

        crc = SDPHYCRCR() # FIXME: Report valid/errors to software.
        crc = ClockDomainsRenamer("sd")(crc)
        self.comb += pads_in.connect(crc.pads_in)
        fsm = FSM(reset_state="IDLE")
        fsm = ClockDomainsRenamer("sd")(fsm)
        self.submodules += crc, fsm
        fsm.act("IDLE",
            If(sink.valid,
                pads_out.clk.eq(1),
                pads_out.data.oe.eq(1),
                If(wrstarted,
                    pads_out.data.o.eq(sink.data[4:8]),
                    NextState("DATA")
                ).Else(
                    pads_out.data.o.eq(0),
                    NextState("START")
                )
            )
        )
        fsm.act("START",
            pads_out.clk.eq(1),
            pads_out.data.oe.eq(1),
            pads_out.data.o.eq(sink.data[4:8]),
            NextValue(wrstarted, 1),
            NextState("DATA")
        )
        fsm.act("DATA",
            pads_out.clk.eq(1),
            pads_out.data.oe.eq(1),
            pads_out.data.o.eq(sink.data[0:4]),
            If(sink.last,
                NextState("STOP")
            ).Else(
                sink.ready.eq(1),
                NextState("IDLE")
            )
        )
        fsm.act("STOP",
            pads_out.clk.eq(1),
            pads_out.data.oe.eq(1),
            pads_out.data.o.eq(0b1111),
            NextValue(wrstarted, 0),
            crc.start.eq(1),
            NextState("RESPONSE")
        )
        fsm.act("RESPONSE",
            pads_out.clk.eq(1),
            If(count < 16,
                NextValue(count, count + 1),
            ).Else(
                # wait while busy
                If(pads_in.data.i[0],
                    NextValue(count, 0),
                    sink.ready.eq(1),
                    NextState("IDLE")
                )
            )
        )

# SDCard PHY Data Read -----------------------------------------------------------------------------

class SDPHYDATAR(Module):
    def __init__(self, cfg):
        self.pads_in  = pads_in  = stream.Endpoint(_sdpads_in_layout)
        self.pads_out = pads_out = stream.Endpoint(_sdpads_out_layout)
        self.sink   = sink   = stream.Endpoint([("length", 8)])
        self.source = source = stream.Endpoint([("data", 8), ("status", 3)])

        # # #

        timeout = Signal(32)
        count   = Signal(10)

        datar = SDPHYR(data=True, data_width=4, skip_start_bit=True)
        datar = ClockDomainsRenamer("sd")(datar)
        self.comb += pads_in.connect(datar.pads_in)
        fsm = FSM(reset_state="IDLE")
        fsm = ClockDomainsRenamer("sd")(fsm)
        self.submodules += datar, fsm
        fsm.act("IDLE",
            NextValue(count, 0),
            If(sink.valid,
                pads_out.clk.eq(1),
                NextValue(timeout, 0),
                NextValue(count, 0),
                NextValue(datar.reset, 1),
                NextState("WAIT")
            )
        )
        fsm.act("WAIT",
            pads_out.clk.eq(1),
            NextValue(datar.reset, 0),
            NextValue(timeout, timeout + 1),
            If(datar.source.valid,
                NextState("DATA")
            ).Elif(timeout > cfg.timeout,
                NextState("TIMEOUT")
            )
        )
        fsm.act("DATA",
            pads_out.clk.eq(1),
            source.valid.eq(datar.source.valid),
            source.status.eq(SDCARD_STREAM_STATUS_OK),
            source.last.eq(count == (cfg.blocksize + 8 - 1)), # 1 block + 64-bit CRC
            source.data.eq(datar.source.data),
            If(source.valid & source.ready,
                datar.source.ready.eq(1),
                NextValue(count, count + 1),
                If(source.last,
                    If(sink.last,
                        NextValue(count, 0),
                        NextState("CLK40")
                    ).Else(
                        sink.ready.eq(1),
                        NextState("IDLE")
                    )
                )
            )
        )
        fsm.act("CLK40",
            pads_out.clk.eq(1),
            NextValue(count, count + 1),
            If(count == (40-1),
                sink.ready.eq(1),
                NextState("IDLE")
            )
        )
        fsm.act("TIMEOUT",
            source.valid.eq(1),
            source.status.eq(SDCARD_STREAM_STATUS_TIMEOUT),
            source.last.eq(1),
            If(source.valid & source.ready,
                sink.ready.eq(1),
                NextState("IDLE")
            )
        )

# SDCard PHY IO ------------------------------------------------------------------------------------

class SDPHYIOGen(Module):
    def __init__(self, sdpads, pads):
        # Data tristate
        self.data_t = TSTriple(4)
        self.specials += self.data_t.get_tristate(pads.data)

        # Cmd tristate
        self.cmd_t = TSTriple()
        self.specials += self.cmd_t.get_tristate(pads.cmd)

        # Clk domain feedback
        if hasattr(pads, "clkfb"):
            raise NotImplementedError

        # Clk output
        # FIXME: use DDR output for high clk freq but requires low latency or modification to the core.
        sdpads_clk = Signal()
        self.sync.sd += sdpads_clk.eq(sdpads.clk)
        self.comb += If(sdpads_clk, pads.clk.eq(~ClockSignal("sd")))

        # Cmd output
        self.sync.sd += self.cmd_t.oe.eq(sdpads.cmd.oe)
        self.sync.sd += self.cmd_t.o.eq(sdpads.cmd.o)

        # Cmd input
        self.specials += SDRInput(self.cmd_t.i, sdpads.cmd.i, ClockSignal("sd"))

        # Data output
        self.sync += self.data_t.oe.eq(sdpads.data.oe)
        self.sync += self.data_t.o.eq(sdpads.data.o)

        # Data input
        for i in range(4):
            self.specials += SDRInput(self.data_t.i[i], sdpads.data.i[i], ClockSignal("sd"))

# SDCard PHY Emulator ------------------------------------------------------------------------------

class SDPHYIOEmulator(Module):
    def __init__(self, sdpads, pads):
        self.clock_domains.cd_sd = ClockDomain()
        clk_divider = Signal(16)
        self.sync += clk_divider.eq(clk_divider + 1)
        self.comb += ClockSignal("sd").eq(clk_divider[3])
        self.comb += ResetSignal("sd").eq(ResetSignal())

        # Clk
        self.comb += If(sdpads.clk, pads.clk.eq(~ClockSignal("sd")))

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
    def __init__(self, pads, device):
        self.card_detect = CSRStatus() # Assume SDCard is present if no cd pin.
        self.comb += self.card_detect.status.eq(getattr(pads, "cd", 0))

        self.submodules.cfg   = cfg   = SDPHYCFG()
        self.submodules.cmdw  = cmdw  = SDPHYCMDW()
        self.submodules.cmdr  = cmdr  = SDPHYCMDR(cfg)
        self.submodules.dataw = dataw = SDPHYDATAW()
        self.submodules.datar = datar = SDPHYDATAR(cfg)

        # # #

        self.sdpads = sdpads = Record(_sdpads_layout)

        # IOs
        if hasattr(pads, "cmd_t") and hasattr(pads, "dat_t"):
            self.submodules.io = SDPHYIOEmulator(sdpads, pads)
        else:
            self.submodules.io = SDPHYIOGen(sdpads, pads)

        # Connect pads_out of submodules to physical pads ----------------------------------------
        self.comb += [
            sdpads.clk.eq(    reduce(or_, [m.pads_out.clk     for m in [cmdw, cmdr, dataw, datar]])),
            sdpads.cmd.oe.eq( reduce(or_, [m.pads_out.cmd.oe  for m in [cmdw, cmdr, dataw, datar]])),
            sdpads.cmd.o.eq(  reduce(or_, [m.pads_out.cmd.o   for m in [cmdw, cmdr, dataw, datar]])),
            sdpads.data.oe.eq(reduce(or_, [m.pads_out.data.oe for m in [cmdw, cmdr, dataw, datar]])),
            sdpads.data.o.eq( reduce(or_, [m.pads_out.data.o  for m in [cmdw, cmdr, dataw, datar]])),
        ]

        # Connect physical pads to pads_in of submodules -------------------------------------------
        for m in [cmdw, cmdr, dataw, datar]:
            self.comb += m.pads_in.cmd.i.eq(sdpads.cmd.i)
            self.comb += m.pads_in.data.i.eq(sdpads.data.i)
