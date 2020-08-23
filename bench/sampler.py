#!/usr/bin/env python3

#
# This file is part of LiteSDCard.
#
# Copyright (c) 2020 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import socket
import argparse

from migen import *

from migen.genlib.cdc import MultiReg

from litex.soc.interconnect.csr import *
from litex.soc.interconnect import stream

# Gateware -----------------------------------------------------------------------------------------

class Sampler(Module, AutoCSR):
    def __init__(self, pads):
        self.enable        = CSRStorage()
        self.pattern       = CSRStorage()
        self.state         = CSRStatus(fields=[
            CSRField("idle",    offset=0),
            CSRField("trigger", offset=1),
            CSRField("capture", offset=2),
        ])
        self.trig_value          = CSRStorage(8)
        self.trig_mask           = CSRStorage(8)
        self.sample_count        = CSRStorage(32)
        self.sample_downsampling = CSRStorage(16, reset=1)
        self.source              = stream.Endpoint([("data", 8)])

        # # #

        # Resynchronize data in sys_clk domain.
        data_pads = Signal(8)
        self.specials += MultiReg(pads, data_pads, n=2)

        # Generate data pattern.
        data_pattern = Signal(8)
        self.sync += data_pattern.eq(data_pattern + 1)

        # Select data.
        data = Signal(8)
        self.sync += [
            If(self.pattern.storage,
                data.eq(data_pads)
            ).Else(
                data.eq(data_pattern)
            )
        ]

        # Main FSM.
        count        = Signal(32)
        downsampling = Signal(16)
        fsm   = FSM(reset_state="IDLE")
        fsm   = ResetInserter()(fsm)
        self.submodules += fsm
        self.comb += fsm.reset.eq(~self.enable.storage)
        fsm.act("IDLE",
            self.state.fields.idle.eq(1),
            NextValue(count, 0),
            NextValue(downsampling, 0),
            NextState("TRIGGER")
        )
        fsm.act("TRIGGER",
            self.state.fields.trigger.eq(1),
            If((data & self.trig_mask.storage) == (self.trig_value.storage & self.trig_mask.storage),
                NextState("CAPTURE")
            )
        )
        fsm.act("CAPTURE",
            self.state.fields.capture.eq(1),
            If(downsampling == (self.sample_downsampling.storage - 1),
                self.source.valid.eq(1),
                NextValue(downsampling, 0)
            ).Else(
                NextValue(downsampling, downsampling + 1)
            ),
            self.source.data.eq(data),
            If(self.source.valid & self.source.ready,
                NextValue(count, count + 1),
                If(count == (self.sample_count.storage - 1),
                    NextState("IDLE")
                )
            )
        )

# Software -----------------------------------------------------------------------------------------

if __name__ == '__main__':
    from litex import RemoteClient
    parser = argparse.ArgumentParser()
    parser.add_argument("--value",        default="0",         help="Trigger Value.")
    parser.add_argument("--mask",         default="0",         help="Trigger Mask.")
    parser.add_argument("--count",        default="1e3",       help="Sample Count.")
    parser.add_argument("--downsampling", default="1",         help="Sample Downsampling.")
    parser.add_argument("--pattern",      action="store_true", help="Enable Pattern.")
    args = parser.parse_args()

    wb = RemoteClient()
    wb.open()

    # # #

    def num(s):
        try:
            return int(s, 0)
        except ValueError:
            return int(float(s))

    class Sampler:
        def set_pattern(self, enable):
            wb.regs.sampler_pattern.write(enable)

        def run(self, trig_value=0, trig_mask=0, sample_count=int(1e6), sample_downsampling=1):
            # Disable Sampler
            wb.regs.sampler_enable.write(0)

            # Configure trigger
            wb.regs.sampler_trig_value.write(trig_value)
            wb.regs.sampler_trig_mask.write(trig_mask)

            # Configure count/downsampling
            wb.regs.sampler_sample_count.write(sample_count)
            wb.regs.sampler_sample_downsampling.write(sample_downsampling)

            # Enable Sampler
            wb.regs.sampler_enable.write(1)

            # Capture
            data_count = 0
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(("192.168.1.100", 2000))
            f = open("data.bin", "wb")
            while data_count < sample_count:
                print(data_count)
                data, addr = sock.recvfrom(1024)

                f.write(data)
                data_count += len(data)

            # Disable Sampler
            wb.regs.sampler_enable.write(0)

    sampler = Sampler()
    sampler.set_pattern(int(args.pattern))
    sampler.run(
        trig_value          = num(args.value),
        trig_mask           = num(args.mask),
        sample_count        = num(args.count),
        sample_downsampling = num(args.downsampling)
    )

    # # #

    wb.close()
