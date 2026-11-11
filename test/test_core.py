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


def _crc7(data):
    crc = 0
    for byte in data:
        for i in range(8):
            bit = ((byte >> (7 - i)) & 1) ^ ((crc >> 6) & 1)
            crc = (crc << 1) & 0x7f
            if bit:
                crc ^= 0x09
    return crc


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

    def _run_write_block_delimiter(self, block_length, block_count):
        phy = _FakePHY()
        dut = SDCore(phy)

        last_positions = []

        def host_gen():
            yield dut.block_length.storage.eq(block_length)
            yield dut.block_count.storage.eq(block_count)
            yield dut.cmd_command.fields.cmd_type.eq(SDCARD_CTRL_RESPONSE_SHORT)
            yield dut.cmd_command.fields.data_type.eq(SDCARD_CTRL_DATA_TRANSFER_WRITE)
            yield dut.cmd_command.fields.cmd.eq(25)
            yield dut.cmd_send.wr_stb.eq(1)
            yield
            yield dut.cmd_send.wr_stb.eq(0)

        def cmdw_gen():
            yield phy.cmdw.sink.ready.eq(1)
            for _ in range(32):
                yield

        def cmdr_gen():
            for _ in range(64):
                if (yield phy.cmdr.sink.valid):
                    break
                yield
            for i in range(6):
                yield phy.cmdr.source.status.eq(SDCARD_STREAM_STATUS_OK)
                yield phy.cmdr.source.last.eq(i == 5)
                yield phy.cmdr.source.valid.eq(1)
                yield
            yield phy.cmdr.source.valid.eq(0)

        def sink_gen():
            yield dut.sink.valid.eq(1)
            yield phy.dataw.sink.ready.eq(1)
            n = 0
            for _ in range(block_length*block_count + 256):
                if (yield phy.dataw.sink.valid) & (yield phy.dataw.sink.ready):
                    if (yield phy.dataw.sink.last):
                        last_positions.append(n)
                    n += 1
                    if n == block_length*block_count:
                        break
                yield
            yield dut.sink.valid.eq(0)

        run_simulation(dut, [host_gen(), cmdw_gen(), cmdr_gen(), sink_gen()])
        return last_positions

    def test_write_block_delimiter_512(self):
        last_positions = self._run_write_block_delimiter(block_length=512, block_count=2)
        self.assertEqual(last_positions, [511, 1023])

    def test_write_block_delimiter_above_512(self):
        last_positions = self._run_write_block_delimiter(block_length=1023, block_count=2)
        self.assertEqual(last_positions, [1022, 2045])

    def _run_cmd_response(self, response, status=SDCARD_STREAM_STATUS_OK, crc=1, cmd_type=SDCARD_CTRL_RESPONSE_SHORT, data_type=SDCARD_CTRL_DATA_TRANSFER_NONE):
        phy = _FakePHY()
        dut = SDCore(phy)
        idle = dut.fsm.ongoing("IDLE")

        cmd_event = []

        def host_gen():
            yield dut.cmd_command.fields.cmd_type.eq(cmd_type)
            yield dut.cmd_command.fields.crc.eq(crc)
            yield dut.cmd_command.fields.data_type.eq(data_type)
            yield dut.cmd_command.fields.cmd.eq(13)
            yield dut.block_length.storage.eq(512)
            yield dut.block_count.storage.eq(1)
            yield dut.cmd_send.wr_stb.eq(1)
            yield
            yield dut.cmd_send.wr_stb.eq(0)
            for _ in range(64):
                if (yield idle) == 0:
                    break
                yield
            for _ in range(64):
                if (yield idle) == 1:
                    break
                yield
            yield
            cmd_event.append({
                "done"    : (yield dut.cmd_event.fields.done),
                "error"   : (yield dut.cmd_event.fields.error),
                "timeout" : (yield dut.cmd_event.fields.timeout),
                "crc"     : (yield dut.cmd_event.fields.crc),
                "data_error" : (yield dut.data_event.fields.error),
            })

        def cmdw_gen():
            yield phy.cmdw.sink.ready.eq(1)
            for _ in range(32):
                yield

        def cmdr_gen():
            for _ in range(64):
                if (yield phy.cmdr.sink.valid):
                    break
                yield
            for i, data in enumerate(response):
                yield phy.cmdr.source.data.eq(data)
                yield phy.cmdr.source.status.eq(status)
                yield phy.cmdr.source.last.eq(i == len(response) - 1)
                yield phy.cmdr.source.valid.eq(1)
                yield
                while (yield phy.cmdr.source.ready) == 0:
                    yield
            yield phy.cmdr.source.valid.eq(0)

        run_simulation(dut, [host_gen(), cmdw_gen(), cmdr_gen()])
        self.assertEqual(len(cmd_event), 1)
        return cmd_event[0]

    def test_cmd_event_crc_ok(self):
        response = [0x0d, 0x00, 0x00, 0x09, 0x00]
        response.append((_crc7(response) << 1) | 1)
        event = self._run_cmd_response(response)
        self.assertEqual(event, {"done": 1, "error": 0, "timeout": 0, "crc": 0, "data_error": 0})

    def test_cmd_event_crc_error(self):
        response = [0x0d, 0x00, 0x00, 0x09, 0x00]
        response.append(((_crc7(response) ^ 0x01) << 1) | 1)
        event = self._run_cmd_response(response)
        self.assertEqual(event, {"done": 1, "error": 1, "timeout": 0, "crc": 1, "data_error": 0})

    def test_cmd_event_crc_long_response(self):
        cid      = list(range(0x10, 0x10 + 15))
        response = [0x3f] + cid + [(_crc7(cid) << 1) | 1] # R2: CRC7 over CID/CSD only.
        event = self._run_cmd_response(response, cmd_type=SDCARD_CTRL_RESPONSE_LONG)
        self.assertEqual(event, {"done": 1, "error": 0, "timeout": 0, "crc": 0, "data_error": 0})
        response[-1] ^= 0x02
        event = self._run_cmd_response(response, cmd_type=SDCARD_CTRL_RESPONSE_LONG)
        self.assertEqual(event, {"done": 1, "error": 1, "timeout": 0, "crc": 1, "data_error": 0})

    def test_cmd_event_crc_check_disabled(self):
        response = [0x3f, 0xff, 0xff, 0xff, 0xff, 0xff] # R3 (OCR): no CRC.
        event = self._run_cmd_response(response, crc=0)
        self.assertEqual(event, {"done": 1, "error": 0, "timeout": 0, "crc": 0, "data_error": 0})

    def test_cmd_event_crc_error_data_cmd(self):
        response = [0x11, 0x00, 0x00, 0x09, 0x00]
        response.append(((_crc7(response) ^ 0x01) << 1) | 1)
        for data_type in [SDCARD_CTRL_DATA_TRANSFER_READ, SDCARD_CTRL_DATA_TRANSFER_WRITE]:
            event = self._run_cmd_response(response, data_type=data_type)
            self.assertEqual(event, {"done": 1, "error": 1, "timeout": 0, "crc": 1, "data_error": 1})

    def test_cmd_event_timeout_data_cmd(self):
        event = self._run_cmd_response([0x00], status=SDCARD_STREAM_STATUS_TIMEOUT,
            data_type=SDCARD_CTRL_DATA_TRANSFER_READ)
        self.assertEqual(event, {"done": 1, "error": 1, "timeout": 1, "crc": 0, "data_error": 1})

    def test_cmd_event_timeout(self):
        event = self._run_cmd_response([0x00], status=SDCARD_STREAM_STATUS_TIMEOUT)
        self.assertEqual(event, {"done": 1, "error": 1, "timeout": 1, "crc": 0, "data_error": 0})


if __name__ == "__main__":
    unittest.main()
