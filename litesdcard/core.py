#
# This file is part of LiteSDCard.
#
# Copyright (c) 2017-2020 Florent Kermarrec <florent@enjoy-digital.fr>
# Copyright (c) 2017 Pierre-Olivier Vauboin <po@lambdaconcept.com>
# Copyright (c) 2018 bunnie <bunnie@kosagi.com>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *
from migen.genlib.cdc import MultiReg

from litex.soc.interconnect.csr import *
from litex.soc.interconnect import stream

from litesdcard.common import *
from litesdcard.crc import CRC
from litesdcard.crc import CRC16Checker, CRC16Inserter

# SDCore -------------------------------------------------------------------------------------------

class SDCore(Module, AutoCSR):
    def __init__(self, phy):
        self.sink   = stream.Endpoint([("data", 8)])
        self.source = stream.Endpoint([("data", 8)])

        self.cmd_argument = CSRStorage(32)
        self.cmd_command  = CSRStorage(32)
        self.cmd_send     = CSR()
        self.cmd_response = CSRStatus(128)

        self.cmd_event    = CSRStatus(4)
        self.data_event   = CSRStatus(4)

        self.block_length = CSRStorage(10)
        self.block_count  = CSRStorage(32)

        # # #

        # Register Mapping -------------------------------------------------------------------------
        cmd_argument = self.cmd_argument.storage
        cmd_command  = self.cmd_command.storage
        cmd_send     = self.cmd_send.re
        cmd_response = self.cmd_response.status
        cmd_event    = self.cmd_event.status
        data_event   = self.data_event.status
        block_length = self.block_length.storage
        block_count  = self.block_count.storage

        # CRC Inserter/Checkers --------------------------------------------------------------------
        self.submodules.crc7_inserter  = crc7_inserter  = CRC(polynom=0x9, taps=7, dw=40)
        self.submodules.crc16_inserter = crc16_inserter = CRC16Inserter()
        self.submodules.crc16_checker  = crc16_checker  = CRC16Checker()
        self.comb += self.sink.connect(crc16_inserter.sink)
        self.comb += crc16_checker.source.connect(self.source)

        # Cmd/Data Signals -------------------------------------------------------------------------
        cmd_type    = Signal(2)
        cmd_count   = Signal(3)
        cmd_done    = Signal()
        cmd_error   = Signal()
        cmd_timeout = Signal()

        data_type    = Signal(2)
        data_count   = Signal(32)
        data_done    = Signal()
        data_error   = Signal()
        data_timeout = Signal()

        self.comb += [
            cmd_type.eq(cmd_command[0:2]),
            data_type.eq(cmd_command[5:7]),
            cmd_event.eq(Cat(
                cmd_done,
                cmd_error,
                cmd_timeout,
                0)), # FIXME cmd_response CRC.
            data_event.eq(Cat(
                data_done,
                data_error,
                data_timeout,
                0)), # FIXME data_response CRC.
            crc7_inserter.din.eq(Cat(
                cmd_argument,
                cmd_command[8:14],
                1,
                0)),
            crc7_inserter.reset.eq(1),
            crc7_inserter.enable.eq(1),
        ]

        # Main FSM ---------------------------------------------------------------------------------
        self.submodules.fsm = fsm = FSM()
        fsm.act("IDLE",
            NextValue(cmd_done,   1),
            NextValue(data_done,  1),
            NextValue(cmd_count,  0),
            NextValue(data_count, 0),
            If(cmd_send,
                NextValue(cmd_done,     0),
                NextValue(cmd_error,    0),
                NextValue(cmd_timeout,  0),
                NextValue(data_done,    0),
                NextValue(data_error,   0),
                NextValue(data_timeout, 0),
                NextState("CMD")
            )
        )
        fsm.act("CMD",
            phy.cmdw.sink.valid.eq(1),
            Case(cmd_count, {
                0: phy.cmdw.sink.data.eq(Cat(cmd_command[8:14], 1, 0)),
                1: phy.cmdw.sink.data.eq(cmd_argument[24:32]),
                2: phy.cmdw.sink.data.eq(cmd_argument[16:24]),
                3: phy.cmdw.sink.data.eq(cmd_argument[ 8:16]),
                4: phy.cmdw.sink.data.eq(cmd_argument[ 0: 8]),
                5: [phy.cmdw.sink.data.eq(Cat(1, crc7_inserter.crc)),
                    phy.cmdw.sink.last.eq(cmd_type == SDCARD_CTRL_RESPONSE_NONE)]
               }
            ),
            If(phy.cmdw.sink.valid & phy.cmdw.sink.ready,
                NextValue(cmd_count, cmd_count + 1),
                If(cmd_count == (6-1),
                    If(cmd_type == SDCARD_CTRL_RESPONSE_NONE,
                        NextValue(cmd_done, 1),
                        NextState("IDLE")
                    ).Else(
                        NextState("CMD-RESPONSE"),
                    )
                )
            )
        )
        fsm.act("CMD-RESPONSE",
            phy.cmdr.sink.valid.eq(1),
            phy.cmdr.sink.last.eq(data_type == SDCARD_CTRL_DATA_TRANSFER_NONE),
            If(cmd_type == SDCARD_CTRL_RESPONSE_LONG,
                phy.cmdr.sink.length.eq(17+1) # 136bits + 8bit shift to expose expected 128-bit window to software
            ).Else(
                phy.cmdr.sink.length.eq(6)  # 48bits
            ),
            phy.cmdr.source.ready.eq(1),
            If(phy.cmdr.source.valid,
                If(phy.cmdr.source.status == SDCARD_STREAM_STATUS_TIMEOUT,
                    NextValue(cmd_timeout, 1),
                    NextState("IDLE")
                ).Elif(phy.cmdr.source.last,
                    If(data_type == SDCARD_CTRL_DATA_TRANSFER_WRITE,
                        NextState("DATA-WRITE")
                    ).Elif(data_type == SDCARD_CTRL_DATA_TRANSFER_READ,
                        NextState("DATA-READ")
                    ).Else(
                        NextState("IDLE")
                    ),
                ).Else(
                    NextValue(cmd_response, Cat(phy.cmdr.source.data, cmd_response))
                )
            )
        )
        fsm.act("DATA-WRITE",
            crc16_inserter.source.connect(phy.dataw.sink),
            If(phy.dataw.sink.valid &
                phy.dataw.sink.last &
                phy.dataw.sink.ready,
                NextValue(data_count, data_count + 1),
                If(data_count == (block_count - 1),
                    NextState("IDLE")
                )
            ),
            phy.datar.source.ready.eq(1),
            If(phy.datar.source.valid,
                If(phy.datar.source.status != SDCARD_STREAM_STATUS_DATAACCEPTED,
                    NextValue(data_error, 1)
                )
            )
        )
        fsm.act("DATA-READ",
            phy.datar.sink.valid.eq(1),
            phy.datar.sink.block_length.eq(block_length),
            phy.datar.sink.last.eq(data_count == (block_count - 1)),
            If(phy.datar.source.valid,
                If(phy.datar.source.status == SDCARD_STREAM_STATUS_OK,
                    phy.datar.source.connect(crc16_checker.sink, omit={"status"}),
                    If(phy.datar.source.last & phy.datar.source.ready,
                        NextValue(data_count, data_count + 1),
                        If(data_count == (block_count - 1),
                            NextState("IDLE")
                        ).Else(
                            NextState("DATA-READ")
                        )
                    )
                ).Elif(phy.datar.source.status == SDCARD_STREAM_STATUS_TIMEOUT,
                    NextValue(data_timeout, 1),
                    NextValue(data_count, 0),
                    phy.datar.source.ready.eq(1),
                    NextState("IDLE")
                )
            )
        )
