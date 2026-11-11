#
# This file is part of LiteSDCard.
#
# Copyright (c) 2020 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import unittest

from migen import *

from litesdcard.phy import *
from litesdcard.phy import _sdpads_layout

def c2bool(c):
    return {"-": 1, "_": 0}[c]


class TestPHY(unittest.TestCase):
    def test_clocker_div0(self):
        # Effective Div = 2.
        def gen(dut):
            clk   = "__-_-_-_-_-_-_-_"
            ce    = "_-_-_-_-_-_-_-_-"
            for i in range(len(clk)):
                self.assertEqual(c2bool(clk[i]),   (yield dut.clk))
                self.assertEqual(c2bool(ce[i]),    (yield dut.ce))
                yield
        dut = SDPHYClocker()
        dut.divider.storage.reset = 0
        run_simulation(dut, gen(dut))

    def test_clocker_div1(self):
        # Effective Div = 2.
        def gen(dut):
            clk   = "__-_-_-_-_-_-_-_"
            ce    = "_-_-_-_-_-_-_-_-"
            for i in range(len(clk)):
                self.assertEqual(c2bool(clk[i]),   (yield dut.clk))
                self.assertEqual(c2bool(ce[i]),    (yield dut.ce))
                yield
        dut = SDPHYClocker()
        dut.divider.storage.reset = 1
        run_simulation(dut, gen(dut))

    def test_clocker_div2(self):
        # Effective Div = 2.
        def gen(dut):
            clk   = "__-_-_-_-_-_-_-_"
            ce    = "_-_-_-_-_-_-_-_-"
            for i in range(len(clk)):
                self.assertEqual(c2bool(clk[i]),   (yield dut.clk))
                self.assertEqual(c2bool(ce[i]),    (yield dut.ce))
                yield
        dut = SDPHYClocker()
        dut.divider.storage.reset = 2
        run_simulation(dut, gen(dut))

    def test_clocker_div3(self):
        # Effective Div = 4.
        def gen(dut):
            clk   = "___--__--__--__--"
            ce    = "_-___-___-___-___"
            for i in range(len(clk)):
                self.assertEqual(c2bool(clk[i]),   (yield dut.clk))
                self.assertEqual(c2bool(ce[i]),    (yield dut.ce))
                yield
        dut = SDPHYClocker()
        dut.divider.storage.reset = 3
        run_simulation(dut, gen(dut))

    def test_clocker_div4(self):
        # Effective Div = 4.
        def gen(dut):
            clk   = "___--__--__--__--"
            ce    = "_-___-___-___-___"
            for i in range(len(clk)):
                self.assertEqual(c2bool(clk[i]),   (yield dut.clk))
                self.assertEqual(c2bool(ce[i]),    (yield dut.ce))
                yield
        dut = SDPHYClocker()
        dut.divider.storage.reset = 4
        run_simulation(dut, gen(dut))

    def test_clocker_div5(self):
        # Effective Div = 6.
        def gen(dut):
            clk   = "____---___---___---_"
            ce    = "_-_____-_____-_____-"
            for i in range(len(clk)):
                self.assertEqual(c2bool(clk[i]),   (yield dut.clk))
                self.assertEqual(c2bool(ce[i]),    (yield dut.ce))
                yield
        dut = SDPHYClocker()
        dut.divider.storage.reset = 5
        run_simulation(dut, gen(dut))

    def test_clocker_div8(self):
        # Effective Div = 8.
        def gen(dut):
            yield dut.divider.storage.eq(8)
            clk   = "_____----____----___"
            ce    = "_-_______-_______-__"
            for i in range(len(clk)):
                self.assertEqual(c2bool(clk[i]),   (yield dut.clk))
                self.assertEqual(c2bool(ce[i]),    (yield dut.ce))
                yield
        dut = SDPHYClocker()
        dut.divider.storage.reset = 8
        run_simulation(dut, gen(dut))

    def test_phyr_cmd(self):
        def stim_gen(dut):
            yield dut.pads_in.valid.eq(1)
            #      ---s+0x55--0x00----0xff----0x00----
            cmd = "---_-_-_-_-________--------________"
            for i in range(len(cmd)):
                yield dut.pads_in.cmd.i.eq(c2bool(cmd[i]))
                yield
        def check_gen(dut):
            data = [0x55, 0x00, 0xff]
            yield dut.source.ready.eq(1)
            for i in range(len(data)):
                while (yield dut.source.valid) == 0:
                    yield
                self.assertEqual(data[i], (yield dut.source.data))
                yield
        dut = SDPHYR(_sdpads_layout(4), cmd=True)
        run_simulation(dut, [stim_gen(dut), check_gen(dut)])

    def test_phyr_data(self):
        def stim_gen(dut):
            data = [0xf, 0xf, 0x0, 0x5, 0xa, 0x5, 0x1, 0x2, 0x3]
            yield dut.pads_in.valid.eq(1)
            for i in range(len(data)):
                yield dut.pads_in.data.i.eq(data[i])
                yield
        def check_gen(dut):
            data = [0x5a, 0x51, 0x23]
            yield dut.source.ready.eq(1)
            for i in range(len(data)):
                while (yield dut.source.valid) == 0:
                    yield
                self.assertEqual(data[i], (yield dut.source.data))
                yield
        dut = SDPHYR(_sdpads_layout(4), data=True, data_width=4, skip_start_bit=True)
        run_simulation(dut, [stim_gen(dut), check_gen(dut)])

    def test_phyinit(self):
        def gen(dut):
            for n in range(4):
                yield dut.initialize.wr_stb.eq(1)
                yield
                yield dut.initialize.wr_stb.eq(0)
                yield dut.pads_out.ready.eq(1)
                clk   = "_" + "-"*80 + "__"
                for i in range(len(clk)):
                    self.assertEqual(c2bool(clk[i]), (yield dut.pads_out.clk))
                    yield
        dut = SDPHYInit(_sdpads_layout(4))
        run_simulation(dut, [gen(dut)])

    def test_phycmdw(self):
        def stim_gen(dut):
            data = [0x55, 0x00, 0xff]
            yield dut.sink.valid.eq(1)
            for i in range(len(data)):
                yield dut.sink.data.eq(data[i])
                yield dut.sink.last.eq(i == len(data) - 1)
                yield
                while (yield dut.sink.ready) == 0:
                    yield
        def check_gen(dut):
            yield dut.pads_out.ready.eq(1)
            #        ---0x55----0x00----0xff----
            cmd_o  = "___-_-_-_-________--------"
            cmd_oe = "__------------------------"
            for i in range(len(cmd_o)):
                self.assertEqual(c2bool(cmd_o[i]),  (yield dut.pads_out.cmd.o))
                self.assertEqual(c2bool(cmd_oe[i]), (yield dut.pads_out.cmd.oe))
                yield
        dut = SDPHYCMDW(_sdpads_layout(4))
        run_simulation(dut, [stim_gen(dut), check_gen(dut)])

    def test_phycmdr(self):
        def stim_gen(dut):
            yield dut.pads_in.valid.eq(1)
            #      ---s+0x55--0x00----0xff----0x00----
            cmd = "---_-_-_-_-________--------________"
            for i in range(len(cmd)):
                yield dut.pads_in.cmd.i.eq(c2bool(cmd[i]))
                yield
        def check_gen(dut):
            yield dut.pads_out.ready.eq(1)
            yield dut.sink.valid.eq(1)
            yield dut.sink.length.eq(3)
            yield dut.source.ready.eq(1)
            data = [0x55, 0x00, 0xff]
            last = [0b0,  0b0,  0b1]
            yield dut.source.ready.eq(1)
            for i in range(len(data)):
                while (yield dut.source.valid) == 0:
                    yield
                self.assertEqual(data[i], (yield dut.source.data))
                self.assertEqual(last[i], (yield dut.source.last))
                yield
        cmdw = Module()
        cmdw.done = 1
        dut  = SDPHYCMDR(_sdpads_layout(4), 1e6, 5e-3, cmdw)
        run_simulation(dut, [stim_gen(dut), check_gen(dut)])

    def test_phycrc(self):
        pass

    def _run_phydataw(self, busy_cycles):
        # Write one 1-byte block; the card answers with an accepted CRC status token then holds
        # DAT0 low (busy) for busy_cycles (None: forever).
        data_width = Signal(2)
        dut        = SDPHYDATAW(_sdpads_layout(4), data_width, 1e6, 200e-6) # 200 cycles timeout.
        crc_state  = dut.fsm.ongoing("CRC")

        status     = []
        sink_ready = []

        def sink_gen():
            yield dut.pads_out.ready.eq(1)
            yield dut.sink.data.eq(0x5a)
            yield dut.sink.last.eq(1)
            yield dut.sink.last_block.eq(1)
            yield dut.sink.valid.eq(1)
            yield
            for _ in range(1024):
                if (yield dut.sink.ready):
                    sink_ready.append(True)
                    break
                yield
            yield dut.sink.valid.eq(0)

        def card_gen():
            yield dut.pads_in.valid.eq(1)
            yield dut.pads_in.data.i.eq(0b1111)
            for _ in range(1024):
                if (yield crc_state):
                    break
                yield
            # Start bit, CRC status token (010: accepted), end bit.
            for bit in [0, 0, 1, 0, 1]:
                yield dut.pads_in.data.i.eq(0b1110 | bit)
                yield
            # Busy.
            yield dut.pads_in.data.i.eq(0b1110)
            for _ in range(1024 if busy_cycles is None else busy_cycles):
                yield
            yield dut.pads_in.data.i.eq(0b1111)

        def source_gen():
            yield dut.source.ready.eq(1)
            for _ in range(1024):
                if (yield dut.source.valid):
                    status.append((yield dut.source.status))
                yield

        run_simulation(dut, [sink_gen(), card_gen(), source_gen()])
        return status, sink_ready

    def test_phydataw(self):
        status, sink_ready = self._run_phydataw(busy_cycles=32)
        self.assertEqual(status, [SDCARD_STREAM_STATUS_DATAACCEPTED])
        self.assertEqual(sink_ready, [True])

    def test_phydataw_busy_timeout(self):
        status, sink_ready = self._run_phydataw(busy_cycles=None)
        self.assertEqual(status, [SDCARD_STREAM_STATUS_DATAACCEPTED, SDCARD_STREAM_STATUS_TIMEOUT])
        self.assertEqual(sink_ready, [True])

    def test_phydatar_backpressure_no_timeout(self):
        # 1-bit read of a 4-byte block with the consumer stalled for longer than the timeout: the SD
        # clock is stopped (stop) during the stall and the timeout must not expire.
        data_width = Signal(2)
        dut        = SDPHYDATAR(_sdpads_layout(4), data_width, 1e6, 100e-6) # 100 cycles timeout.

        data   = [0xa5, 0x5a, 0x12, 0x34]
        bits   = [1]*4 + [0] # Idle/Start.
        for byte in data + [0x00, 0x00]: # Data + CRC16 (CRC value not checked here).
            bits += [(byte >> (7 - i)) & 1 for i in range(8)]
        bits  += [1]*32 # End/Idle.
        status = []

        def sink_gen():
            yield dut.pads_out.ready.eq(1)
            yield dut.sink.block_length.eq(len(data))
            yield dut.sink.last.eq(1)
            yield dut.sink.valid.eq(1)
            for _ in range(2048):
                if (yield dut.sink.ready):
                    break
                yield
            yield dut.sink.valid.eq(0)

        def card_gen():
            yield dut.pads_in.data.i.eq(0b1111)
            for _ in range(8):
                yield
            i = 0
            for _ in range(2048):
                stop = (yield dut.stop)
                yield dut.pads_in.valid.eq(~stop & 1)
                yield dut.pads_in.data.i.eq(0b1110 | bits[min(i, len(bits) - 1)])
                if not stop:
                    i += 1
                yield

        def source_gen():
            for _ in range(32):
                if (yield dut.source.valid):
                    break
                yield
            # Consumer stall (3x timeout).
            for _ in range(300):
                yield
            yield dut.source.ready.eq(1)
            yield
            for _ in range(1024):
                if (yield dut.source.valid):
                    status.append((yield dut.source.status))
                yield

        run_simulation(dut, [sink_gen(), card_gen(), source_gen()])
        self.assertNotIn(SDCARD_STREAM_STATUS_TIMEOUT, status)
        self.assertEqual(len(status), len(data) + 2) # Data + CRC16 (dropped by the core).

    def test_phydatar(self):
        pass


