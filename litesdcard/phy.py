# This file is Copyright (c) 2017-2020 Florent Kermarrec <florent@enjoy-digital.fr>
# This file is Copyright (c) 2017 Pierre-Olivier Vauboin <po@lambdaconcept.com>
# License: BSD

from migen import *
from migen.genlib.cdc import MultiReg

from litex.build.io import SDRInput, SDROutput

from litex.soc.interconnect import stream
from litex.soc.interconnect.csr import *

from litesdcard.common import *

# Pads ---------------------------------------------------------------------------------------------

def _sdpads():
    sdpads = Record([
        ("clk", 1, DIR_M_TO_S),
        ("cmd", [
            ("i",  1, DIR_S_TO_M),
            ("o",  1, DIR_M_TO_S),
            ("oe", 1, DIR_M_TO_S)
        ]),
        ("data", [
            ("i",  4, DIR_S_TO_M),
            ("o",  4, DIR_M_TO_S),
            ("oe", 1, DIR_M_TO_S)
        ]),
    ])
    sdpads.cmd.o.reset   = 0b1
    sdpads.cmd.oe.reset  = 0b1
    sdpads.data.o.reset  = 0b1111
    sdpads.data.oe.reset = 0b1111
    return sdpads

# Configuration ------------------------------------------------------------------------------------

class SDPHYCFG(Module, AutoCSR):
    def __init__(self):
        self.timeout   = Signal(32)
        self.blocksize = Signal(16)

# SDCard PHY Command Write -------------------------------------------------------------------------

class SDPHYCMDW(Module):
    def __init__(self):
        self.pads = pads = _sdpads()
        self.sink = sink = stream.Endpoint([("data", 8)])

        # # #

        initialized = Signal() # FIXME: should be controlled by software.
        count       = Signal(8)
        fsm = FSM(reset_state="IDLE")
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
            pads.clk.eq(1),
            pads.data.oe.eq(1),
            pads.data.o.eq(0xf),
            NextValue(count, count + 1),
            If(count == (80-1),
                NextValue(initialized, 1),
                NextState("IDLE")
            )
        )
        fsm.act("WRITE",
            pads.clk.eq(1),
            Case(count, {i: pads.cmd.o.eq(sink.data[8-1-i]) for i in range(8)}),
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
            pads.clk.eq(1),
            NextValue(count, count + 1),
            If(count == (8-1),
                sink.ready.eq(1),
                NextState("IDLE")
            )
        )

# SDCard PHY Read ----------------------------------------------------------------------------------

@ResetInserter()
class SDPHYR(Module):
    def __init__(self, idata, skip_start_bit=False):
        self.source = stream.Endpoint([("data", 8)])

        # # #

        # Xfer starts when data == 0
        start = Signal()
        run   = Signal()
        self.comb += start.eq(idata == 0)
        self.sync += run.eq(start | run)

        # Convert data to 8-bit stream
        converter = stream.Converter(len(idata), 8, reverse=True)
        buf       = stream.Buffer([("data", 8)])
        self.submodules += converter, buf
        self.comb += [
            converter.sink.valid.eq(run if skip_start_bit else (start | run)),
            converter.sink.data.eq(idata),
            converter.source.connect(buf.sink),
            buf.source.connect(self.source)
        ]

# SDCard PHY Command Read --------------------------------------------------------------------------

