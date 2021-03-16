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

        # Cmd Registers.
        self.cmd_argument = CSRStorage(32, description="SDCard Cmd Argument.")
        self.cmd_command  = CSRStorage(32, fields=[
            CSRField("cmd_type",  offset=0, size=2, description="Core/PHY Cmd transfer type."),
            CSRField("data_type", offset=5, size=2, description="Core/PHY Data transfer type."),
            CSRField("cmd",       offset=8, size=6, description="SDCard Cmd.")
        ])
        self.cmd_send     = CSRStorage(description="Run Cmd/Data transfer.")
        self.cmd_response = CSRStatus(128, description="SDCard Cmd Response.")

        # Cmd/Data Event Registers.
        self.cmd_event    = CSRStatus(4, fields=[
            CSRField("done",    size=1, description="Cmd transfer has been executed."),
            CSRField("error",   size=1, description="Cmd transfer has failed due to error(s)."),
            CSRField("timeout", size=1, description="Timeout error."),
            CSRField("crc",     size=1, description="CRC Error."), # FIXME: Generate/Connect.
        ])
        self.data_event   = CSRStatus(4, fields=[
            CSRField("done",    size=1, description="Data transfer has been executed."),
            CSRField("error",   size=1, description="Data transfer has failed due to error(s)."),
            CSRField("timeout", size=1, description="Timeout Error."),
            CSRField("crc",     size=1, description="CRC Error."), # FIXME: Generate/Connect.
        ])

        # Block Length/Count Registers.
        self.block_length = CSRStorage(10, description="Data transfer Block Length (in bytes).")
        self.block_count  = CSRStorage(32, description="Data transfer Block Count.")

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
        cmd_type     = Signal(2)
        cmd_count    = Signal(3)
        cmd_done     = Signal()
        cmd_error    = Signal()
        cmd_timeout  = Signal()

        data_type    = Signal(2)
        data_count   = Signal(32)
        data_done    = Signal()
        data_error   = Signal()
        data_timeout = Signal()

        cmd          = Signal(6)

        self.comb += [
            # Decode type of Cmd/Data from Register.
            cmd_type.eq(self.cmd_command.fields.cmd_type),
            data_type.eq(self.cmd_command.fields.data_type),
            cmd.eq(self.cmd_command.fields.cmd),

            # Encode Cmd Event to Register.
            self.cmd_event.fields.done.eq(cmd_done),
            self.cmd_event.fields.error.eq(cmd_error),
            self.cmd_event.fields.timeout.eq(cmd_timeout),
            self.cmd_event.fields.crc.eq(0),

            # Encode Data Event to Register.
            self.data_event.fields.done.eq(data_done),
            self.data_event.fields.error.eq(data_error),
            self.data_event.fields.timeout.eq(data_timeout),
            self.data_event.fields.crc.eq(0),

            # Prepare CRCInserter Data.
            crc7_inserter.din.eq(Cat(
                cmd_argument,
                cmd,
                1,
                0)),
            crc7_inserter.reset.eq(1),
            crc7_inserter.enable.eq(1),
        ]

        # Main FSM ---------------------------------------------------------------------------------
        self.submodules.fsm = fsm = FSM()
        fsm.act("IDLE",
            # Set Cmd/Data Done and clear Count.
            NextValue(cmd_done,   1),
            NextValue(data_done,  1),
            NextValue(cmd_count,  0),
            NextValue(data_count, 0),
            # Wait for a valid Cmd.
            If(cmd_send,
                # Clear Cmd/Data Done/Error/Timeout.
                NextValue(cmd_done,     0),
                NextValue(cmd_error,    0),
                NextValue(cmd_timeout,  0),
                NextValue(data_done,    0),
                NextValue(data_error,   0),
                NextValue(data_timeout, 0),
                NextState("CMD-SEND")
            )
        )
        fsm.act("CMD-SEND",
            # Send the Cmd to the PHY.
            phy.cmdw.sink.valid.eq(1),
            phy.cmdw.sink.last.eq(cmd_count == (6-1)), # 6 bytes / 48-bit.
            phy.cmdw.sink.cmd_type.eq(cmd_type),
            Case(cmd_count, {
                0: phy.cmdw.sink.data.eq(Cat(cmd, 1, 0)),
                1: phy.cmdw.sink.data.eq(cmd_argument[24:32]),
                2: phy.cmdw.sink.data.eq(cmd_argument[16:24]),
                3: phy.cmdw.sink.data.eq(cmd_argument[ 8:16]),
                4: phy.cmdw.sink.data.eq(cmd_argument[ 0: 8]),
                5: phy.cmdw.sink.data.eq(Cat(1, crc7_inserter.crc)),
               }
            ),
            # On a valid PHY cycle:
            If(phy.cmdw.sink.ready,
                # Increment count.
                NextValue(cmd_count, cmd_count + 1),
                # When the Cmd has been transfered:
                If(phy.cmdw.sink.last,
                    # If not expecting a response, return to Idle.
                    If(cmd_type == SDCARD_CTRL_RESPONSE_NONE,
                        NextState("IDLE")
                    # Else get the CMD Response.
                    ).Else(
                        NextState("CMD-RESPONSE"),
                    )
                )
            )
        )
        fsm.act("CMD-RESPONSE",
            # Set the Cmd Response information to the PHY.
            phy.cmdr.sink.valid.eq(1),
            phy.cmdr.sink.cmd_type.eq(cmd_type),
            phy.cmdr.sink.data_type.eq(data_type),
            If(cmd_type == SDCARD_CTRL_RESPONSE_LONG,
                # 136-bit + 8-bit shift to expose expected 128-bit window to software.
                phy.cmdr.sink.length.eq((136 + 8)//8)
            ).Else(
                # 48-bit.
                phy.cmdr.sink.length.eq(48//8)
            ),

            # Receive the Cmd Response from the PHY.
            phy.cmdr.source.ready.eq(1),
            If(phy.cmdr.source.valid,
                # On Timeout: set Cmd Timeout and return to Idle.
                If(phy.cmdr.source.status == SDCARD_STREAM_STATUS_TIMEOUT,
                    NextValue(cmd_timeout, 1),
                    NextState("IDLE")
                # On last Cmd byte:
                ).Elif(phy.cmdr.source.last,
                    # Send/Receive Data for Data Cmds.
                    If(data_type == SDCARD_CTRL_DATA_TRANSFER_WRITE,
                        NextState("DATA-WRITE")
                    ).Elif(data_type == SDCARD_CTRL_DATA_TRANSFER_READ,
                        NextState("DATA-READ")
                    # Else return to Idle.
                    ).Else(
                        NextState("IDLE")
                    ),
                # Else Shift Cmd Response.
                ).Else(
                    NextValue(cmd_response, Cat(phy.cmdr.source.data, cmd_response))
                )
            )
        )
        fsm.act("DATA-WRITE",
            # Send Data to the PHY (through CRC16 Inserter).
            crc16_inserter.source.connect(phy.dataw.sink),
            # On last PHY Data cycle:
            If(phy.dataw.sink.valid & phy.dataw.sink.ready & phy.dataw.sink.last,
                # Incremennt Data Count.
                NextValue(data_count, data_count + 1),
                # Transfer is done when Data Count reaches Block Count.
                If(data_count == (block_count - 1),
                    NextState("IDLE")
                )
            ),

            # Receive Status from the PHY.
            phy.datar.source.ready.eq(1),
            If(phy.datar.source.valid,
                # Set Data Error when Data has not been accepted.
                If(phy.datar.source.status != SDCARD_STREAM_STATUS_DATAACCEPTED,
                    NextValue(data_error, 1)
                )
            )
        )
        fsm.act("DATA-READ",
            # Send Data Response information to the PHY.
            phy.datar.sink.valid.eq(1),
            phy.datar.sink.block_length.eq(block_length),
            phy.datar.sink.last.eq(data_count == (block_count - 1)),

            # Receive Data Response and Status from the PHY.
            If(phy.datar.source.valid,
                # On valid Data:
                If(phy.datar.source.status == SDCARD_STREAM_STATUS_OK,
                    # Receive Data (through CRC16 Checker).
                    phy.datar.source.connect(crc16_checker.sink, omit={"status"}),
                    # On last Data:
                    If(phy.datar.source.last & phy.datar.source.ready,
                        # Increment Data Count.
                        NextValue(data_count, data_count + 1),
                        # Transfer is Done when Data Count reaches Block Count.
                        If(data_count == (block_count - 1),
                            NextState("IDLE")
                        )
                    )
                # On Timeout: set Data Timeout and return to Idle.
                ).Elif(phy.datar.source.status == SDCARD_STREAM_STATUS_TIMEOUT,
                    NextValue(data_timeout, 1),
                    phy.datar.source.ready.eq(1),
                    NextState("IDLE")
                )
            )
        )
