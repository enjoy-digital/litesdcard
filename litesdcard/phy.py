# This file is Copyright (c) 2017-2018 Florent Kermarrec <florent@enjoy-digital.fr>
# This file is Copyright (c) 2017 Pierre-Olivier Vauboin <po@lambdaconcept.com>
# License: BSD

from migen import *
from migen.genlib.cdc import MultiReg, PulseSynchronizer

from litex.build.io import SDRInput, SDROutput

from litex.soc.interconnect import stream
from litex.soc.interconnect.csr import *

from litesdcard.common import *


def _sdpads():
    sdpads = Record([
        ("data", [
            ("i",  4, DIR_S_TO_M),
            ("o",  4, DIR_M_TO_S),
            ("oe", 1, DIR_M_TO_S)
        ]),
        ("cmd", [
            ("i",  1, DIR_S_TO_M),
            ("o",  1, DIR_M_TO_S),
            ("oe", 1, DIR_M_TO_S)
        ]),
        ("clk", 1, DIR_M_TO_S)
    ])
    sdpads.cmd.o.reset = 1
    sdpads.cmd.oe.reset = 1
    sdpads.data.o.reset = 0b1111
    sdpads.data.oe.reset = 0b1111
    return sdpads


class SDPHYCFG(Module, AutoCSR):
    def __init__(self):
        self.datatimeout = Signal(32)
        self.cmdtimeout = Signal(32)
        self.blocksize = Signal(16)


@ResetInserter()
class SDPHYRFB(Module):
    def __init__(self, idata, skip_start_bit=False):
        self.source = source = stream.Endpoint([("data", 8)])

        # # #

        n = 8//len(idata)
        sel = Signal(max=n)
        data = Signal(8)

        self.submodules.fsm = fsm = ClockDomainsRenamer("sd_fb")(FSM(reset_state="IDLE"))

        fsm.act("IDLE",
            If(idata == 0,
                NextValue(data, 0),
                If(skip_start_bit,
                    NextValue(sel, 0)
                ).Else(
                    NextValue(sel, 1)
                ),
                NextState("READ")
            )
        )

        fsm.act("READ",
            If(sel == (n-1),
                source.valid.eq(1),
                source.data.eq(Cat(idata, data)),
                NextValue(sel, 0)
            ).Else(
                NextValue(data, Cat(idata, data)),
                NextValue(sel, sel + 1)
            )
        )


class SDPHYCMDR(Module):
    def __init__(self, cfg):
        self.pads = pads = _sdpads()
        self.sink = sink = stream.Endpoint([("data", 8)])
        self.source = source = stream.Endpoint([("data", 8), ("status", 3)])

        # # #

        cmdrfb_reset = Signal()

        self.submodules.cmdrfb = SDPHYRFB(pads.cmd.i, False)
        self.submodules.fifo = ClockDomainsRenamer({"write": "sd_fb", "read": "sd"})(
            stream.AsyncFIFO(self.cmdrfb.source.description, 4)
        )
        self.comb += self.cmdrfb.source.connect(self.fifo.sink)

        ctimeout = Signal(32)

        cread = Signal(10)
        ctoread = Signal(10)
        cnt = Signal(8)

        self.submodules.fsm = fsm = ClockDomainsRenamer("sd")(FSM(reset_state="IDLE"))

        fsm.act("IDLE",
            If(sink.valid,
                NextValue(ctimeout, 0),
                NextValue(cread, 0),
                NextValue(ctoread, sink.data),
                NextState("CMD_READSTART")
            ).Else(
                cmdrfb_reset.eq(1),
                self.fifo.source.ready.eq(1),
            )
        )
        self.specials += MultiReg(cmdrfb_reset, self.cmdrfb.reset, "sd_fb")

        fsm.act("CMD_READSTART",
            pads.cmd.oe.eq(0),
            pads.clk.eq(1),
            NextValue(ctimeout, ctimeout + 1),
            If(self.fifo.source.valid,
                NextState("CMD_READ")
            ).Elif(ctimeout > cfg.cmdtimeout,
                NextState("TIMEOUT")
            )
        )

        fsm.act("CMD_READ",
            pads.cmd.oe.eq(0),
            pads.clk.eq(1),
            source.valid.eq(self.fifo.source.valid),
            source.data.eq(self.fifo.source.data),
            source.status.eq(SDCARD_STREAM_STATUS_OK),
            source.last.eq(cread == ctoread),
            self.fifo.source.ready.eq(source.ready),
            If(source.valid & source.ready,
                NextValue(cread, cread + 1),
                If(cread == ctoread,
                    If(sink.last,
                        NextState("CMD_CLK8")
                    ).Else(
                        sink.ready.eq(1),
                        NextState("IDLE")
                    )
                )
            )
        )

        fsm.act("CMD_CLK8",
            If(cnt < 7,
                NextValue(cnt, cnt + 1),
                pads.clk.eq(1)
            ).Else(
                NextValue(cnt, 0),
                sink.ready.eq(1),
                NextState("IDLE")
            )
        )

        fsm.act("TIMEOUT",
            source.valid.eq(1),
            source.data.eq(0),
            source.status.eq(SDCARD_STREAM_STATUS_TIMEOUT),
            source.last.eq(1),
            If(source.valid & source.ready,
                sink.ready.eq(1),
                NextState("IDLE")
            )
        )


