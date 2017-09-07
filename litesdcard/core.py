from litex.gen import *
from litex.soc.interconnect import stream
from litex.soc.interconnect.csr import *

from litesdcard.common import *
from litesdcard.crc import CRC, CRCChecker
from litesdcard.crc import CRCDownstreamChecker, CRCUpstreamInserter


class SDCore(Module, AutoCSR):
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

        self.sink = sink = stream.Endpoint([("data", 8), ("ctrl", 8)])
        self.source = source = stream.Endpoint([("data", 8), ("ctrl", 8)])

        # # #

        self.submodules.crc7 = CRC(9, 7, 40)
        self.submodules.crc7checker = CRCChecker(9, 7, 120)
        self.submodules.crc16 = CRCUpstreamInserter()
        self.submodules.crc16checker = CRCDownstreamChecker()

        self.rsink = self.crc16.sink
        self.rsource = self.crc16checker.source

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
        ctcases = {}
        for i in range(4):
            ctcases[i] = [
                source.data.eq(self.cmdtimeout.storage[24-(8*i):32-(8*i)]),
                mode.eq(SDCARD_STREAM_CFG_TIMEOUT_CMD_HH + i)
            ]
        blkcases = {}
        for i in range(2):
            blkcases[i] = [
                source.data.eq(self.blocksize.storage[8-(8*i):16-(8*i)]),
                mode.eq(SDCARD_STREAM_CFG_BLKSIZE_H + i)
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
                NextState("IDLE")
            )
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
            If(source.valid & source.ready, # In async fifo
                NextState("WAIT_RESP")
            )
        )

        fsm.act("WAIT_RESP",
            If(sink.valid, # Wait for resp or timeout coming from phy
                sink.ready.eq(1),
                If(sink.ctrl[0] == SDCARD_STREAM_CMD, # Should be always true
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
                        ),
                    ).Else(
                        NextValue(self.response.status,
                            Cat(sink.data, self.response.status[0:112]))
                    )
                )
            )
        )

        fsm.act("RECV_DATA",
            source.data.eq(0), # Read 1 block
            source.valid.eq(1),
            source.last.eq(self.blockcount.storage == blkcnt),
            cmddata.eq(SDCARD_STREAM_DATA),
            rdwr.eq(SDCARD_STREAM_READ),
            mode.eq(SDCARD_STREAM_XFER),
            If(source.valid & source.ready,
                NextState("WAIT_DATA")
            )
        )

        fsm.act("WAIT_DATA",
            If(sink.valid,
                If(sink.ctrl[0] == SDCARD_STREAM_DATA, # Should be always true
                    If(status == SDCARD_STREAM_STATUS_OK,
                        self.crc16checker.sink.data.eq(sink.data), # Manual connect streams except ctrl
                        self.crc16checker.sink.valid.eq(sink.valid),
                        self.crc16checker.sink.last.eq(sink.last),
                        sink.ready.eq(self.crc16checker.sink.ready),

                        If(sink.last & sink.ready, # End of block
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
                        sink.ready.eq(1),
                        NextState("IDLE")
                    )
                ).Else(
                    sink.ready.eq(1),
                )
            )
        )

        fsm.act("SEND_DATA",
            source.data.eq(self.crc16.source.data),
            cmddata.eq(SDCARD_STREAM_DATA),
            rdwr.eq(SDCARD_STREAM_WRITE),
            mode.eq(SDCARD_STREAM_XFER),
            source.last.eq(self.crc16.source.last),
            source.valid.eq(self.crc16.source.valid),
            self.crc16.source.ready.eq(source.ready),

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

            If(sink.valid,
                sink.ready.eq(1),
                If(status != SDCARD_STREAM_STATUS_DATAACCEPTED,
                    NextValue(derrwrite, 1)
                )
            )
        )