class TestSDPHYCSRLayout(unittest.TestCase):
    def test_csr_layout(self):
        # The register offsets are used by existing drivers (ex: Linux litex_mmc writes the settings
        # register at offset 0x18): new registers must be added after the existing ones.
        pads = Record([("clk", 1), ("cmd_i", 1), ("cmd_o", 1), ("cmd_t", 1),
                       ("dat_i", 4), ("dat_o", 4), ("dat_t", 4)])
        phy  = SDPHY(pads, "sim", 100e6)
        self.assertEqual([csr.name for csr in phy.get_csrs()], [
            "card_detect",     # 0x00.
            "clocker_divider", # 0x04.
            "init_initialize", # 0x08.
            "cmdr_timeout",    # 0x0c.
            "dataw_status",    # 0x10.
            "datar_timeout",   # 0x14.
            "settings",        # 0x18.
            "dataw_timeout",   # 0x1c.
        ])


class TestSDPHYDataWidth(unittest.TestCase):
    def _phy(self, n):
        pads = Record([("clk", 1), ("cmd", 1), ("data", n)])
        return SDPHY(pads, "xc7", 100e6)

    def test_data_width_capabilities(self):
        for n, constants, reset in [
            (1, [],                           SD_PHY_SPEED_1X),
            (4, ["support_4x"],               SD_PHY_SPEED_4X),
            (8, ["support_4x", "support_8x"], SD_PHY_SPEED_4X),
        ]:
            phy = self._phy(n)
            self.assertEqual(sorted(c.name for c in phy.get_constants()), constants)
            self.assertEqual(phy.settings.fields.data_width.reset.value, reset)

if __name__ == '__main__':
    unittest.main()
