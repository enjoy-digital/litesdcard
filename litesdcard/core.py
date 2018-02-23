from migen import *
from migen.genlib.cdc import MultiReg, BusSynchronizer, PulseSynchronizer

from litex.soc.interconnect import stream
from litex.soc.interconnect.csr import *

from litesdcard.common import *
from litesdcard.crc import CRC, CRCChecker
from litesdcard.crc import CRCDownstreamChecker, CRCUpstreamInserter


class SDCore(Module, AutoCSR):
    def __init__(self, phy):
        self.sink = stream.Endpoint([("data", 32)])
        self.source = stream.Endpoint([("data", 32)])

        self.argument = CSRStorage(32)
        self.command = CSRStorage(32)
        self.response = CSRStatus(120)

        self.cmdevt = CSRStatus(32)
        self.dataevt = CSRStatus(32)

        self.blocksize = CSRStorage(16)
        self.blockcount = CSRStorage(32)

        self.datatimeout = CSRStorage(32, reset=2**16)
        self.cmdtimeout = CSRStorage(32, reset=2**16)

        self.datawcrcclear = CSRStorage()
        self.datawcrcvalids = CSRStatus(32)
        self.datawcrcerrors = CSRStatus(32)

        # # #

        argument = Signal(32)
        command = Signal(32)
        response = Signal(120)
        cmdevt = Signal(32)
        dataevt = Signal(32)
        blocksize = Signal(16)
        blockcount = Signal(32)
        datatimeout = Signal(32)
        cmdtimeout = Signal(32)

        # sys to sd cdc
        self.specials += [
            MultiReg(self.argument.storage, argument, "sd"),
            MultiReg(self.command.storage, command, "sd"),
            MultiReg(self.blocksize.storage, blocksize, "sd"),
            MultiReg(self.blockcount.storage, blockcount, "sd"),
            MultiReg(self.datatimeout.storage, datatimeout, "sd"),
            MultiReg(self.cmdtimeout.storage, cmdtimeout, "sd")
        ]

        # sd to sys cdc
        response_cdc = BusSynchronizer(120, "sd", "sys")
        cmdevt_cdc = BusSynchronizer(32, "sd", "sys")
        dataevt_cdc = BusSynchronizer(32, "sd", "sys")
        self.submodules += response_cdc, cmdevt_cdc, dataevt_cdc
        self.comb += [
            response_cdc.i.eq(response),
            self.response.status.eq(response_cdc.o),
            cmdevt_cdc.i.eq(cmdevt),
            self.cmdevt.status.eq(cmdevt_cdc.o),
            dataevt_cdc.i.eq(dataevt),
            self.dataevt.status.eq(dataevt_cdc.o)
        ]

        self.submodules.new_command = PulseSynchronizer("sys", "sd")
        self.comb += self.new_command.i.eq(self.command.re)

        self.comb += [
            phy.cfg.blocksize.eq(blocksize),
            phy.cfg.datatimeout.eq(datatimeout),
            phy.cfg.cmdtimeout.eq(cmdtimeout),
            phy.dataw.crc_clear.eq(self.datawcrcclear.storage),
            self.datawcrcvalids.status.eq(phy.dataw.crc_valids),
            self.datawcrcerrors.status.eq(phy.dataw.crc_errors)
        ]

        self.submodules.crc7inserter = ClockDomainsRenamer("sd")(CRC(9, 7, 40))
        self.submodules.crc7checker = ClockDomainsRenamer("sd")(CRCChecker(9, 7, 120))
        self.submodules.crc16inserter = ClockDomainsRenamer("sd")(CRCUpstreamInserter())
        self.submodules.crc16checker = ClockDomainsRenamer("sd")(CRCDownstreamChecker())

        self.submodules.upstream_cdc = ClockDomainsRenamer({"write": "sys", "read": "sd"})(
            stream.AsyncFIFO(self.sink.description, 4))
        self.submodules.downstream_cdc = ClockDomainsRenamer({"write": "sd", "read": "sys"})(
            stream.AsyncFIFO(self.source.description, 4))

        self.submodules.upstream_converter = ClockDomainsRenamer("sd")(
            stream.StrideConverter([('data', 32)], [('data', 8)], reverse=True))
        self.submodules.downstream_converter = ClockDomainsRenamer("sd")(
            stream.StrideConverter([('data', 8)], [('data', 32)], reverse=True))

        self.comb += [
            self.sink.connect(self.upstream_cdc.sink),
            self.upstream_cdc.source.connect(self.upstream_converter.sink),
            self.upstream_converter.source.connect(self.crc16inserter.sink),

            self.crc16checker.source.connect(self.downstream_converter.sink),
            self.downstream_converter.source.connect(self.downstream_cdc.sink),
            self.downstream_cdc.source.connect(self.source)
        ]

        self.submodules.fsm = fsm = ClockDomainsRenamer("sd")(FSM())

        csel = Signal(max=6)
        waitresp = Signal(2)
        dataxfer = Signal(2)
        cmddone = Signal(reset=1)
        datadone = Signal(reset=1)
        blkcnt = Signal(32)
        pos = Signal(2)

        cerrtimeout = Signal()
        cerrcrc_en = Signal()
        derrtimeout = Signal()
        derrwrite = Signal()
        derrread_en = Signal()

        self.comb += [
            waitresp.eq(command[0:2]),
            dataxfer.eq(command[5:7]),
            cmdevt.eq(Cat(
                cmddone,
                C(0, 1),
                cerrtimeout,
                cerrcrc_en & ~self.crc7checker.valid)),
            dataevt.eq(Cat(
                datadone,
                derrwrite,
                derrtimeout,
                derrread_en & ~self.crc16checker.valid)),

            self.crc7inserter.val.eq(Cat(
                argument,
                command[8:14],
                1,
                0)),
            self.crc7inserter.clr.eq(1),
            self.crc7inserter.enable.eq(1),

            self.crc7checker.val.eq(response)
        ]

        ccases = {} # To send command and CRC
        ccases[0] = phy.sink.data.eq(Cat(command[8:14], 1, 0))
        for i in range(4):
            ccases[i+1] = phy.sink.data.eq(argument[24-8*i:32-8*i])
        ccases[5] = [
            phy.sink.data.eq(Cat(1, self.crc7inserter.crc)),
            phy.sink.last.eq(waitresp == SDCARD_CTRL_RESPONSE_NONE)
        ]

        fsm.act("IDLE",
            NextValue(pos, 0),
            If(self.new_command.o,
                NextValue(cmddone, 0),
                NextValue(cerrtimeout, 0),
                NextValue(cerrcrc_en, 0),
                NextValue(datadone, 0),
                NextValue(derrtimeout, 0),
                NextValue(derrwrite, 0),
                NextValue(derrread_en, 0),
                NextValue(response, 0),
                NextState("SEND_CMD")
            )
        )

        fsm.act("SEND_CMD",
            phy.sink.valid.eq(1),
            phy.sink.cmd_data_n.eq(1),
            phy.sink.rd_wr_n.eq(0),
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
            phy.sink.valid.eq(1),
            phy.sink.cmd_data_n.eq(1),
            phy.sink.rd_wr_n.eq(1),
            phy.sink.last.eq(dataxfer == SDCARD_CTRL_DATA_TRANSFER_NONE),
            If(waitresp == SDCARD_CTRL_RESPONSE_SHORT,
                phy.sink.data.eq(5) # (5+1)*8 == 48bits
            ).Elif(waitresp == SDCARD_CTRL_RESPONSE_LONG,
                phy.sink.data.eq(16) # (16+1)*8 == 136bits
            ),

            If(phy.source.valid, # Wait for resp or timeout coming from phy
                phy.source.ready.eq(1),
                If(phy.source.status == SDCARD_STREAM_STATUS_TIMEOUT,
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
                    NextValue(response,
                        Cat(phy.source.data, response[0:112]))
                )
            )
        )

        fsm.act("RECV_DATA",
            phy.sink.valid.eq(1),
            phy.sink.cmd_data_n.eq(0),
            phy.sink.rd_wr_n.eq(1),
            phy.sink.last.eq(blkcnt == (blockcount - 1)),
            phy.sink.data.eq(0), # Read 1 block

            If(phy.source.valid,
                phy.source.ready.eq(1),
                If(phy.source.status == SDCARD_STREAM_STATUS_OK,
                    self.crc16checker.sink.data.eq(phy.source.data), # Manual connect streams except ctrl
                    self.crc16checker.sink.valid.eq(phy.source.valid),
                    self.crc16checker.sink.last.eq(phy.source.last),
                    phy.source.ready.eq(self.crc16checker.sink.ready),

                    If(phy.source.last & phy.source.ready, # End of block
                        If(blkcnt < (blockcount - 1),
                            NextValue(blkcnt, blkcnt + 1),
                            NextState("RECV_DATA")
                        ).Else(
                            NextValue(blkcnt, 0),
                            NextValue(datadone, 1),
                            NextState("IDLE")
                        )
                    )
                ).Elif(phy.source.status == SDCARD_STREAM_STATUS_TIMEOUT,
                    NextValue(derrtimeout, 1),
                    NextValue(blkcnt, 0),
                    NextValue(datadone, 1),
                    phy.source.ready.eq(1),
                    NextState("IDLE")
                )
            )
        )

        fsm.act("SEND_DATA",
            phy.sink.valid.eq(self.crc16inserter.source.valid),
            phy.sink.cmd_data_n.eq(0),
            phy.sink.rd_wr_n.eq(0),
            phy.sink.last.eq(self.crc16inserter.source.last),
            phy.sink.data.eq(self.crc16inserter.source.data),
            self.crc16inserter.source.ready.eq(phy.sink.ready),

            If(self.crc16inserter.source.valid &
               self.crc16inserter.source.last &
               self.crc16inserter.source.ready,
                If(blkcnt < (blockcount - 1),
                    NextValue(blkcnt, blkcnt + 1)
                ).Else(
                    NextValue(blkcnt, 0),
                    NextValue(datadone, 1),
                    NextState("IDLE")
                )
            ),

            If(phy.source.valid,
                phy.source.ready.eq(1),
                If(phy.source.status != SDCARD_STREAM_STATUS_DATAACCEPTED,
                    NextValue(derrwrite, 1)
                )
            )
        )
