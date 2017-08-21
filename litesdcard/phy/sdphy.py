from litex.gen import *
from litex.soc.interconnect import stream
from litex.soc.interconnect.csr import *

from litesdcard.core.crcgeneric import CRC, CRCChecker
from litesdcard.core.crcchecker import DOWNCRCChecker, UPCRCAdd

SDCARD_STREAM_CMD = 0
SDCARD_STREAM_DATA = 1

SDCARD_STREAM_READ = 0
SDCARD_STREAM_WRITE = 1

SDCARD_STREAM_XFER = 0
SDCARD_STREAM_CFG_TIMEOUT_CMD_HH = 1
SDCARD_STREAM_CFG_TIMEOUT_CMD_HL = 2
SDCARD_STREAM_CFG_TIMEOUT_CMD_LH = 3
SDCARD_STREAM_CFG_TIMEOUT_CMD_LL = 4
SDCARD_STREAM_CFG_TIMEOUT_DATA_HH = 5
SDCARD_STREAM_CFG_TIMEOUT_DATA_HL = 6
SDCARD_STREAM_CFG_TIMEOUT_DATA_LH = 7
SDCARD_STREAM_CFG_TIMEOUT_DATA_LL = 8
SDCARD_STREAM_CFG_BLKSIZE_H = 9
SDCARD_STREAM_CFG_BLKSIZE_L = 10

SDCARD_STREAM_STATUS_OK = 0
SDCARD_STREAM_STATUS_TIMEOUT = 1
SDCARD_STREAM_STATUS_DATAACCEPTED = 0b010
SDCARD_STREAM_STATUS_CRCERROR = 0b101
SDCARD_STREAM_STATUS_WRITEERROR = 0b110

SDCARD_CTRL_DATA_TRANSFER_NONE = 0
SDCARD_CTRL_DATA_TRANSFER_READ = 1
SDCARD_CTRL_DATA_TRANSFER_WRITE = 2

SDCARD_CTRL_RESPONSE_NONE = 0
SDCARD_CTRL_RESPONSE_SHORT = 1
SDCARD_CTRL_RESPONSE_LONG = 2


