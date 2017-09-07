from litex.gen import *
from litex.soc.interconnect import stream
from litex.soc.interconnect.csr import *

from litesdcard.common import *
from litesdcard.crc import CRC, CRCChecker
from litesdcard.crc import CRCDownstreamChecker, CRCUpstreamInserter


class SDCore(Module, AutoCSR):
    def __init__(self, phy):
        self.sink = stream.Endpoint([("data", 8)])
        self.source = stream.Endpoint([("data", 8)])

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

        self.debug = Signal(4)

        # # #

        self.submodules.crc7 = CRC(9, 7, 40)
        self.submodules.crc7checker = CRCChecker(9, 7, 120)
        self.submodules.crc16 = CRCUpstreamInserter()
        self.submodules.crc16checker = CRCDownstreamChecker()
        self.comb += [
            self.sink.connect(self.crc16.sink),
            self.crc16checker.source.connect(self.source)
        ]

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

            phy.sink.ctrl.eq(Cat(cmddata, rdwr, mode)),
            status.eq(phy.source.ctrl[1:5]),

            self.crc7.val.eq(Cat(self.argument.storage,
                                 self.command.storage[8:14],
                                 1,
                                 0)),
            self.crc7.clr.eq(1),
            self.crc7.enable.eq(1),

            self.crc7checker.val.eq(self.response.status)
        ]

        ccases = {} # To send command and CRC
        ccases[0] = phy.sink.data.eq(Cat(self.command.storage[8:14], 1, 0))
        for i in range(4):
            ccases[i+1] = phy.sink.data.eq(self.argument.storage[24-8*i:32-8*i])
        ccases[5] = [
            phy.sink.data.eq(Cat(1, self.crc7.crc)),
            phy.sink.last.eq(waitresp == SDCARD_CTRL_RESPONSE_NONE)
        ]

        fsm.act("IDLE",
            self.debug.eq(0),
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
                phy.sink.data.eq(self.datatimeout.storage[24-(8*i):32-(8*i)]),
                mode.eq(SDCARD_STREAM_CFG_TIMEOUT_DATA_HH + i)
            ]
        ctcases = {}
        for i in range(4):
            ctcases[i] = [
                phy.sink.data.eq(self.cmdtimeout.storage[24-(8*i):32-(8*i)]),
                mode.eq(SDCARD_STREAM_CFG_TIMEOUT_CMD_HH + i)
            ]
        blkcases = {}
        for i in range(2):
            blkcases[i] = [
                phy.sink.data.eq(self.blocksize.storage[8-(8*i):16-(8*i)]),
                mode.eq(SDCARD_STREAM_CFG_BLKSIZE_H + i)
            ]

        fsm.act("CFG_TIMEOUT_DATA",
            self.debug.eq(1),
            phy.sink.valid.eq(1),
            Case(pos, dtcases),
            If(phy.sink.valid & phy.sink.ready,
                NextValue(pos, pos + 1),
                If(pos == 3,
                    NextState("IDLE")
                )
            )
        )

        fsm.act("CFG_TIMEOUT_CMD",
            self.debug.eq(2),
            phy.sink.valid.eq(1),
            Case(pos, ctcases),
            If(phy.sink.valid & phy.sink.ready,
                NextValue(pos, pos + 1),
                If(pos == 3,
                    NextState("IDLE")
                )
            )
        )

        fsm.act("CFG_BLKSIZE",
            self.debug.eq(3),
            phy.sink.valid.eq(1),
            Case(pos, blkcases),
            If(phy.sink.valid & phy.sink.ready,
                NextValue(pos, pos + 1),
                If(pos == 1,
                    NextState("IDLE")
                )
            )
        )

        fsm.act("CFG_VOLTAGE",
            self.debug.eq(4),
            phy.sink.valid.eq(1),
            phy.sink.data.eq(self.voltage.storage[0:8]),
            mode.eq(SDCARD_STREAM_CFG_VOLTAGE),
            If(phy.sink.valid & phy.sink.ready,
                NextState("IDLE")
            )
        )

        fsm.act("SEND_CMD",
            self.debug.eq(5),
            phy.sink.valid.eq(1),
            cmddata.eq(SDCARD_STREAM_CMD),
            rdwr.eq(SDCARD_STREAM_WRITE),
            mode.eq(SDCARD_STREAM_XFER),
            Case(csel, ccases),
            If(phy.sink.valid & phy.sink.ready,
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
            self.debug.eq(6),
            If(waitresp == SDCARD_CTRL_RESPONSE_SHORT,
                phy.sink.data.eq(5) # (5+1)*8 == 48bits
            ).Elif(waitresp == SDCARD_CTRL_RESPONSE_LONG,
                phy.sink.data.eq(16) # (16+1)*8 == 136bits
            ),
            phy.sink.valid.eq(1),
            phy.sink.last.eq(dataxfer == SDCARD_CTRL_DATA_TRANSFER_NONE),
            cmddata.eq(SDCARD_STREAM_CMD),
            rdwr.eq(SDCARD_STREAM_READ),
            mode.eq(SDCARD_STREAM_XFER),
            If(phy.source.valid, # Wait for resp or timeout coming from phy
                phy.source.ready.eq(1),
                If(phy.source.ctrl[0] == SDCARD_STREAM_CMD, # Should be always true
                    If(status == SDCARD_STREAM_STATUS_TIMEOUT,
                        NextValue(cerrtimeout, 1),
                        NextValue(cmddone, 1),
                        NextValue(datadone, 1),
                        NextState("IDLE")
                    ).Elif(phy.source.last,
                        # Check response CRC
                        NextValue(self.crc7checker.check, phy.source.data[1:8]),
                        NextValue(cmddone, 1),
                        If(dataxfer == SDCARD_CTRL_DATA_TRANSFER_READ,
                            NextValue(derrread_en, 1),
                            NextState("RECV_DATA")
                        ).Elif(dataxfer == SDCARD_CTRL_DATA_TRANSFER_WRITE,
                            NextState("SEND_DATA")
                        ).Else(
                            NextValue(datadone, 1),
                            NextState("IDLE")
                        ),
                    ).Else(
                        NextValue(self.response.status,
                            Cat(phy.source.data, self.response.status[0:112]))
                    )
                )
            )
        )

        fsm.act("RECV_DATA",
            self.debug.eq(7),
            phy.sink.data.eq(0), # Read 1 block
            phy.sink.valid.eq(1),
            phy.sink.last.eq(self.blockcount.storage == blkcnt),
            cmddata.eq(SDCARD_STREAM_DATA),
            rdwr.eq(SDCARD_STREAM_READ),
            mode.eq(SDCARD_STREAM_XFER),
            If(phy.sink.valid & phy.sink.ready,
                NextState("WAIT_DATA")
            )
        )

        fsm.act("WAIT_DATA",
            self.debug.eq(8),
            If(phy.source.valid,
                If(phy.source.ctrl[0] == SDCARD_STREAM_DATA, # Should be always true
                    If(status == SDCARD_STREAM_STATUS_OK,
                        self.crc16checker.sink.data.eq(phy.source.data), # Manual connect streams except ctrl
                        self.crc16checker.sink.valid.eq(phy.source.valid),
                        self.crc16checker.sink.last.eq(phy.source.last),
                        phy.source.ready.eq(self.crc16checker.sink.ready),

                        If(phy.source.last & phy.source.ready, # End of block
                            If(self.blockcount.storage > blkcnt,
                                NextValue(blkcnt, blkcnt + 1),
                                NextState("RECV_DATA")
                            ).Else(
                                NextValue(blkcnt, 0),
                                NextValue(datadone, 1),
                                NextState("IDLE")
                            )
                        )
                    ).Elif(status == SDCARD_STREAM_STATUS_TIMEOUT,
                        NextValue(derrtimeout, 1),
                        NextValue(blkcnt, 0),
                        NextValue(datadone, 1),
                        phy.source.ready.eq(1),
                        NextState("IDLE")
                    )
                ).Else(
                    phy.source.ready.eq(1),
                )
            )
        )

        fsm.act("SEND_DATA",
            self.debug.eq(9),
            phy.sink.data.eq(self.crc16.source.data),
            cmddata.eq(SDCARD_STREAM_DATA),
            rdwr.eq(SDCARD_STREAM_WRITE),
            mode.eq(SDCARD_STREAM_XFER),
            phy.sink.last.eq(self.crc16.source.last),
            phy.sink.valid.eq(self.crc16.source.valid),
            self.crc16.source.ready.eq(phy.sink.ready),

            If(self.crc16.source.valid &
               self.crc16.source.last &
               self.crc16.source.ready,
                If(self.blockcount.storage > blkcnt,
                    NextValue(blkcnt, blkcnt + 1)
                ).Else(
                    NextValue(blkcnt, 0),
                    NextValue(datadone, 1),
                    NextState("IDLE")
                )
            ),

            If(phy.source.valid,
                phy.source.ready.eq(1),
                If(status != SDCARD_STREAM_STATUS_DATAACCEPTED,
                    NextValue(derrwrite, 1)
                )
            )
        )
