#!/usr/bin/env python3
# -*- coding: utf-8 -*-

def extract(x, start, size):
    return (x >> start) & (2**size - 1)

def decode_rca(r6):
    rca = int.from_bytes(r6[2:4], 'little')
    print("RCA: {:04x}".format(rca))
    return rca

class SCR():
    def __init__(self, scr):
        self.scr = scr

        self.scr_structure = extract(scr, 60, 4)

        self.sd_spec = extract(scr, 56, 4)
        self.sd_spec3 = extract(scr, 47, 1)
        self.sd_spec4 = extract(scr, 42, 1)
        self.sd_specx = extract(scr, 38, 4)

        self.data_stat_after_erase = extract(scr, 55, 1)

        self.sd_security = extract(scr, 52, 3)

        self.sd_bus_widths = extract(scr, 48, 4)
        self.sd_bus_width_1bit = extract(scr, 48, 1)
        self.sd_bus_width_4bit = extract(scr, 50, 1)

        ex_security = extract(scr, 43, 4)
        self.ex_security_supported = ex_security > 0

        self.cmd_support = extract(scr, 32, 2)
        self.cmd_support_scc = extract(scr, 32, 1)
        self.cmd_support_sbc = extract(scr, 33, 1)

    def __str__(self):
        sd_spec_version = {
            0 : "Version 1.0 and 1.01",
            1 : "Version 1.10",
            2 : "Version 2.00",
            3 : "Version 3.0X",
            4 : "Version 4.XX",
            5 : "Version 5.XX",
            6 : "Version 6.XX",
        }[self.sd_spec + self.sd_spec3 + self.sd_spec4 + self.sd_specx]

        sd_security_version = {
            0 : "None",
            1 : "Not Used",
            2 : "SDSC Card (Security Version 1.01)",
            3 : "SDHC Card (Security Version 2.00)",
            4 : "SDXC Card (Security Version 3.xx)"
        }[self.sd_security]

        sd_bus_width_supported = ""
        if self.sd_bus_width_1bit == 1:
            sd_bus_width_supported += "\n        1 bit (DAT0)"
        if self.sd_bus_width_4bit == 1:
            sd_bus_width_supported += "\n        4 bit (DAT0-3)"

        cmd_supported = ""
        if self.cmd_support_sbc == 1:
            cmd_supported += "\n        Set Block Count (CMD23)"
        if self.cmd_support_scc == 1:
            cmd_supported += "\n        Speed Class Control (CMD20)"

        r = """
    SCR Register: {:016x}
    SCR Structure: {}
    SD Memory Card - Spec. Version: {}
    Data status after erases: {}
    CPRM Security Support: {}
    DAT Bus widths supported: {}
    Extended Security Support: {}
    Command Support bits: {}
""".format(
    self.scr,
    "SCR version 1.0" if self.scr_structure == 0 else "reserved",
    sd_spec_version,
    self.data_stat_after_erase,
    sd_security_version,
    sd_bus_width_supported,
    "Supported" if self.ex_security_supported else "Not supported",
    cmd_supported,
)
        return r

def decode_scr(comm, addr):
    data = []
    for i in range(8//4):
        data.append(comm.read(addr + 4*i))
    ba = bytearray()
    for d in data:
        ba += bytearray(d.to_bytes(4, 'little'))
    scr = SCR(int(ba.hex(), 16))
    print(scr)
    return scr
