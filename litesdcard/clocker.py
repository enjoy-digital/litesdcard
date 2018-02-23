from migen import *
from migen.genlib.resetsync import AsyncResetSynchronizer

from litex.soc.interconnect.csr import *


class SDClockerS6(Module, AutoCSR):
    def __init__(self, sys_clk_freq=50e6, max_sd_clk_freq=100e6):
            self._cmd_data = CSRStorage(10)
            self._send_cmd_data = CSR()
            self._send_go = CSR()
            self._status = CSRStatus(4)
            self._max_sd_clk_freq = CSRConstant(max_sd_clk_freq)

            self.clock_domains.cd_sd = ClockDomain()
            self.clock_domains.cd_sd_fb = ClockDomain()

            # # #

            clk_sd_unbuffered = Signal()
            sd_progdata = Signal()
            sd_progen = Signal()
            sd_progdone = Signal()

            sd_locked = Signal()

            clkfx_md_max = max(2.0/4.0, max_sd_clk_freq/sys_clk_freq)
            self._clkfx_md_max_1000 = CSRConstant(clkfx_md_max*1000.0)
            self.specials += Instance("DCM_CLKGEN",
                # parameters
                p_SPREAD_SPECTRUM="NONE",
                p_STARTUP_WAIT="FALSE",

                # reset
                i_FREEZEDCM=0,
                i_RST=ResetSignal(),

                # input
                i_CLKIN=ClockSignal(),
                p_CLKIN_PERIOD=1e9/sys_clk_freq,

                # output
                p_CLKFXDV_DIVIDE=2,
                p_CLKFX_MULTIPLY=2,
                p_CLKFX_DIVIDE=4,
                p_CLKFX_MD_MAX=clkfx_md_max,
                o_CLKFX=clk_sd_unbuffered,
                o_LOCKED=sd_locked,

                # programming interface
                i_PROGCLK=ClockSignal(),
                i_PROGDATA=sd_progdata,
                i_PROGEN=sd_progen,
                o_PROGDONE=sd_progdone
            )

            remaining_bits = Signal(max=11)
            transmitting = Signal()
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

            # enforce gap between commands
            busy_counter = Signal(max=14)
            busy = Signal()
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


class SDClockerS7(Module, AutoCSR):
    def __init__(self, sys_clk_freq=100e6):
        self.clock_domains.cd_sd = ClockDomain()
        self.clock_domains.cd_sd_fb = ClockDomain()

        self._mmcm_reset = CSRStorage()
        self._mmcm_read = CSR()
        self._mmcm_write = CSR()
        self._mmcm_drdy = CSRStatus()
        self._mmcm_adr = CSRStorage(7)
        self._mmcm_dat_w = CSRStorage(16)
        self._mmcm_dat_r = CSRStatus(16)

        # # #

        mmcm_locked = Signal()
        mmcm_fb = Signal()
        mmcm_clk0 = Signal()
        mmcm_drdy = Signal()

        self.specials += [
            Instance("MMCME2_ADV",
                p_BANDWIDTH="OPTIMIZED",
                i_RST=self._mmcm_reset.storage, o_LOCKED=mmcm_locked,

                # VCO
                p_REF_JITTER1=0.01, p_CLKIN1_PERIOD=1e9/sys_clk_freq,
                p_CLKFBOUT_MULT_F=30.0, p_CLKFBOUT_PHASE=0.000, p_DIVCLK_DIVIDE=2,
                i_CLKIN1=ClockSignal(), i_CLKFBIN=mmcm_fb, o_CLKFBOUT=mmcm_fb,

                # CLK0
                p_CLKOUT0_DIVIDE_F=10.0, p_CLKOUT0_PHASE=0.000, o_CLKOUT0=mmcm_clk0,

                # DRP
                i_DCLK=ClockSignal(),
                i_DWE=self._mmcm_write.re,
                i_DEN=self._mmcm_read.re | self._mmcm_write.re,
                o_DRDY=mmcm_drdy,
                i_DADDR=self._mmcm_adr.storage,
                i_DI=self._mmcm_dat_w.storage,
                o_DO=self._mmcm_dat_r.status
            ),
            Instance("BUFG", i_I=mmcm_clk0, o_O=self.cd_sd.clk),
        ]
        self.sync += [
            If(self._mmcm_read.re | self._mmcm_write.re,
                self._mmcm_drdy.status.eq(0)
            ).Elif(mmcm_drdy,
                self._mmcm_drdy.status.eq(1)
            )
        ]
        self.comb += self.cd_sd.rst.eq(~mmcm_locked)