class SDPHYCMDW(Module):
    def __init__(self):
        self.pads = pads = _sdpads()
        self.sink = sink = stream.Endpoint([("data", 8)])

        # # #

        isinit = Signal()
        cntinit = Signal(8)
        cnt = Signal(8)
        wrsel = Signal(3)
        wrtmpdata = Signal(8)

        wrcases = {} # For command write
        for i in range(8):
            wrcases[i] =  pads.cmd.o.eq(wrtmpdata[7-i])

        self.submodules.fsm = fsm = ClockDomainsRenamer("sd")(FSM(reset_state="IDLE"))

        fsm.act("IDLE",
            If(sink.valid,
                If(~isinit,
                    NextState("INIT")
                ).Else(
                    pads.clk.eq(1),
                    pads.cmd.o.eq(sink.data[7]),
                    NextValue(wrtmpdata, sink.data),
                    NextValue(wrsel, 1),
                    NextState("CMD_WRITE")
                )
            )
        )

        fsm.act("INIT",
            # Initialize sdcard with 80 clock cycles
            pads.clk.eq(1),
            If(cntinit < 80,
                NextValue(cntinit, cntinit + 1),
                NextValue(pads.data.oe, 1),
                NextValue(pads.data.o, 0xf)
            ).Else(
                NextValue(cntinit, 0),
                NextValue(isinit, 1),
                NextValue(pads.data.oe, 0),
                NextState("IDLE")
            )
        )

        fsm.act("CMD_WRITE",
            Case(wrsel, wrcases),
            NextValue(wrsel, wrsel + 1),
            If(wrsel == 0,
                If(sink.last,
                    pads.clk.eq(1),
                    NextState("CMD_CLK8")
                ).Else(
                    sink.ready.eq(1),
                    NextState("IDLE")
                )
            ).Else(
                pads.clk.eq(1)
            )
        )

        fsm.act("CMD_CLK8",
            If(cnt < 7,
                NextValue(cnt, cnt + 1),
                pads.clk.eq(1)
            ).Else(
                NextValue(cnt, 0),
                sink.ready.eq(1),
                NextState("IDLE")
            )
        )


class SDPHYDATAR(Module):
    def __init__(self, cfg):
        self.pads = pads = _sdpads()
        self.sink = sink = stream.Endpoint([("data", 8)])
        self.source = source = stream.Endpoint([("data", 8), ("status", 3)])

        # # #

        datarfb_reset = Signal()

        self.submodules.datarfb = SDPHYRFB(pads.data.i, True)
        self.submodules.cdc = ClockDomainsRenamer({"write": "sd_fb", "read": "sd"})(
            stream.AsyncFIFO(self.datarfb.source.description, 4)
        )
        self.submodules.buffer = ClockDomainsRenamer("sd")(stream.Buffer(self.datarfb.source.description))
        self.comb += self.datarfb.source.connect(self.buffer.sink)

        dtimeout = Signal(32)

        read = Signal(10)
        toread = Signal(10)
        cnt = Signal(8)

        self.submodules.fsm = fsm = ClockDomainsRenamer("sd")(FSM(reset_state="IDLE"))

        fsm.act("IDLE",
            pads.data.oe.eq(0),
            pads.clk.eq(1),
            datarfb_reset.eq(1),
            self.buffer.source.ready.eq(1),
            If(sink.valid,
                NextValue(dtimeout, 0),
                NextValue(read, 0),
                # Read 1 block + 8*8 == 64 bits CRC
                NextValue(toread, cfg.blocksize + 8),
                NextState("DATA_READSTART")
            )
        )

        self.specials += MultiReg(datarfb_reset, self.datarfb.reset, "sd_fb")

        fsm.act("DATA_READSTART",
            pads.data.oe.eq(0),
            pads.clk.eq(1),
            NextValue(dtimeout, dtimeout + 1),
            If(self.buffer.source.valid,
                NextState("DATA_READ")
            ).Elif(dtimeout > cfg.datatimeout,
                NextState("TIMEOUT")
            )
        )

        fsm.act("DATA_READ",
            pads.data.oe.eq(0),
            pads.clk.eq(1),
            source.valid.eq(self.buffer.source.valid),
            source.data.eq(self.buffer.source.data),
            source.status.eq(SDCARD_STREAM_STATUS_OK),
            source.last.eq(read == (toread - 1)),
            self.buffer.source.ready.eq(source.ready),
            If(source.valid & source.ready,
                NextValue(read, read + 1),
                If(read == (toread - 1),
                    If(sink.last,
                        NextState("DATA_CLK40")
                    ).Else(
                        sink.ready.eq(1),
                        NextState("DATA_FLUSH")
                    )
                )
            )
        )

        fsm.act("DATA_FLUSH",
            pads.data.oe.eq(0),
            datarfb_reset.eq(1),
            self.buffer.source.ready.eq(1),
            If(cnt < 5,
                NextValue(cnt, cnt + 1),
            ).Else(
                NextValue(cnt, 0),
                NextState("IDLE")
            )
        )

        fsm.act("DATA_CLK40",
            pads.data.oe.eq(1),
            pads.data.o.eq(0xf),
            If(cnt < 40,
                NextValue(cnt, cnt + 1),
                pads.clk.eq(1)
            ).Else(
                NextValue(cnt, 0),
                sink.ready.eq(1),
                NextState("IDLE")
            )
        )

        fsm.act("TIMEOUT",
            source.valid.eq(1),
            source.data.eq(0),
            source.status.eq(SDCARD_STREAM_STATUS_TIMEOUT),
            source.last.eq(1),
            If(source.valid & source.ready,
                sink.ready.eq(1),
                NextState("IDLE")
            )
        )