class SDCtrl(Module, AutoCSR):
    def __init__(self):
        self.argument = CSRStorage(32)
        self.command = CSRStorage(32)
        self.response = CSRStatus(120)
        self.datatimeout = CSRStorage(32)
        self.cmdtimeout = CSRStorage(32)
        self.cmdevt = CSRStatus(32)
        self.dataevt = CSRStatus(32)
        self.blocksize = CSRStorage(16)
        self.blockcount = CSRStorage(16)
        self.debug = CSRStatus(32)

        self.submodules.crc7 = CRC(9, 7, 40)
        self.submodules.crc7checker = CRCChecker(9, 7, 120)
        self.submodules.crc16 = UPCRCAdd()
        self.submodules.crc16checker = DOWNCRCChecker()

        self.rsink = self.crc16.sink
        self.rsource = self.crc16checker.source

        self.sink = stream.Endpoint([("data", 8), ("ctrl", 8)])
        self.source = stream.Endpoint([("data", 8), ("ctrl", 8)])

        self.submodules.fsm = fsm = FSM()

        csel = Signal(max=6)
        waitresp = Signal(2)
        dataxfer = Signal(2)
        cmddone = Signal(reset=1)
        datadone = Signal(reset=1)
        blkcnt = Signal(16)
        pos = Signal(2)

        cmddata = Signal()
        rdwr = Signal()
        mode = Signal(6)
        status = Signal(4)

        cerrtimeout = Signal()
        cerrcrc_en = Signal()
        derrtimeout = Signal()
        derrwrite = Signal()
        derrread_en = Signal()

        self.comb += [
            waitresp.eq(self.command.storage[0:2]),
            dataxfer.eq(self.command.storage[5:7]),
            self.cmdevt.status.eq(Cat(cmddone,
                                      C(0, 1),
                                      cerrtimeout,
                                      cerrcrc_en & ~self.crc7checker.valid)),
            self.dataevt.status.eq(Cat(datadone,
                                       derrwrite,
                                       derrtimeout,
                                       derrread_en & ~self.crc16checker.valid)),

            self.source.ctrl.eq(Cat(cmddata, rdwr, mode)),
            status.eq(self.sink.ctrl[1:5]),

            self.crc7.val.eq(Cat(self.argument.storage,
                                 self.command.storage[8:14],
                                 1,
                                 0)),
            self.crc7.clr.eq(1),
            self.crc7.enable.eq(1),

            self.crc7checker.val.eq(self.response.status)
        ]

        ccases = {} # To send command and CRC
        ccases[0] = self.source.data.eq(Cat(self.command.storage[8:14], 1, 0))
        for i in range(4):
            ccases[i+1] = self.source.data.eq(self.argument.storage[24-8*i:32-8*i])
        ccases[5] = [
            self.source.data.eq(Cat(1, self.crc7.crc)),
            self.source.last.eq(waitresp == SDCARD_CTRL_RESPONSE_NONE)
        ]

        fsm.act("IDLE",
            NextValue(pos, 0),
            If(self.datatimeout.re,
                NextState("CFG_TIMEOUT_DATA"),
            ).Elif(self.cmdtimeout.re,
                NextState("CFG_TIMEOUT_CMD"),
            ).Elif(self.blocksize.re,
                NextState("CFG_BLKSIZE"),
            ).Elif(self.command.re,
                NextValue(cmddone, 0),
                NextValue(cerrtimeout, 0),
                NextValue(cerrcrc_en, 0),
                NextValue(datadone, 0),
                NextValue(derrtimeout, 0),
                NextValue(derrwrite, 0),
                NextValue(derrread_en, 0),
                NextValue(self.debug.status, 0),
                NextValue(self.response.status, 0),
                NextState("SEND_CMD")
            )
        )

        dtcases = {}
        for i in range(4):
            dtcases[i] = [
                self.source.data.eq(self.datatimeout.storage[24-(8*i):32-(8*i)]),
                mode.eq(SDCARD_STREAM_CFG_TIMEOUT_DATA_HH + i)
            ]
        ctcases = {}
        for i in range(4):
            ctcases[i] = [
                self.source.data.eq(self.cmdtimeout.storage[24-(8*i):32-(8*i)]),
                mode.eq(SDCARD_STREAM_CFG_TIMEOUT_CMD_HH + i)
            ]
        blkcases = {}
        for i in range(2):
            blkcases[i] = [
                self.source.data.eq(self.blocksize.storage[8-(8*i):16-(8*i)]),
                mode.eq(SDCARD_STREAM_CFG_BLKSIZE_H + i)
            ]

        fsm.act("CFG_TIMEOUT_DATA",
            self.source.valid.eq(1),
            Case(pos, dtcases),
            If(self.source.valid & self.source.ready,
                NextValue(pos, pos + 1),
                If(pos == 3,
                    NextState("IDLE")
                )
            )
        )

        fsm.act("CFG_TIMEOUT_CMD",
            self.source.valid.eq(1),
            Case(pos, ctcases),
            If(self.source.valid & self.source.ready,
                NextValue(pos, pos + 1),
                If(pos == 3,
                    NextState("IDLE")
                )
            )
        )

        fsm.act("CFG_BLKSIZE",
            self.source.valid.eq(1),
            Case(pos, blkcases),
            If(self.source.valid & self.source.ready,
                NextValue(pos, pos + 1),
                If(pos == 1,
                    NextState("IDLE")
                )
            )
        )

        fsm.act("SEND_CMD",
            self.source.valid.eq(1),
            cmddata.eq(SDCARD_STREAM_CMD),
            rdwr.eq(SDCARD_STREAM_WRITE),
            mode.eq(SDCARD_STREAM_XFER),
            Case(csel, ccases),
            If(self.source.valid & self.source.ready,
                If(csel < 5,
                    NextValue(csel, csel + 1)
                ).Else(
                    NextValue(csel, 0),
                    If(waitresp == SDCARD_CTRL_RESPONSE_NONE,
                        NextValue(cmddone, 1),
                        NextState("IDLE")
                    ).Else(
                        NextValue(cerrcrc_en, 1),
                        NextState("RECV_RESP")
                    )
                )
            )
        )

        fsm.act("RECV_RESP",
            If(waitresp == SDCARD_CTRL_RESPONSE_SHORT,
                self.source.data.eq(5) # (5+1)*8 == 48bits
            ).Elif(waitresp == SDCARD_CTRL_RESPONSE_LONG,
                self.source.data.eq(16) # (16+1)*8 == 136bits
            ),
            self.source.valid.eq(1),
            self.source.last.eq(dataxfer == SDCARD_CTRL_DATA_TRANSFER_NONE),
            cmddata.eq(SDCARD_STREAM_CMD),
            rdwr.eq(SDCARD_STREAM_READ),
            mode.eq(SDCARD_STREAM_XFER),

            If(self.sink.valid,
                self.sink.ready.eq(1),
                If(self.sink.ctrl[0] == SDCARD_STREAM_CMD,
                    If(status == SDCARD_STREAM_STATUS_TIMEOUT,
                        NextValue(cerrtimeout, 1),
                        NextValue(cmddone, 1),
                        NextValue(datadone, 1),
                        NextState("IDLE")
                    ).Elif(self.sink.last,
                        # Check response CRC
                        NextValue(self.crc7checker.check, self.sink.data[1:8]),
                        NextValue(cmddone, 1),
                        If(dataxfer == SDCARD_CTRL_DATA_TRANSFER_READ,
                            NextValue(derrread_en, 1),
                            NextState("RECV_DATA")
                        ).Elif(dataxfer == SDCARD_CTRL_DATA_TRANSFER_WRITE,
                            NextState("SEND_DATA")
                        ).Else(
                            NextValue(datadone, 1),
                            NextState("IDLE")
                        )
                    ).Else(
                        NextValue(self.response.status,
                                  Cat(self.sink.data, self.response.status[0:112])),
                    )
                )
            )
        )

        fsm.act("RECV_DATA",
            self.source.data.eq(0), # Read 1 block
            cmddata.eq(SDCARD_STREAM_DATA),
            rdwr.eq(SDCARD_STREAM_READ),
            mode.eq(SDCARD_STREAM_XFER),
            self.source.last.eq(self.blockcount.storage == blkcnt),
            self.source.valid.eq(1),

            If(self.sink.ctrl[0] == SDCARD_STREAM_DATA,
                If(status == SDCARD_STREAM_STATUS_OK,
                    self.crc16checker.sink.data.eq(self.sink.data), # Manual connect
                    self.crc16checker.sink.valid.eq(self.sink.valid),
                    self.crc16checker.sink.last.eq(self.sink.last),
                    self.sink.ready.eq(self.crc16checker.sink.ready)
                )
            ),

            If(self.sink.valid & (status == SDCARD_STREAM_STATUS_TIMEOUT),
                NextValue(derrtimeout, 1),
                self.sink.ready.eq(1),
                NextValue(blkcnt, 0),
                NextValue(datadone, 1),
                NextState("IDLE")
            ).Elif(self.source.valid & self.source.ready,
                If(self.blockcount.storage > blkcnt,
                    NextValue(blkcnt, blkcnt + 1)
                ).Else(
                    NextValue(blkcnt, 0),
                    NextValue(datadone, 1),
                    NextState("IDLE")
                )
            )
        )

        fsm.act("SEND_DATA",
            self.source.data.eq(self.crc16.source.data),
            cmddata.eq(SDCARD_STREAM_DATA),
            rdwr.eq(SDCARD_STREAM_WRITE),
            mode.eq(SDCARD_STREAM_XFER),
            self.source.last.eq(self.crc16.source.last),
            self.source.valid.eq(self.crc16.source.valid),
            self.crc16.source.ready.eq(self.source.ready),

            If(self.crc16.source.valid & self.crc16.source.last & self.crc16.source.ready,
                If(self.blockcount.storage > blkcnt,
                    NextValue(blkcnt, blkcnt + 1)
                ).Else(
                    NextValue(blkcnt, 0),
                    NextValue(datadone, 1),
                    NextState("IDLE")
                )
            ),

            If(self.sink.valid,
                self.sink.ready.eq(1),
                NextValue(self.debug.status, status), # XXX debug
                If(status != SDCARD_STREAM_STATUS_DATAACCEPTED,
                    NextValue(derrwrite, 1)
                )
            )
        )


