#
# This file is part of LiteSDCard.
#
# Copyright (c) 2017-2023 Florent Kermarrec <florent@enjoy-digital.fr>
# Copyright (c) 2017 Pierre-Olivier Vauboin <po@lambdaconcept.com>
# Copyright (c) 2018 bunnie <bunnie@kosagi.com>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *
from migen.genlib.cdc import MultiReg

from litex.gen import *

from litex.soc.interconnect.csr import *
from litex.soc.interconnect import stream

from litesdcard.common import *
from litesdcard.crc import CRC

# SDCore -------------------------------------------------------------------------------------------

class SDCore(LiteXModule):
    def __init__(self, phy):
        self.sink   = stream.Endpoint([("data", 8)])
        self.source = stream.Endpoint([("data", 8)])
        self.irq = Signal()

        # Cmd Registers.
        self.cmd_argument = CSRStorage(32, description="SDCard Cmd Argument.")
        self.cmd_command  = CSRStorage(32, fields=[
            CSRField("cmd_type",  offset=0, size=2, description="Core/PHY Cmd transfer type."),
            CSRField("crc",       offset=2, size=1, description="Enable CRC7 check for response."),
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
            CSRField("crc",     size=1, description="CRC Error."),
        ])
        self.data_event   = CSRStatus(4, fields=[
            CSRField("done",    size=1, description="Data transfer has been executed."),
            CSRField("error",   size=1, description="Data transfer has failed due to error(s)."),
            CSRField("timeout", size=1, description="Timeout Error."),
            CSRField("crc",     size=1, description="CRC Error."),
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
        self.crc7_inserter  = crc7_inserter  = CRC(polynom=0x9, taps=7, dw=8)

        # Cmd/Data Signals -------------------------------------------------------------------------
        cmd_type     = Signal(2)
        cmd_crc_en   = Signal()
        cmd_count    = Signal(3)
        cmd_done     = Signal()
        cmd_error    = Signal()
        cmd_timeout  = Signal()
        cmd_crc      = Signal()

        data_type    = Signal(2)
        data_count   = Signal(32)
        data_done    = Signal()
        data_error   = Signal()
        data_timeout = Signal()
        data_crc     = Signal()

        cmd          = Signal(6)

        self.comb += [
            # Decode type of Cmd/Data from Register.
            cmd_type.eq(self.cmd_command.fields.cmd_type),
            cmd_crc_en.eq(self.cmd_command.fields.crc),
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
            self.data_event.fields.crc.eq(data_crc),
        ]

        # Block delimiter for DATA-WRITE
        count = Signal(9)
        self.sync += [
            If(self.sink.valid & self.sink.ready,
                count.eq(count + 1),
                If(self.sink.last, count.eq(0))
            )
        ]
        self.comb += If(count == (block_length - 1), self.sink.last.eq(1))

        # IRQ / Generate IRQ on CMD done rising edge
        done_d     = Signal()
        self.sync += done_d.eq(cmd_done)
        self.sync += self.irq.eq(cmd_done & ~done_d)

        # Main FSM ---------------------------------------------------------------------------------
        self.fsm = fsm = FSM()
        fsm.act("IDLE",
            # Set Cmd/Data Done and clear Count.
            NextValue(cmd_done,   1),
            NextValue(data_done,  1),
            NextValue(cmd_count,  0),
            NextValue(data_count, 0),
            crc7_inserter.reset.eq(1),
            # Wait for a valid Cmd.
            If(cmd_send,
                # Clear Cmd/Data Done/Error/Timeout.
                NextValue(cmd_done,     0),
                NextValue(cmd_error,    0),
                NextValue(cmd_timeout,  0),
                NextValue(cmd_crc,      0),
                NextValue(data_done,    0),
                NextValue(data_error,   0),
                NextValue(data_timeout, 0),
                NextValue(data_crc,     0),
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
            crc7_inserter.din.eq(phy.cmdw.sink.data),
            # On a valid PHY cycle:
            If(phy.cmdw.sink.ready,
                # Increment count.
                NextValue(cmd_count, cmd_count + 1),
                # When the Cmd has been transfered:
                If(phy.cmdw.sink.last,
                    crc7_inserter.reset.eq(1),
                    # If not expecting a response, return to Idle.
                    If(cmd_type == SDCARD_CTRL_RESPONSE_NONE,
                        NextState("IDLE")
                    # Else get the CMD Response.
                    ).Else(
                        NextValue(cmd_count,  0),
                        NextState("CMD-RESPONSE"),
                    )
                ).Else(
                    crc7_inserter.enable.eq(1),
                )
            )
        )
        fsm.act("CMD-RESPONSE",
            # Set the Cmd Response information to the PHY.
            phy.cmdr.sink.valid.eq(1),
            phy.cmdr.sink.cmd_type.eq(cmd_type),
            phy.cmdr.sink.data_type.eq(data_type),
            If(cmd_type == SDCARD_CTRL_RESPONSE_LONG,
                # 136-bit, 17 bytes.
                phy.cmdr.sink.length.eq(136//8)
            ).Else(
                # 48-bit 6 bytes.
                phy.cmdr.sink.length.eq(48//8)
            ),

            # Receive the Cmd Response from the PHY.
            phy.cmdr.source.ready.eq(1),
            crc7_inserter.din.eq(phy.cmdr.source.data),
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
                    If(cmd_type == SDCARD_CTRL_RESPONSE_LONG,
                        # 8-bit shift to expose expected 128-bit window to software.
                        NextValue(cmd_response, Cat(phy.cmdr.source.data, cmd_response)),
                    ),
                    If(cmd_crc_en & (crc7_inserter.crc != phy.cmdr.source.data[1:]),
                        # If CRC check enabled and CRC bad, set Cmd Error/CRC and return to Idle
                        NextValue(cmd_crc, 1),
                        NextState("IDLE"),
                    ),
                # Else Shift Cmd Response.
                ).Else(
                    If(cmd_count == 0,
                        NextValue(cmd_count, 1),
                    ),
                    # Skip first byte for long response. Forlong response, we check 120 bits only (without CRC).
                    crc7_inserter.enable.eq(Mux(cmd_type == SDCARD_CTRL_RESPONSE_LONG, cmd_count > 0, 1)),
                    NextValue(cmd_response, Cat(phy.cmdr.source.data, cmd_response))
                )
            )
        )
        fsm.act("DATA-WRITE",
            # Send Data to the PHY.
            self.sink.connect(phy.dataw.sink),
            phy.dataw.sink.last_block.eq(data_count == (block_count - 1)),
            # On last PHY Data cycle:
            If(phy.dataw.sink.valid & phy.dataw.sink.ready & phy.dataw.sink.last,
                # Incremennt Data Count.
                NextValue(data_count, data_count + 1),
                # Transfer is done when Data Count reaches Block Count.
                If(phy.dataw.sink.last_block,
                    NextState("IDLE")
                )
            ),

            # Receive Status from the PHY.
            phy.dataw.source.ready.eq(1),
            If(phy.dataw.source.valid,
                # Set Data Error when Data has not been accepted.
                If(phy.dataw.source.status == SDCARD_STREAM_STATUS_CRCERROR,
                    NextValue(data_crc, 1)
                ).Elif(phy.dataw.source.status != SDCARD_STREAM_STATUS_DATAACCEPTED,
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
                If((phy.datar.source.status == SDCARD_STREAM_STATUS_OK) |
                   (phy.datar.source.status == SDCARD_STREAM_STATUS_CRCERROR),
                    # Receive Data and drop CRC part.
                    If(phy.datar.source.drop,
                        phy.datar.source.ready.eq(1)
                    ).Else(
                        phy.datar.source.connect(self.source, omit={"status", "drop"}),
                    ),
                    # On last Data:
                    If(phy.datar.source.last & phy.datar.source.ready,
                        # Increment Data Count.
                        NextValue(data_count, data_count + 1),
                        # Transfer is Done when Data Count reaches Block Count.
                        If(data_count == (block_count - 1),
                            NextState("IDLE")
                        )
                    ),
                    If(phy.dataw.source.status == SDCARD_STREAM_STATUS_CRCERROR,
                        NextValue(data_crc, 1),
                    ),
                # On Timeout: set Data Timeout and return to Idle.
                ).Elif(phy.datar.source.status == SDCARD_STREAM_STATUS_TIMEOUT,
                    NextValue(data_timeout, 1),
                    phy.datar.source.ready.eq(1),
                    NextState("IDLE")
                )
            )
        )
