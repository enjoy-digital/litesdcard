# This file is Copyright (c) 2017-2020 Florent Kermarrec <florent@enjoy-digital.fr>
# This file is Copyright (c) 2018 bunnie <bunnie@kosagi.com>
# License: BSD

from migen import *
from migen.genlib.resetsync import AsyncResetSynchronizer

from litex.soc.interconnect.csr import *

from litex.soc.cores.clock import S7MMCM

# SDClockerS6 --------------------------------------------------------------------------------------

class SDClockerS6(Module, AutoCSR):
    def __init__(self, sys_clk_freq=50e6, max_sd_clk_freq=100e6):
            self._cmd_data        = CSRStorage(10)
            self._send_cmd_data   = CSR()
            self._send_go         = CSR()
            self._status          = CSRStatus(4)
            self._max_sd_clk_freq = CSRConstant(max_sd_clk_freq)

            self.clock_domains.cd_sd    = ClockDomain()
            self.clock_domains.cd_sd_fb = ClockDomain()

            # # #

            clk_sd_unbuffered = Signal()
            sd_progdata       = Signal()
            sd_progen         = Signal()
            sd_progdone       = Signal()
            sd_locked         = Signal()

            clkfx_md_max = max(2.0/4.0, max_sd_clk_freq/sys_clk_freq)
            self._clkfx_md_max_1000 = CSRConstant(clkfx_md_max*1000.0)
            self.specials += Instance("DCM_CLKGEN",
                # Parameters
                p_SPREAD_SPECTRUM = "NONE",
                p_STARTUP_WAIT    = "FALSE",

                # Reset
                i_FREEZEDCM       = 0,
                i_RST             = ResetSignal(),

                # Input
                i_CLKIN           = ClockSignal(),
                p_CLKIN_PERIOD    = 1e9/sys_clk_freq,

                # Output
                p_CLKFXDV_DIVIDE  = 2,
                p_CLKFX_MULTIPLY  = 2,
                p_CLKFX_DIVIDE    = 4,
                p_CLKFX_MD_MAX    = clkfx_md_max,
                o_CLKFX           = clk_sd_unbuffered,
                o_LOCKED          = sd_locked,

                # Programming interface
                i_PROGCLK         = ClockSignal(),
                i_PROGDATA        = sd_progdata,
                i_PROGEN          = sd_progen,
                o_PROGDONE        = sd_progdone
            )

            remaining_bits = Signal(max=11)
            transmitting   = Signal()
            self.comb += transmitting.eq(remaining_bits != 0)
            sr = Signal(10)
            self.sync += [
                If(self._send_cmd_data.re,
                    remaining_bits.eq(10),
                    sr.eq(self._cmd_data.storage)
                ).Elif(transmitting,
                    remaining_bits.eq(remaining_bits - 1),
                    sr.eq(sr[1:])
                )
            ]
            self.comb += [
                sd_progdata.eq(transmitting & sr[0]),
                sd_progen.eq(transmitting | self._send_go.re)
            ]

            # Enforce gap between commands
            busy_counter = Signal(max=14)
            busy         = Signal()
            self.comb += busy.eq(busy_counter != 0)
            self.sync += If(self._send_cmd_data.re,
                    busy_counter.eq(13)
                ).Elif(busy,
                    busy_counter.eq(busy_counter - 1)
                )

            self.comb += self._status.status.eq(Cat(busy, sd_progdone, sd_locked))

            self.specials += [
                Instance("BUFG", i_I=clk_sd_unbuffered, o_O=self.cd_sd.clk),
                AsyncResetSynchronizer(self.cd_sd, ~sd_locked)
            ]


# SDClockerS7 --------------------------------------------------------------------------------------

class SDClockerS7(Module, AutoCSR):
    def __init__(self, sys_clk_freq=100e6, sd_clk_freq=10e6):
        self.clock_domains.cd_sd    = ClockDomain()
        self.clock_domains.cd_sd_fb = ClockDomain()

        self.submodules.mmcm = mmcm = S7MMCM(speedgrade=-1)
        mmcm.register_clkin(ClockSignal(), sys_clk_freq)
        mmcm.create_clkout(self.cd_sd, sd_clk_freq)
        mmcm.expose_drp()


# SDClockerECP5 ------------------------------------------------------------------------------------

class SDClockerECP5(Module):
    def __init__(self):
        self.clock_domains.cd_sd    = ClockDomain()
        self.clock_domains.cd_sd_fb = ClockDomain()

        self.comb += self.cd_sd.clk.eq(ClockSignal("clk10"))
        self.comb += self.cd_sd.rst.eq(ResetSignal("clk10"))
