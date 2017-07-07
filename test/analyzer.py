#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from litex.soc.tools.remote import RemoteClient
from litescope.software.driver.analyzer import LiteScopeAnalyzerDriver

wb = RemoteClient(csr_csv="build/csr.csv")
wb.open()

# # #

analyzer = LiteScopeAnalyzerDriver(wb.regs, "analyzer", debug=True)
# analyzer.configure_trigger()
# analyzer.configure_trigger(cond={"sdq_phy_en": 1, "sdq_phy_i": 1})
# analyzer.configure_trigger(cond={"sdctrl_crc16checker_sink_last": 1, "sdctrl_crc16checker_sink_payload_data": 0x00})
analyzer.configure_trigger(cond={"sdphy_stsel": 1})
analyzer.configure_subsampler(1)
analyzer.run(offset=200, length=512) # 10000
while not analyzer.done():
    pass
analyzer.upload()
analyzer.save("vcd/litescope.vcd")

# # #

wb.close()