class SDPHYCRCRFB(Module):
    def __init__(self, idata):
        self.start = Signal()
        self.valid = Signal()
        self.error = Signal()

        # # #

        counter = Signal(2)
        shift = Signal()
        data = Signal(3)

        valid = Signal()
        error = Signal()

        self.submodules.fsm = fsm = ClockDomainsRenamer("sd_fb")(FSM(reset_state="IDLE"))

        self.sync.sd_fb += If(shift, data.eq(Cat(idata, data)))

        self.submodules.pulse_start = PulseSynchronizer("sd", "sd_fb")
        self.comb += self.pulse_start.i.eq(self.start)

        fsm.act("IDLE",
            If(self.pulse_start.o,
                NextState("START")
            )
        )
        fsm.act("START",
            If(idata == 0,
                NextValue(counter, 0),
                NextState("RECEIVE")
            )
        )
        fsm.act("RECEIVE",
            shift.eq(1),
            If(counter == 2,
                NextState("CHECK")
            ).Else(
                NextValue(counter, counter + 1)
            )
        )
        fsm.act("CHECK",
            If(data == 0b101,
                valid.eq(0),
                error.eq(1),
            ).Else(
                valid.eq(1),
                error.eq(0)
            ),
            NextState("IDLE")
        )

        self.submodules.pulse_valid = PulseSynchronizer("sd_fb", "sd")
        self.submodules.pulse_error = PulseSynchronizer("sd_fb", "sd")
        self.comb += [
            self.pulse_valid.i.eq(valid),
            self.valid.eq(self.pulse_valid.o),
            self.pulse_error.i.eq(error),
            self.error.eq(self.pulse_error.o)
        ]


