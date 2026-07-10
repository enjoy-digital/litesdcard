#
# This file is part of LiteSDCard.
#
# Copyright (c) 2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import unittest

from migen import *

from litex.soc.interconnect import stream

from litesdcard.common import *
from litesdcard.core import SDCore


class _FakePHY:
    def __init__(self):
        self.cmdw = _EndpointPair(
            sink_layout=[("data", 8), ("cmd_type", 2)],
        )
        self.cmdr = _EndpointPair(
            sink_layout=[("cmd_type", 2), ("data_type", 2), ("length", 8)],
            source_layout=[("data", 8), ("status", 3)],
        )
        self.dataw = _EndpointPair(
            sink_layout=[("data", 8), ("last_block", 1)],
            source_layout=[("status", 3)],
        )
        self.datar = _EndpointPair(
            sink_layout=[("block_length", 10)],
            source_layout=[("data", 8), ("status", 3), ("drop", 1)],
        )


class _EndpointPair:
    def __init__(self, sink_layout, source_layout=None):
        self.sink = stream.Endpoint(sink_layout)
        if source_layout is not None:
            self.source = stream.Endpoint(source_layout)


class TestSDCore(unittest.TestCase):
    def test_read_data_reception_starts_during_cmd_response(self):
        phy = _FakePHY()
        dut = SDCore(phy)

        early_datar_start = []
        read_data         = []

        def host_gen():
            yield dut.block_length.storage.eq(1)
            yield dut.block_count.storage.eq(1)
            yield dut.cmd_command.fields.cmd_type.eq(SDCARD_CTRL_RESPONSE_SHORT)
            yield dut.cmd_command.fields.data_type.eq(SDCARD_CTRL_DATA_TRANSFER_READ)
            yield dut.cmd_command.fields.cmd.eq(17)
            yield dut.source.ready.eq(1)
            yield dut.cmd_send.wr_stb.eq(1)
            yield
            yield dut.cmd_send.wr_stb.eq(0)

            for _ in range(128):
                if (yield dut.source.valid):
                    read_data.append((yield dut.source.data))
                    break
                yield

        def cmdw_gen():
            yield phy.cmdw.sink.ready.eq(1)
            for _ in range(128):
                yield

        def cmdr_gen():
            response = [0x11, 0x22, 0x33, 0x44, 0x55, 0x66]
            while (yield phy.cmdr.sink.valid) == 0:
                yield

            for i, data in enumerate(response):
                yield phy.cmdr.source.data.eq(data)
                yield phy.cmdr.source.status.eq(SDCARD_STREAM_STATUS_OK)
                yield phy.cmdr.source.last.eq(i == len(response) - 1)
                yield phy.cmdr.source.valid.eq(1)
                if i < len(response) - 1 and (yield phy.datar.sink.valid):
                    early_datar_start.append(True)
                yield
                while (yield phy.cmdr.source.ready) == 0:
                    yield
                yield phy.cmdr.source.valid.eq(0)
                yield

        def datar_gen():
            while (yield phy.datar.sink.valid) == 0:
                yield

            yield phy.datar.source.data.eq(0xa5)
            yield phy.datar.source.status.eq(SDCARD_STREAM_STATUS_OK)
            yield phy.datar.source.drop.eq(0)
            yield phy.datar.source.first.eq(1)
            yield phy.datar.source.last.eq(1)
            yield phy.datar.source.valid.eq(1)
            while (yield phy.datar.source.ready) == 0:
                yield
            yield phy.datar.sink.ready.eq(1)
            yield
            yield phy.datar.source.valid.eq(0)
            yield phy.datar.sink.ready.eq(0)

        run_simulation(dut, [host_gen(), cmdw_gen(), cmdr_gen(), datar_gen()])

        self.assertEqual(early_datar_start, [True])
        self.assertEqual(read_data, [0xa5])


if __name__ == "__main__":
    unittest.main()