class SDPHYCMDR(Module):
    def __init__(self, cfg):
        self.pads   = pads   = _sdpads()
        self.sink   = sink   = stream.Endpoint([("data", 8)])
        self.source = source = stream.Endpoint([("data", 8), ("status", 3)])

        # # #

        timeout = Signal(32)
        count   = Signal(8)

        cmdr = SDPHYR(pads.cmd.i, skip_start_bit=False)
        fsm  = FSM(reset_state="IDLE")
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
            pads.cmd.oe.eq(0),
            pads.clk.eq(1),
            NextValue(cmdr.reset, 0),
            NextValue(timeout, timeout + 1),
            If(cmdr.source.valid,
                NextState("CMD")
            ).Elif(timeout > cfg.timeout,
                NextState("TIMEOUT")
            )
        )
        fsm.act("CMD",
            pads.cmd.oe.eq(0),
            pads.clk.eq(1),
            source.valid.eq(cmdr.source.valid),
            source.status.eq(SDCARD_STREAM_STATUS_OK),
            source.last.eq(count == sink.data),
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
            pads.clk.eq(1),
            NextValue(count, count + 1),
            If(count == 7,
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
    def __init__(self, idata):
        self.start = Signal()
        self.valid = Signal()
        self.error = Signal()

        # # #

        crcr = SDPHYR(idata, skip_start_bit=True)
        fsm  = FSM(reset_state="IDLE")
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
        self.pads = pads = _sdpads()
        self.sink = sink = stream.Endpoint([("data", 8)])

        # # #

        wrstarted = Signal()
        count     = Signal(8)

        crc = SDPHYCRCR(pads.data.i[0]) # FIXME: Report valid/errors to software.
        fsm = fsm = FSM(reset_state="IDLE")
        self.submodules += crc, fsm
        fsm.act("IDLE",
            If(sink.valid,
                pads.clk.eq(1),
                pads.data.oe.eq(1),
                If(wrstarted,
                    pads.data.o.eq(sink.data[4:8]),
                    NextState("DATA")
                ).Else(
                    pads.data.o.eq(0),
                    NextState("START")
                )
            )
        )
        fsm.act("START",
            pads.clk.eq(1),
            pads.data.oe.eq(1),
            pads.data.o.eq(sink.data[4:8]),
            NextValue(wrstarted, 1),
            NextState("DATA")
        )
        fsm.act("DATA",
            pads.clk.eq(1),
            pads.data.oe.eq(1),
            pads.data.o.eq(sink.data[0:4]),
            If(sink.last,
                NextState("STOP")
            ).Else(
                sink.ready.eq(1),
                NextState("IDLE")
            )
        )
        fsm.act("STOP",
            pads.clk.eq(1),
            pads.data.oe.eq(1),
            pads.data.o.eq(0xf),
            NextValue(wrstarted, 0),
            crc.start.eq(1),
            NextState("RESPONSE")
        )
        fsm.act("RESPONSE",
            pads.clk.eq(1),
            pads.data.oe.eq(0),
            If(count < 16,
                NextValue(count, count + 1),
            ).Else(
                # wait while busy
                If(pads.data.i[0],
                    NextValue(count, 0),
                    sink.ready.eq(1),
                    NextState("IDLE")
                )
            )
        )

# SDCard PHY Data Read -----------------------------------------------------------------------------

class SDPHYDATAR(Module):
    def __init__(self, cfg):
        self.pads   = pads   = _sdpads()
        self.sink   = sink   = stream.Endpoint([("data", 8)])
        self.source = source = stream.Endpoint([("data", 8), ("status", 3)])

        # # #

        timeout = Signal(32)
        count   = Signal(10)

        datar = SDPHYR(pads.data.i, skip_start_bit=True)
        fsm   = FSM(reset_state="IDLE")
        self.submodules += datar, fsm
        fsm.act("IDLE",
            NextValue(count, 0),
            pads.data.oe.eq(0),
            pads.clk.eq(1),
            If(sink.valid,
                NextValue(timeout, 0),
                NextValue(count, 0),
                NextValue(datar.reset, 1),
                NextState("WAIT")
            )
        )
        fsm.act("WAIT",
            pads.data.oe.eq(0),
            pads.clk.eq(1),
            NextValue(datar.reset, 0),
            NextValue(timeout, timeout + 1),
            If(datar.source.valid,
                NextState("DATA")
            ).Elif(timeout > cfg.timeout,
                NextState("TIMEOUT")
            )
        )
        fsm.act("DATA",
            pads.data.oe.eq(0),
            pads.clk.eq(1),
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
            pads.clk.eq(1),
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
        self.comb += ClockSignal("sd").eq(ClockSignal())
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
        self.sink   = sink   = stream.Endpoint([("data", 8), ("cmd_data_n", 1), ("rd_wr_n", 1)])
        self.source = source = stream.Endpoint([("data", 8), ("status", 3)])
        self.card_detect = CSRStatus()
        self.comb += self.card_detect.status.eq(getattr(pads, "cd", 0)) # Assume SDCard is present if no cd pin.

        # # #

        self.sdpads = sdpads = _sdpads()

        # IOs
        if hasattr(pads, "cmd_t") and hasattr(pads, "dat_t"):
            self.submodules.io = SDPHYIOEmulator(sdpads, pads)
        else:
            self.submodules.io = SDPHYIOGen(sdpads, pads)

        # PHY submodules
        self.submodules.cfg   = cfg   = ClockDomainsRenamer("sd")(SDPHYCFG())
        self.submodules.cmdw  = cmdw  = ClockDomainsRenamer("sd")(SDPHYCMDW())
        self.submodules.cmdr  = cmdr  = ClockDomainsRenamer("sd")(SDPHYCMDR(cfg))
        self.submodules.dataw = dataw = ClockDomainsRenamer("sd")(SDPHYDATAW())
        self.submodules.datar = datar = ClockDomainsRenamer("sd")(SDPHYDATAR(cfg))

        self.comb += \
            If(sink.valid,
                # Command mode
                If(sink.cmd_data_n,
                    # Write command
                    If(~sink.rd_wr_n,
                        sink.connect(cmdw.sink, omit=set(["cmd_data_n", "rd_wr_n"])),
                        cmdw.pads.connect(sdpads)
                    # Read command
                    ).Else(
                        sink.connect(cmdr.sink, omit=set(["cmd_data_n", "rd_wr_n"])),
                        cmdr.pads.connect(sdpads),
                        cmdr.source.connect(source)
                    )
                # Data mode
                ).Else(
                    # Write data
                    If(~sink.rd_wr_n,
                        sink.connect(dataw.sink, omit=set(["cmd_data_n", "rd_wr_n"])),
                        dataw.pads.connect(sdpads)
                    # Read data
                    ).Else(
                        sink.connect(datar.sink, omit=set(["cmd_data_n", "rd_wr_n"])),
                        datar.pads.connect(sdpads),
                        datar.source.connect(source)
                    )
                )
            )
