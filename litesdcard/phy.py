from litex.gen import *
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


class SDPHYRFB(Module):
    def __init__(self, idata, enable):
        self.source = source = stream.Endpoint([("data", 2)])

        # # #

        n = 8//len(idata)
        sel = Signal(max=n)
        data = Signal(8)

        self.submodules.fsm = fsm = ResetInserter()(FSM())
        self.comb += fsm.reset.eq(~enable)

        fsm.act("IDLE",
            NextValue(sel, 0),
            NextState("READSTART")
        )

        fsm.act("READSTART",
            If(idata == 0,
                NextValue(sel, sel + 1),
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
        self.sink = sink = stream.Endpoint([("data", 8), ("ctrl", 2)])
        self.source = source = stream.Endpoint([("data", 8), ("ctrl", 2)])

        # # #

        enable = Signal()

        self.submodules.cmdrfb = ClockDomainsRenamer("sd_rx")(SDPHYRFB(pads.cmd.i, enable))
        self.submodules.fifo = ClockDomainsRenamer({"write": "sd_rx", "read": "sd_tx"})(
            stream.AsyncFIFO(self.cmdrfb.source.description, 4)
        )
        self.comb += self.cmdrfb.source.connect(self.fifo.sink)

        ctimeout = Signal(32)

        cread = Signal(8)
        ctoread = Signal(8)
        cnt = Signal(8)

        status = Signal(4)
        self.comb += source.ctrl.eq(Cat(SDCARD_STREAM_CMD, status))

        self.submodules.fsm = fsm = FSM()

        fsm.act("IDLE",
            If(sink.valid,
                NextValue(ctimeout, 0),
                NextValue(cread, 0),
                NextValue(ctoread, sink.data),
                NextState("CMD_READSTART")
            )
        )

        fsm.act("CMD_READSTART",
            enable.eq(1),
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
            enable.eq(1),
            pads.cmd.oe.eq(0),
            pads.clk.eq(1),
            source.valid.eq(self.fifo.source.valid),
            source.data.eq(self.fifo.source.data),
            status.eq(SDCARD_STREAM_STATUS_OK),
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
            status.eq(SDCARD_STREAM_STATUS_TIMEOUT),
            source.last.eq(1),
            If(source.valid & source.ready,
                sink.ready.eq(1),
                NextState("IDLE")
            )
        )


class SDPHYCMDW(Module):
    def __init__(self):
        self.pads = pads = _sdpads()
        self.sink = sink = stream.Endpoint([("data", 8), ("ctrl", 2)])

        # # #

        isinit = Signal()
        cntinit = Signal(8)
        cnt = Signal(8)
        wrsel = Signal(3)
        wrtmpdata = Signal(8)

        wrcases = {} # For command write
        for i in range(8):
            wrcases[i] =  pads.cmd.o.eq(wrtmpdata[7-i])

        self.submodules.fsm = fsm = FSM()

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
        self.sink = sink = stream.Endpoint([("data", 8), ("ctrl", 2)])
        self.source = source = stream.Endpoint([("data", 8), ("ctrl", 2)])

        # # #

        enable = Signal()

        self.submodules.datarfb = ClockDomainsRenamer("sd_rx")(SDPHYRFB(pads.data.i, enable))
        self.submodules.fifo = ClockDomainsRenamer({"write": "sd_rx", "read": "sd_tx"})(
            stream.AsyncFIFO(self.datarfb.source.description, 4)
        )
        self.comb += self.datarfb.source.connect(self.fifo.sink)

        dtimeout = Signal(32)

        read = Signal(8)
        toread = Signal(8)
        cnt = Signal(8)

        status = Signal(4)
        self.comb += source.ctrl.eq(Cat(SDCARD_STREAM_DATA, status))

        self.submodules.fsm = fsm = FSM()

        fsm.act("IDLE",
            If(sink.valid,
                NextValue(dtimeout, 0),
                NextValue(read, 0),
                # Read 1 block + 8*8 == 64 bits CRC
                NextValue(toread, cfg.blocksize + 8),
                NextState("DATA_READSTART")
            )
        )

        fsm.act("DATA_READSTART",
            enable.eq(1),
            pads.data.oe.eq(0),
            pads.clk.eq(1),
            NextValue(dtimeout, dtimeout + 1),
            If(self.fifo.source.valid,
                NextState("DATA_READ")
            ).Elif(dtimeout > cfg.datatimeout,
                NextState("TIMEOUT")
            )
        )

        fsm.act("DATA_READ",
            enable.eq(1),
            pads.data.oe.eq(0),
            pads.clk.eq(1),

            source.valid.eq(self.fifo.source.valid),
            source.data.eq(self.fifo.source.data),
            status.eq(SDCARD_STREAM_STATUS_OK),
            source.last.eq(read == toread),
            self.fifo.source.ready.eq(source.ready),

            If(source.valid & source.ready,
                NextValue(read, read + 1),
                If(read == toread,
                    If(sink.last,
                        NextState("DATA_CLK40")
                    ).Else(
                        sink.ready.eq(1),
                        NextState("IDLE")
                    )
                )
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
            status.eq(SDCARD_STREAM_STATUS_TIMEOUT),
            source.last.eq(1),
            If(source.valid & source.ready,
                sink.ready.eq(1),
                NextState("IDLE")
            )
        )


class SDPHYDATAW(Module):
    def __init__(self):
        self.pads = pads = _sdpads()
        self.sink = sink = stream.Endpoint([("data", 8), ("ctrl", 2)])

        # # #

        wrstarted = Signal()

        self.submodules.fsm = fsm = FSM()

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
            NextState("IDLE") # XXX not implemented
        )


class SDPHYIOS6(Module):
    def __init__(self, sdpads, pads):
        # Data tristate
        self.data_t = TSTriple(4)
        self.specials += self.data_t.get_tristate(pads.data)

        # Cmd tristate
        self.cmd_t = TSTriple()
        self.specials += self.cmd_t.get_tristate(pads.cmd)

        # Clk domain feedback
        if hasattr(pads, "clkfb"):
            self.specials += Instance("IBUFG", i_I=pads.clkfb, o_O=ClockSignal("sd_rx"))

        # Clk output
        self.specials += Instance("ODDR2", p_DDR_ALIGNMENT="NONE",
            p_INIT=1, p_SRTYPE="SYNC",
            i_D0=0, i_D1=sdpads.clk, i_S=0, i_R=0, i_CE=1,
            i_C0=ClockSignal("sd_tx"), i_C1=~ClockSignal("sd_tx"),
            o_Q=pads.clk
        )

        # Cmd input DDR
        self.specials += Instance("IDDR2",
            p_DDR_ALIGNMENT="C1", p_INIT_Q0=0, p_INIT_Q1=0, p_SRTYPE="ASYNC",
            i_C0=ClockSignal("sd_rx"), i_C1=~ClockSignal("sd_rx"),
            i_CE=1, i_S=0, i_R=0,
            i_D=self.cmd_t.i, o_Q0=Signal(), o_Q1=sdpads.cmd.i
        )

        # Data input DDR
        for i in range(4):
            self.specials += Instance("IDDR2",
                p_DDR_ALIGNMENT="C0", p_INIT_Q0=0, p_INIT_Q1=0, p_SRTYPE="ASYNC",
                i_C0=ClockSignal("sd_rx"), i_C1=~ClockSignal("sd_rx"),
                i_CE=1, i_S=0, i_R=0,
                i_D=self.data_t.i[i], o_Q0=Signal(), o_Q1=sdpads.data.i[i]
            )


class SDPHYIOS7(Module):
    def __init__(self, sdpads, pads):
        # Data tristate
        self.data_t = TSTriple(4)
        self.specials += self.data_t.get_tristate(pads.data)

        # Cmd tristate
        self.cmd_t = TSTriple()
        self.specials += self.cmd_t.get_tristate(pads.cmd)

        # Clk domain feedback
        if hasattr(pads, "clkfb"):
            self.specials += Instance("IBUFG", i_I=pads.clkfb, o_O=ClockSignal("sd_rx"))

        # Clk output
        self.specials += Instance("ODDR",
            p_DDR_CLK_EDGE="SAME_EDGE",
            i_C=ClockSignal("sd_tx"), i_CE=1, i_S=0, i_R=0,
            i_D1=0, i_D2=sdpads.clk, o_Q=pads.clk
        )

        # Cmd input DDR
        self.specials += Instance("IDDR",
            p_DDR_CLK_EDGE="SAME_EDGE_PIPELINED",
            i_C=ClockSignal("sd_rx"), i_CE=1, i_S=0, i_R=0,
            i_D=self.cmd_t.i, o_Q1=Signal(), o_Q2=sdpads.cmd.i
        )

        # Data input DDR
        for i in range(4):
            self.specials += Instance("IDDR",
                p_DDR_CLK_EDGE="SAME_EDGE_PIPELINED",
                i_C=ClockSignal("sd_rx"), i_CE=1, i_S=0, i_R=0,
                i_D=self.data_t.i[i], o_Q1=Signal(), o_Q2=sdpads.data.i[i],
            )


class SDPHY(Module, AutoCSR):
    def __init__(self, pads, device):
        self.sink = sink = stream.Endpoint([("data", 8), ("ctrl", 2)])
        self.source = source = stream.Endpoint([("data", 8), ("ctrl", 2)])
        if hasattr(pads, "sel"):
            self.voltage_sel = CSRStorage()
            self.comb += pads.sel.eq(self.voltage_sel.storage)

        # # #

        self.sdpads = sdpads = _sdpads()

        cmddata = Signal()
        rdwr = Signal()

        # IOs (device specific)
        if not hasattr(pads, "clkfb"):
            self.comb += [
                ClockSignal("sd_rx").eq(ClockSignal("sd_tx")),
                ResetSignal("sd_rx").eq(ResetSignal("sd_tx"))
            ]
        if hasattr(pads, "cmd_t") and hasattr(pads, "dat_t"):
            # emulator phy
            self.comb += [
                If(sdpads.clk, pads.clk.eq(~ClockSignal("sd_tx"))),

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
            # real phy
            if device[:3] == "xc6":
                self.submodules.io = io = SDPHYIOS6(sdpads, pads)
            elif device[:3] == "xc7":
                self.submodules.io = io = SDPHYIOS7(sdpads, pads)
            else:
                raise NotImplementedError
            self.comb += [
                io.cmd_t.oe.eq(sdpads.cmd.oe),
                io.cmd_t.o.eq(sdpads.cmd.o),

                io.data_t.oe.eq(sdpads.data.oe),
                io.data_t.o.eq(sdpads.data.o)
            ]

        # Stream ctrl bits
        self.comb += [
            cmddata.eq(sink.ctrl[0]),
            rdwr.eq(sink.ctrl[1])
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
                If(cmddata == SDCARD_STREAM_CMD,
                    # Write command
                    If(rdwr == SDCARD_STREAM_WRITE,
                        sink.connect(cmdw.sink),
                        cmdw.pads.connect(sdpads)
                    # Read response
                    ).Elif(rdwr == SDCARD_STREAM_READ,
                        sink.connect(cmdr.sink),
                        cmdr.pads.connect(sdpads),
                        cmdr.source.connect(source)
                    )
                # Data mode
                ).Elif(cmddata == SDCARD_STREAM_DATA,
                    # Write data
                    If(rdwr == SDCARD_STREAM_WRITE,
                        sink.connect(dataw.sink),
                        dataw.pads.connect(sdpads)
                    # Read data
                    ).Elif(rdwr == SDCARD_STREAM_READ,
                        sink.connect(datar.sink),
                        datar.pads.connect(sdpads),
                        datar.source.connect(source)
                    )
                )
            )