class SDPHYDATAW(Module):
    def __init__(self):
        self.pads = pads = _sdpads()
        self.sink = sink = stream.Endpoint([("data", 8)])

        self.crc_clear = Signal()
        self.crc_valids = Signal(32)
        self.crc_errors = Signal(32)

        # # #


        wrstarted = Signal()
        cnt = Signal(8)

        self.submodules.crcfb = SDPHYCRCRFB(pads.data.i[0])
        self.sync.sd += [
            If(self.crc_clear,
                self.crc_valids.eq(0),
                self.crc_errors.eq(0)
            ),
            If(self.crcfb.valid,
                self.crc_valids.eq(self.crc_valids + 1)
            ),
            If(self.crcfb.error,
                self.crc_errors.eq(self.crc_errors + 1)
            )
        ]

        self.submodules.fsm = fsm = ClockDomainsRenamer("sd")(FSM(reset_state="IDLE"))

        fsm.act("IDLE",
            If(sink.valid,
                pads.clk.eq(1),
                pads.data.oe.eq(1),
                If(wrstarted,
                    pads.data.o.eq(sink.data[4:8]),
                    NextState("DATA_WRITE")
                ).Else(
                    pads.data.o.eq(0),
                    NextState("DATA_WRITESTART")
                )
            )
        )

        fsm.act("DATA_WRITESTART",
            pads.clk.eq(1),
            pads.data.oe.eq(1),
            pads.data.o.eq(sink.data[4:8]),
            NextValue(wrstarted, 1),
            NextState("DATA_WRITE")
        )

        fsm.act("DATA_WRITE",
            pads.clk.eq(1),
            pads.data.oe.eq(1),
            pads.data.o.eq(sink.data[0:4]),
            If(sink.last,
                NextState("DATA_WRITESTOP")
            ).Else(
                sink.ready.eq(1),
                NextState("IDLE")
            )
        )

        fsm.act("DATA_WRITESTOP",
            pads.clk.eq(1),
            pads.data.oe.eq(1),
            pads.data.o.eq(0xf),
            NextValue(wrstarted, 0),
            self.crcfb.start.eq(1),
            NextState("DATA_RESPONSE")
        )

        fsm.act("DATA_RESPONSE",
            pads.clk.eq(1),
            pads.data.oe.eq(0),
            If(cnt < 16,
                NextValue(cnt, cnt + 1),
            ).Else(
                # wait while busy
                If(pads.data.i[0],
                    NextValue(cnt, 0),
                    sink.ready.eq(1),
                    NextState("IDLE")
                )
            )
        )

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

        # Cmd input
        self.specials += SDRInput(self.cmd_t.i, sdpads.cmd.i, ClockSignal("sd"))

        # Data input
        for i in range(4):
            self.specials += SDRInput(self.data_t.i[i], sdpads.data.i[i], ClockSignal("sd"))


class SDPHY(Module, AutoCSR):
    def __init__(self, pads, device, **kwargs):
        self.sink = sink = stream.Endpoint([("data", 8), ("cmd_data_n", 1), ("rd_wr_n", 1)])
        self.source = source = stream.Endpoint([("data", 8), ("status", 3)])
        if hasattr(pads, "sel"):
            self.voltage_sel = CSRStorage()
            self.comb += pads.sel.eq(self.voltage_sel.storage)
        self.card_detect = CSRStatus()
        self.comb += self.card_detect.status.eq(getattr(pads, "cd", 0)) # Assume SDCard is present if no cd pin.

        # # #

        self.sdpads = sdpads = _sdpads()

        self.clock_domains.cd_sd    = ClockDomain()
        self.clock_domains.cd_sd_fb = ClockDomain()

        # IOs (device specific)
        self.comb += [
            ClockSignal("sd").eq(ClockSignal("sdcard")),
            ResetSignal("sd").eq(ResetSignal("sdcard")),
            ClockSignal("sd_fb").eq(ClockSignal("sdcard")),
            ResetSignal("sd_fb").eq(ResetSignal("sdcard")),
        ]
        if hasattr(pads, "cmd_t") and hasattr(pads, "dat_t"):
            # emulator phy
            self.comb += [
                If(sdpads.clk, pads.clk.eq(~ClockSignal("sd"))),

                pads.cmd_i.eq(1),
                If(sdpads.cmd.oe, pads.cmd_i.eq(sdpads.cmd.o)),
                sdpads.cmd.i.eq(1),
                If(~pads.cmd_t, sdpads.cmd.i.eq(pads.cmd_o)),

                pads.dat_i.eq(0b1111),
                If(sdpads.data.oe, pads.dat_i.eq(sdpads.data.o)),
                sdpads.data.i.eq(0b1111),
                If(~pads.dat_t[0], sdpads.data.i[0].eq(pads.dat_o[0])),
                If(~pads.dat_t[1], sdpads.data.i[1].eq(pads.dat_o[1])),
                If(~pads.dat_t[2], sdpads.data.i[2].eq(pads.dat_o[2])),
                If(~pads.dat_t[3], sdpads.data.i[3].eq(pads.dat_o[3]))
            ]
        else:
            self.submodules.io = io = SDPHYIOGen(sdpads, pads, **kwargs)
            self.sync.sd += [
                io.cmd_t.oe.eq(sdpads.cmd.oe),
                io.cmd_t.o.eq(sdpads.cmd.o),

                io.data_t.oe.eq(sdpads.data.oe),
                io.data_t.o.eq(sdpads.data.o)
            ]

        # PHY submodules
        self.submodules.cfg = cfg = SDPHYCFG()
        self.submodules.cmdw = cmdw = SDPHYCMDW()
        self.submodules.cmdr = cmdr = SDPHYCMDR(cfg)
        self.submodules.dataw = dataw = SDPHYDATAW()
        self.submodules.datar = datar = SDPHYDATAR(cfg)

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