class SDPHYModel(Module):
    def __init__(self, pads):
        self.sink = stream.Endpoint([("data", 8), ("ctrl", 8)])
        self.source = stream.Endpoint([("data", 8), ("ctrl", 8)])

        self.comb += [
            self.sink.ready.eq(1)
        ]


class SDPHY(Module, AutoCSR):
    def __init__(self, pads):
        self.sink = stream.Endpoint([("data", 8), ("ctrl", 8)])
        self.source = stream.Endpoint([("data", 8), ("ctrl", 8)])

        clk = Signal()
        sclk = Signal()
        data_i1 = Signal(4)
        data_i2 = Signal(4)
        cmd_i1 = Signal()
        cmd_i2 = Signal()

        tmpread = Signal(4)
        read = Signal(16)
        toread = Signal(16)
        cread = Signal(8)
        ctoread = Signal(8)

        wrtmpdata = Signal(8)
        wrsel = Signal(3)
        wrstarted = Signal()
        rdtmpdata = Signal(7) # LSB is comb
        rdsel = Signal(3)
        sttmpdata = Signal(7) # LSB is comb
        stsel = Signal(3)

        isinit = Signal()
        dclkcnt = Signal(8)
        cclkcnt = Signal(8)
        ctimeout = Signal(32)
        dtimeout = Signal(32)

        cfgdtimeout = Signal(32)
        cfgctimeout = Signal(32)
        cfgblksize = Signal(16)

        cmddata = Signal()
        rdwr = Signal()
        mode = Signal(6)
        status = Signal(4)

        # XXX debug
        self.sttmpdata = sttmpdata
        self.data_i2 = data_i2
        self.stsel = stsel
        self.cfgdtimeout = cfgdtimeout
        self.cfgblksize = cfgblksize

        self.data_t = TSTriple(4)
        self.specials += self.data_t.get_tristate(pads.data)

        self.cmd_t = TSTriple()
        self.specials += self.cmd_t.get_tristate(pads.cmd)

        self.specials += Instance("ODDR2", p_DDR_ALIGNMENT="NONE",
            p_INIT=1, p_SRTYPE="SYNC",
            i_D0=0, i_D1=clk, i_S=0, i_R=0, i_CE=1,
            i_C0=ClockSignal("sys"), i_C1=~ClockSignal("sys"),
            o_Q=pads.clk
        )

        if hasattr(pads, "clkfb"):
            clkfb = Signal()
            self.specials += Instance("IBUF", i_I=pads.clkfb, o_O=clkfb)
            self.comb += sclk.eq(clkfb)
        else:
            self.comb += sclk.eq(ClockSignal("sys"))

        # FIXME: handle sclk to sys clk cdc
        for i in range(4):
            self.specials += Instance("IDDR2",
                p_DDR_ALIGNMENT="C0", p_INIT_Q0=0, p_INIT_Q1=0, p_SRTYPE="ASYNC",
                i_C0=sclk, i_C1=~sclk,
                i_CE=1, i_S=0, i_R=0,
                i_D=self.data_t.i[i], o_Q0=data_i1[i], o_Q1=data_i2[i]
            )

        self.specials += Instance("IDDR2",
            p_DDR_ALIGNMENT="C1", p_INIT_Q0=0, p_INIT_Q1=0, p_SRTYPE="ASYNC",
            i_C0=sclk, i_C1=~sclk,
            i_CE=1, i_S=0, i_R=0,
            i_D=self.cmd_t.i, o_Q0=cmd_i1, o_Q1=cmd_i2
        )

        self.comb += [
            cmddata.eq(self.sink.ctrl[0]),
            rdwr.eq(self.sink.ctrl[1]),
            mode.eq(self.sink.ctrl[2:8]),

            self.source.ctrl.eq(Cat(cmddata, status))
        ]

        self.submodules.fsm = fsm = FSM()

        cfgcases = {} # PHY configuration
        for i in range(4):
            cfgcases[SDCARD_STREAM_CFG_TIMEOUT_DATA_HH + i] = NextValue(
                cfgdtimeout[24-(8*i):32-(8*i)], self.sink.data)
            cfgcases[SDCARD_STREAM_CFG_TIMEOUT_CMD_HH + i] = NextValue(
                cfgctimeout[24-(8*i):32-(8*i)], self.sink.data)
        for i in range(2):
            cfgcases[SDCARD_STREAM_CFG_BLKSIZE_H + i] = NextValue(
                cfgblksize[8-(8*i):16-(8*i)], self.sink.data)

        wrcases = {} # For command write
        for i in range(8):
            wrcases[i] =  self.cmd_t.o.eq(wrtmpdata[7-i])
        rdcases = {} # For command read
        for i in range(7): # LSB is comb
            rdcases[i] = NextValue(rdtmpdata[6-i], cmd_i2)
        stcases = {} # For status read
        for i in range(7): # LSB is comb
            stcases[i] = NextValue(sttmpdata[6-i], data_i2[0])

        fsm.act("IDLE",
            If(self.sink.valid,
                If(mode != SDCARD_STREAM_XFER, # Config mode
                    Case(mode, cfgcases),
                    self.sink.ready.eq(1)
                ).Elif(cmddata == SDCARD_STREAM_CMD, # Command mode
                    clk.eq(1),
                    NextValue(ctimeout, 0),
                    If(~isinit,
                        NextState("INIT")
                    ).Elif(rdwr == SDCARD_STREAM_WRITE,
                        NextValue(wrtmpdata, self.sink.data),
                        NextState("CMD_WRITE"),
                        NextValue(wrsel, 0)
                    ).Elif(rdwr == SDCARD_STREAM_READ,
                        NextValue(ctoread, self.sink.data),
                        NextValue(cread, 0),
                        NextState("CMD_READSTART"),
                        NextValue(rdsel, 0)
                    ),
                ).Elif(cmddata == SDCARD_STREAM_DATA, # Data mode
                    clk.eq(1),
                    NextValue(dtimeout, 0),
                    If(rdwr == SDCARD_STREAM_WRITE,
                        If(wrstarted,
                            NextValue(self.data_t.o, self.sink.data[4:8]),
                            NextValue(self.data_t.oe, 1),
                            NextState("DATA_WRITE")
                        ).Else(
                            NextValue(self.data_t.o, 0),
                            NextValue(self.data_t.oe, 1),
                            NextState("DATA_WRITESTART")
                        )
                    ).Elif(rdwr == SDCARD_STREAM_READ,
                        NextValue(toread, cfgblksize + 8), # Read 1 block
                        NextValue(read, 0),
                        NextValue(self.data_t.oe, 0),
                        NextState("DATA_READSTART")
                    )
                )
            )
        )

        fsm.act("INIT",
            clk.eq(1),
            self.cmd_t.oe.eq(1),
            self.cmd_t.o.eq(1),
            If(cclkcnt < 80,
                NextValue(cclkcnt, cclkcnt + 1),
                NextValue(self.data_t.oe, 1),
                NextValue(self.data_t.o, 0xf)
            ).Else(
                NextValue(cclkcnt, 0),
                NextValue(isinit, 1),
                NextValue(self.data_t.oe, 0),
                NextState("IDLE")
            )
        )

        fsm.act("TIMEOUT",
            self.source.valid.eq(1),
            self.source.data.eq(0),
            status.eq(SDCARD_STREAM_STATUS_TIMEOUT),
            self.source.last.eq(1),
            If(self.source.valid & self.source.ready,
                NextState("IDLE")
            )
        )

        fsm.act("CMD_WRITE",
            self.cmd_t.oe.eq(1),
            Case(wrsel, wrcases),
            NextValue(wrsel, wrsel + 1),
            If(wrsel == 7,
                If(self.sink.last,
                    clk.eq(1),
                    NextState("CMD_CLK8")
                ).Else(
                    self.sink.ready.eq(1),
                    NextState("IDLE")
                )
            ).Else(
                clk.eq(1)
            )
        )

        fsm.act("CMD_READSTART",
            self.cmd_t.oe.eq(0),
            clk.eq(1),
            NextValue(ctimeout, ctimeout + 1),
            If(cmd_i2 == 0,
                NextState("CMD_READ"),
                NextValue(rdsel, 1),
                NextValue(rdtmpdata, 0)
            ).Elif(ctimeout > (cfgctimeout),
                NextState("TIMEOUT")
            )
        )

        fsm.act("CMD_READ",
            self.cmd_t.oe.eq(0),
            Case(rdsel, rdcases),
            If(rdsel == 7,
                self.source.valid.eq(1),
                self.source.data.eq(Cat(cmd_i2, rdtmpdata)),
                status.eq(SDCARD_STREAM_STATUS_OK),
                self.source.last.eq(cread == ctoread),
                If(self.source.valid & self.source.ready,
                    NextValue(cread, cread + 1),
                    NextValue(rdsel, rdsel + 1),
                    If(cread == ctoread,
                        If(self.sink.last,
                            clk.eq(1),
                            NextState("CMD_CLK8")
                        ).Else(
                            self.sink.ready.eq(1),
                            NextState("IDLE")
                        )
                    ).Else(
                        clk.eq(1)
                    )
                )
            ).Else(
                NextValue(rdsel, rdsel + 1),
                clk.eq(1)
            )
        )

        fsm.act("CMD_CLK8",
            self.cmd_t.oe.eq(1),
            self.cmd_t.o.eq(1),
            If(cclkcnt < 7,
                NextValue(cclkcnt, cclkcnt + 1),
                clk.eq(1)
            ).Else(
                NextValue(cclkcnt, 0),
                self.sink.ready.eq(1),
                NextState("IDLE")
            )
        )

        fsm.act("DATA_WRITESTART",
            clk.eq(1),
            NextValue(self.data_t.o, self.sink.data[4:8]),
            NextValue(self.data_t.oe, 1),
            NextState("DATA_WRITE"),
            NextValue(wrstarted, 1)
        )

        fsm.act("DATA_WRITE",
            clk.eq(1),
            NextValue(self.data_t.o, self.sink.data[0:4]),
            NextValue(self.data_t.oe, 1),
            If(self.sink.last,
                NextState("DATA_WRITESTOP")
            ).Else(
                self.sink.ready.eq(1),
                NextState("IDLE")
            )
        )

        fsm.act("DATA_WRITESTOP",
            clk.eq(1),
            NextValue(self.data_t.o, 0xf),
            NextValue(self.data_t.oe, 1),
            NextValue(wrstarted, 0),
            NextState("DATA_GETSTATUS_WAIT0")
        )

        fsm.act("DATA_READSTART",
            clk.eq(1),
            NextValue(self.data_t.oe, 0),
            NextValue(dtimeout, dtimeout + 1),
            If(data_i2 == 0,
                NextState("DATA_READ1"),
            ).Elif(dtimeout > (cfgdtimeout),
                NextState("TIMEOUT")
            )
        )

        fsm.act("DATA_READ1",
            clk.eq(1),
            NextValue(self.data_t.oe, 0),
            NextValue(tmpread, data_i2),
            NextState("DATA_READ2")
        )

        fsm.act("DATA_READ2",
            NextValue(self.data_t.oe, 0),
            self.source.data.eq(Cat(data_i2, tmpread)),
            status.eq(SDCARD_STREAM_STATUS_OK),
            self.source.valid.eq(1),
            self.source.last.eq(read == toread),

            If(self.source.valid & self.source.ready,
                clk.eq(1),
                NextValue(read, read + 1),
                If(read == toread,
                    If(self.sink.last,
                        NextState("DATA_CLK40")
                    ).Else(
                        self.sink.ready.eq(1),
                        NextState("IDLE")
                    )
                ).Else(
                    NextState("DATA_READ1")
                )
            )
        )

        fsm.act("DATA_CLK40",
            NextValue(self.data_t.o, 0xf),
            NextValue(self.data_t.oe, 1),
            If(dclkcnt < 40,
                NextValue(dclkcnt, dclkcnt + 1),
                clk.eq(1)
            ).Else(
                NextValue(dclkcnt, 0),
                self.sink.ready.eq(1),
                NextState("IDLE")
            )
        )

        fsm.act("DATA_CLK40_BUSY",
            NextValue(self.data_t.oe, 0),
            If((dclkcnt < 40) | ~data_i2[0],
                If(dclkcnt < 40,
                    NextValue(dclkcnt, dclkcnt + 1),
                ),
                clk.eq(1)
            ).Else(
                NextValue(dclkcnt, 0),
                self.sink.ready.eq(1),
                NextState("IDLE")
            )
        )

        fsm.act("DATA_GETSTATUS_WAIT0",
            clk.eq(1),
            NextValue(self.data_t.oe, 0),
            NextState("DATA_GETSTATUS_WAIT1")
        )
        fsm.act("DATA_GETSTATUS_WAIT1",
            clk.eq(1),
            NextValue(self.data_t.oe, 0),
            NextState("DATA_GETSTATUS")
        )

        fsm.act("DATA_GETSTATUS",
            Case(stsel, stcases),
            If(stsel == 7,
                self.source.valid.eq(1),
                self.source.data.eq(0),
                status.eq(Cat(data_i2[0], sttmpdata)[1:4]),
                self.source.last.eq(1),
                If(self.source.valid & self.source.ready,
                    NextValue(stsel, 0),
                    NextState("DATA_CLK40_BUSY")
                )
            ).Else(
                NextValue(stsel, stsel + 1),
                clk.eq(1)
            )
        )
