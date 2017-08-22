from litex.gen import *
from litex.soc.interconnect import stream
from litex.soc.interconnect.csr import *

from litesdcard.crc import CRC, CRCChecker
from litesdcard.crc import CRCDownstreamChecker, CRCUpstreamInserter


SDCARD_STREAM_CMD = 0
SDCARD_STREAM_DATA = 1

SDCARD_STREAM_READ = 0
SDCARD_STREAM_WRITE = 1

SDCARD_STREAM_VOLTAGE_3_3 = 0
SDCARD_STREAM_VOLTAGE_1_8 = 1

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
SDCARD_STREAM_CFG_VOLTAGE = 11

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
        self.voltage = CSRStorage(8)
        self.cmdevt = CSRStatus(32)
        self.dataevt = CSRStatus(32)
        self.blocksize = CSRStorage(16)
        self.blockcount = CSRStorage(16)

        self.submodules.crc7 = CRC(9, 7, 40)
        self.submodules.crc7checker = CRCChecker(9, 7, 120)
        self.submodules.crc16inserter = CRCUpstreamInserter()
        self.submodules.crc16checker = CRCDownstreamChecker()

        self.rsink = self.crc16inserter.sink
        self.rsource = self.crc16checker.source

        self.sink = sink = stream.Endpoint([("data", 8), ("ctrl", 8)])
        self.source = source = stream.Endpoint([("data", 8), ("ctrl", 8)])

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

            source.ctrl.eq(Cat(cmddata, rdwr, mode)),
            status.eq(sink.ctrl[1:5]),

            self.crc7.val.eq(Cat(self.argument.storage,
                                 self.command.storage[8:14],
                                 1,
                                 0)),
            self.crc7.clr.eq(1),
            self.crc7.enable.eq(1),

            self.crc7checker.val.eq(self.response.status)
        ]

        ccases = {} # To send command and CRC
        ccases[0] = source.data.eq(Cat(self.command.storage[8:14], 1, 0))
        for i in range(4):
            ccases[i+1] = source.data.eq(self.argument.storage[24-8*i:32-8*i])
        ccases[5] = [
            source.data.eq(Cat(1, self.crc7.crc)),
            source.last.eq(waitresp == SDCARD_CTRL_RESPONSE_NONE)
        ]

        fsm.act("IDLE",
            NextValue(pos, 0),
            If(self.datatimeout.re,
                NextState("CFG_TIMEOUT_DATA"),
            ).Elif(self.cmdtimeout.re,
                NextState("CFG_TIMEOUT_CMD"),
            ).Elif(self.voltage.re,
                NextState("CFG_VOLTAGE"),
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
                NextValue(self.response.status, 0),
                NextState("SEND_CMD")
            )
        )

        dtcases = {}
        for i in range(4):
            dtcases[i] = [
                source.data.eq(self.datatimeout.storage[24-(8*i):32-(8*i)]),
                mode.eq(SDCARD_STREAM_CFG_TIMEOUT_DATA_HH + i)
            ]

        fsm.act("CFG_TIMEOUT_DATA",
            source.valid.eq(1),
            Case(pos, dtcases),
            If(source.valid & source.ready,
                NextValue(pos, pos + 1),
                If(pos == 3,
                    NextState("IDLE")
                )
            )
        )

        ctcases = {}
        for i in range(4):
            ctcases[i] = [
                source.data.eq(self.cmdtimeout.storage[24-(8*i):32-(8*i)]),
                mode.eq(SDCARD_STREAM_CFG_TIMEOUT_CMD_HH + i)
            ]

        fsm.act("CFG_TIMEOUT_CMD",
            source.valid.eq(1),
            Case(pos, ctcases),
            If(source.valid & source.ready,
                NextValue(pos, pos + 1),
                If(pos == 3,
                    NextState("IDLE")
                )
            )
        )

        blkcases = {}
        for i in range(2):
            blkcases[i] = [
                source.data.eq(self.blocksize.storage[8-(8*i):16-(8*i)]),
                mode.eq(SDCARD_STREAM_CFG_BLKSIZE_H + i)
            ]

        fsm.act("CFG_BLKSIZE",
            source.valid.eq(1),
            Case(pos, blkcases),
            If(source.valid & source.ready,
                NextValue(pos, pos + 1),
                If(pos == 1,
                    NextState("IDLE")
                )
            )
        )

        fsm.act("CFG_VOLTAGE",
            source.valid.eq(1),
            source.data.eq(self.voltage.storage[0:8]),
            mode.eq(SDCARD_STREAM_CFG_VOLTAGE),
            If(source.valid & source.ready,
                NextState("IDLE"),
            ),
        )

        fsm.act("SEND_CMD",
            source.valid.eq(1),
            cmddata.eq(SDCARD_STREAM_CMD),
            rdwr.eq(SDCARD_STREAM_WRITE),
            mode.eq(SDCARD_STREAM_XFER),
            Case(csel, ccases),
            If(source.valid & source.ready,
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
                source.data.eq(5) # (5+1)*8 == 48bits
            ).Elif(waitresp == SDCARD_CTRL_RESPONSE_LONG,
                source.data.eq(16) # (16+1)*8 == 136bits
            ),
            source.valid.eq(1),
            source.last.eq(dataxfer == SDCARD_CTRL_DATA_TRANSFER_NONE),
            cmddata.eq(SDCARD_STREAM_CMD),
            rdwr.eq(SDCARD_STREAM_READ),
            mode.eq(SDCARD_STREAM_XFER),

            If(sink.valid,
                sink.ready.eq(1),
                If(sink.ctrl[0] == SDCARD_STREAM_CMD,
                    If(status == SDCARD_STREAM_STATUS_TIMEOUT,
                        NextValue(cerrtimeout, 1),
                        NextValue(cmddone, 1),
                        NextValue(datadone, 1),
                        NextState("IDLE")
                    ).Elif(sink.last,
                        # Check response CRC
                        NextValue(self.crc7checker.check, sink.data[1:8]),
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
                                  Cat(sink.data, self.response.status[0:112])),
                    )
                )
            )
        )

        fsm.act("RECV_DATA",
            source.data.eq(0), # Read 1 block
            cmddata.eq(SDCARD_STREAM_DATA),
            rdwr.eq(SDCARD_STREAM_READ),
            mode.eq(SDCARD_STREAM_XFER),
            source.last.eq(self.blockcount.storage == blkcnt),
            source.valid.eq(1),

            If(sink.ctrl[0] == SDCARD_STREAM_DATA,
                If(status == SDCARD_STREAM_STATUS_OK,
                    self.crc16checker.sink.data.eq(sink.data), # Manual connect
                    self.crc16checker.sink.valid.eq(sink.valid),
                    self.crc16checker.sink.last.eq(sink.last),
                    sink.ready.eq(self.crc16checker.sink.ready)
                )
            ),

            If(sink.valid & (status == SDCARD_STREAM_STATUS_TIMEOUT),
                NextValue(derrtimeout, 1),
                sink.ready.eq(1),
                NextValue(blkcnt, 0),
                NextValue(datadone, 1),
                NextState("IDLE")
            ).Elif(source.valid & source.ready,
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
            source.data.eq(self.crc16inserter.source.data),
            cmddata.eq(SDCARD_STREAM_DATA),
            rdwr.eq(SDCARD_STREAM_WRITE),
            mode.eq(SDCARD_STREAM_XFER),
            source.last.eq(self.crc16inserter.source.last),
            source.valid.eq(self.crc16inserter.source.valid),
            self.crc16inserter.source.ready.eq(source.ready),

            If(self.crc16inserter.source.valid &
               self.crc16inserter.source.last &
               self.crc16inserter.source.ready,
                If(self.blockcount.storage > blkcnt,
                    NextValue(blkcnt, blkcnt + 1)
                ).Else(
                    NextValue(blkcnt, 0),
                    NextValue(datadone, 1),
                    NextState("IDLE")
                )
            ),

            If(sink.valid,
                sink.ready.eq(1),
                If(status != SDCARD_STREAM_STATUS_DATAACCEPTED,
                    NextValue(derrwrite, 1)
                )
            )
        )


class SDPHY(Module, AutoCSR):
    def __init__(self, pads, device):
        self.sink = sink = stream.Endpoint([("data", 8), ("ctrl", 8)])
        self.source = source = stream.Endpoint([("data", 8), ("ctrl", 8)])

        # # #

        clk_en = Signal()
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

        self.data_t = data_t = TSTriple(4)
        self.specials += data_t.get_tristate(pads.data)

        self.cmd_t = cmd_t = TSTriple()
        self.specials += cmd_t.get_tristate(pads.cmd)

        if device[:3] == "xc7":
            # 7 series
            self.specials += Instance("ODDR",
                p_DDR_CLK_EDGE="SAME_EDGE",
                i_C=ClockSignal("sys"), i_CE=1, i_S=0, i_R=0,
                i_D1=0, i_D2=clk_en, o_Q=pads.clk
            )

            for i in range(4):
                self.specials += Instance("IDDR",
                    p_DDR_CLK_EDGE="SAME_EDGE_PIPELINED",
                    i_C=ClockSignal("sys"), i_CE=1, i_S=0, i_R=0,
                    i_D=data_t.i[i], o_Q1=data_i1[i], o_Q2=data_i2[i],
                )
            self.specials += Instance("IDDR",
                p_DDR_CLK_EDGE="SAME_EDGE_PIPELINED",
                i_C=ClockSignal("sys"), i_CE=1, i_S=0, i_R=0,
                i_D=cmd_t.i, o_Q1=cmd_i1, o_Q2=cmd_i2
            )
        elif device[:3] == "xc6":
            # Spartan 6
            self.specials += Instance("ODDR2", p_DDR_ALIGNMENT="NONE",
                p_INIT=1, p_SRTYPE="SYNC",
                i_D0=0, i_D1=clk_en, i_S=0, i_R=0, i_CE=1,
                i_C0=ClockSignal("sys"), i_C1=~ClockSignal("sys"),
                o_Q=pads.clk
            )

            for i in range(4):
                self.specials += Instance("IDDR2",
                    p_DDR_ALIGNMENT="C0", p_INIT_Q0=0, p_INIT_Q1=0, p_SRTYPE="ASYNC",
                    i_C0=ClockSignal("sys"), i_C1=~ClockSignal("sys"),
                    i_CE=1, i_S=0, i_R=0,
                    i_D=data_t.i[i], o_Q0=data_i1[i], o_Q1=data_i2[i]
                )

            self.specials += Instance("IDDR2",
                p_DDR_ALIGNMENT="C1", p_INIT_Q0=0, p_INIT_Q1=0, p_SRTYPE="ASYNC",
                i_C0=ClockSignal("sys"), i_C1=~ClockSignal("sys"),
                i_CE=1, i_S=0, i_R=0,
                i_D=cmd_t.i, o_Q0=cmd_i1, o_Q1=cmd_i2
            )
        else:
            raise NotImplementedError

        self.comb += [
            cmddata.eq(sink.ctrl[0]),
            rdwr.eq(sink.ctrl[1]),
            mode.eq(sink.ctrl[2:8]),

            source.ctrl.eq(Cat(cmddata, status))
        ]

        self.submodules.fsm = fsm = FSM()

        cfgcases = {} # PHY configuration
        for i in range(4):
            cfgcases[SDCARD_STREAM_CFG_TIMEOUT_DATA_HH + i] = NextValue(
                cfgdtimeout[24-(8*i):32-(8*i)], sink.data)
            cfgcases[SDCARD_STREAM_CFG_TIMEOUT_CMD_HH + i] = NextValue(
                cfgctimeout[24-(8*i):32-(8*i)], sink.data)
        for i in range(2):
            cfgcases[SDCARD_STREAM_CFG_BLKSIZE_H + i] = NextValue(
                cfgblksize[8-(8*i):16-(8*i)], sink.data)

        fsm.act("IDLE",
            If(sink.valid,
                If(mode != SDCARD_STREAM_XFER, # Config mode
                    Case(mode, cfgcases),
                    sink.ready.eq(1)
                ).Elif(cmddata == SDCARD_STREAM_CMD, # Command mode
                    clk_en.eq(1),
                    NextValue(ctimeout, 0),
                    If(~isinit,
                        NextState("INIT")
                    ).Elif(rdwr == SDCARD_STREAM_WRITE,
                        NextValue(wrtmpdata, sink.data),
                        NextState("CMD_WRITE"),
                        NextValue(wrsel, 0)
                    ).Elif(rdwr == SDCARD_STREAM_READ,
                        NextValue(ctoread, sink.data),
                        NextValue(cread, 0),
                        NextState("CMD_READSTART"),
                        NextValue(rdsel, 0)
                    ),
                ).Elif(cmddata == SDCARD_STREAM_DATA, # Data mode
                    clk_en.eq(1),
                    NextValue(dtimeout, 0),
                    If(rdwr == SDCARD_STREAM_WRITE,
                        If(wrstarted,
                            NextValue(data_t.o, sink.data[4:8]),
                            NextValue(data_t.oe, 1),
                            NextState("DATA_WRITE")
                        ).Else(
                            NextValue(data_t.o, 0),
                            NextValue(data_t.oe, 1),
                            NextState("DATA_WRITESTART")
                        )
                    ).Elif(rdwr == SDCARD_STREAM_READ,
                        NextValue(toread, cfgblksize + 8), # Read 1 block
                        NextValue(read, 0),
                        NextValue(data_t.oe, 0),
                        NextState("DATA_READSTART")
                    )
                )
            )
        )

        fsm.act("INIT",
            clk_en.eq(1),
            cmd_t.oe.eq(1),
            cmd_t.o.eq(1),
            If(cclkcnt < 80,
                NextValue(cclkcnt, cclkcnt + 1),
                NextValue(data_t.oe, 1),
                NextValue(data_t.o, 0xf)
            ).Else(
                NextValue(cclkcnt, 0),
                NextValue(isinit, 1),
                NextValue(data_t.oe, 0),
                NextState("IDLE")
            )
        )

        fsm.act("TIMEOUT",
            source.valid.eq(1),
            source.data.eq(0),
            status.eq(SDCARD_STREAM_STATUS_TIMEOUT),
            source.last.eq(1),
            If(source.valid & source.ready,
                NextState("IDLE")
            )
        )

        wrcases = {} # For command write
        for i in range(8):
            wrcases[i] =  cmd_t.o.eq(wrtmpdata[7-i])

        fsm.act("CMD_WRITE",
            cmd_t.oe.eq(1),
            Case(wrsel, wrcases),
            NextValue(wrsel, wrsel + 1),
            If(wrsel == 7,
                If(sink.last,
                    clk_en.eq(1),
                    NextState("CMD_CLK8")
                ).Else(
                    sink.ready.eq(1),
                    NextState("IDLE")
                )
            ).Else(
                clk_en.eq(1)
            )
        )

        fsm.act("CMD_READSTART",
            cmd_t.oe.eq(0),
            clk_en.eq(1),
            NextValue(ctimeout, ctimeout + 1),
            If(cmd_i2 == 0,
                NextState("CMD_READ"),
                NextValue(rdsel, 1),
                NextValue(rdtmpdata, 0)
            ).Elif(ctimeout > (cfgctimeout),
                NextState("TIMEOUT")
            )
        )

        rdcases = {} # For command read
        for i in range(7): # LSB is comb
            rdcases[i] = NextValue(rdtmpdata[6-i], cmd_i2)

        fsm.act("CMD_READ",
            cmd_t.oe.eq(0),
            Case(rdsel, rdcases),
            If(rdsel == 7,
                source.valid.eq(1),
                source.data.eq(Cat(cmd_i2, rdtmpdata)),
                status.eq(SDCARD_STREAM_STATUS_OK),
                source.last.eq(cread == ctoread),
                If(source.valid & source.ready,
                    NextValue(cread, cread + 1),
                    NextValue(rdsel, rdsel + 1),
                    If(cread == ctoread,
                        If(sink.last,
                            clk_en.eq(1),
                            NextState("CMD_CLK8")
                        ).Else(
                            sink.ready.eq(1),
                            NextState("IDLE")
                        )
                    ).Else(
                        clk_en.eq(1)
                    )
                )
            ).Else(
                NextValue(rdsel, rdsel + 1),
                clk_en.eq(1)
            )
        )

        fsm.act("CMD_CLK8",
            cmd_t.oe.eq(1),
            cmd_t.o.eq(1),
            If(cclkcnt < 7,
                NextValue(cclkcnt, cclkcnt + 1),
                clk_en.eq(1)
            ).Else(
                NextValue(cclkcnt, 0),
                sink.ready.eq(1),
                NextState("IDLE")
            )
        )

        fsm.act("DATA_WRITESTART",
            clk_en.eq(1),
            NextValue(data_t.o, sink.data[4:8]),
            NextValue(data_t.oe, 1),
            NextState("DATA_WRITE"),
            NextValue(wrstarted, 1)
        )

        fsm.act("DATA_WRITE",
            clk_en.eq(1),
            NextValue(data_t.o, sink.data[0:4]),
            NextValue(data_t.oe, 1),
            If(sink.last,
                NextState("DATA_WRITESTOP")
            ).Else(
                sink.ready.eq(1),
                NextState("IDLE")
            )
        )

        fsm.act("DATA_WRITESTOP",
            clk_en.eq(1),
            NextValue(data_t.o, 0xf),
            NextValue(data_t.oe, 1),
            NextValue(wrstarted, 0),
            NextState("DATA_GETSTATUS_WAIT0")
        )

        fsm.act("DATA_READSTART",
            clk_en.eq(1),
            NextValue(data_t.oe, 0),
            NextValue(dtimeout, dtimeout + 1),
            If(data_i2 == 0,
                NextState("DATA_READ1"),
            ).Elif(dtimeout > (cfgdtimeout),
                NextState("TIMEOUT")
            )
        )

        fsm.act("DATA_READ1",
            clk_en.eq(1),
            NextValue(data_t.oe, 0),
            NextValue(tmpread, data_i2),
            NextState("DATA_READ2")
        )

        fsm.act("DATA_READ2",
            NextValue(data_t.oe, 0),
            source.data.eq(Cat(data_i2, tmpread)),
            status.eq(SDCARD_STREAM_STATUS_OK),
            source.valid.eq(1),
            source.last.eq(read == toread),

            If(source.valid & source.ready,
                clk_en.eq(1),
                NextValue(read, read + 1),
                If(read == toread,
                    If(sink.last,
                        NextState("DATA_CLK40")
                    ).Else(
                        sink.ready.eq(1),
                        NextState("IDLE")
                    )
                ).Else(
                    NextState("DATA_READ1")
                )
            )
        )

        fsm.act("DATA_CLK40",
            NextValue(data_t.o, 0xf),
            NextValue(data_t.oe, 1),
            If(dclkcnt < 40,
                NextValue(dclkcnt, dclkcnt + 1),
                clk_en.eq(1)
            ).Else(
                NextValue(dclkcnt, 0),
                sink.ready.eq(1),
                NextState("IDLE")
            )
        )

        fsm.act("DATA_CLK40_BUSY",
            NextValue(data_t.oe, 0),
            If((dclkcnt < 40) | ~data_i2[0],
                If(dclkcnt < 40,
                    NextValue(dclkcnt, dclkcnt + 1),
                ),
                clk_en.eq(1)
            ).Else(
                NextValue(dclkcnt, 0),
                sink.ready.eq(1),
                NextState("IDLE")
            )
        )

        fsm.act("DATA_GETSTATUS_WAIT0",
            clk_en.eq(1),
            NextValue(data_t.oe, 0),
            NextState("DATA_GETSTATUS_WAIT1")
        )
        fsm.act("DATA_GETSTATUS_WAIT1",
            clk_en.eq(1),
            NextValue(data_t.oe, 0),
            NextState("DATA_GETSTATUS")
        )

        stcases = {} # For status read
        for i in range(7): # LSB is comb
            stcases[i] = NextValue(sttmpdata[6-i], data_i2[0])

        fsm.act("DATA_GETSTATUS",
            Case(stsel, stcases),
            If(stsel == 7,
                source.valid.eq(1),
                source.data.eq(0),
                status.eq(Cat(data_i2[0], sttmpdata)[1:4]),
                source.last.eq(1),
                If(source.valid & source.ready,
                    NextValue(stsel, 0),
                    NextState("DATA_CLK40_BUSY")
                )
            ).Else(
                NextValue(stsel, stsel + 1),
                clk_en.eq(1)
            )
        )
