#!/usr/bin/env python3

from litex.soc.tools.remote import RemoteClient

wb = RemoteClient()
wb.open()

# # #

CLKGEN_STATUS_BUSY = 0x1
CLKGEN_STATUS_PROGDONE = 0x2
CLKGEN_STATUS_LOCKED = 0x4


def get_clock_md(sd_clock):
    ideal_m = sd_clock
    ideal_d = 5000

    best_m = 1
    best_d = 0
    for d in range(1, 256):
        for m in range(2, 256):
            # common denominator is d*bd*ideal_d
            diff_current = abs(d*ideal_d*best_m - d*best_d*ideal_m)
            diff_tested = abs(best_d*ideal_d*m - d*best_d*ideal_m)
            if diff_tested < diff_current:
                best_m = m
                best_d = d
    return best_m, best_d


def clkgen_write(cmd, data):
    word = (data << 2) | cmd
    wb.regs.sdcrg_cmd_data.write(word)
    wb.regs.sdcrg_send_cmd_data.write(1)
    while(wb.regs.sdcrg_status.read() & CLKGEN_STATUS_BUSY):
        pass


def clkgen_set(wb, freq):
    clock_m, clock_d = get_clock_md(freq//10000)
    clkgen_write(0x1, clock_d-1)
    clkgen_write(0x3, clock_m-1)

    wb.regs.sdcrg_send_go.write(1)
    while( not (wb.regs.sdcrg_status.read() & CLKGEN_STATUS_PROGDONE)):
        pass
    while(not (wb.regs.sdcrg_status.read() & CLKGEN_STATUS_LOCKED)):
        pass


clkgen_set(wb, 10e6)

# # #

wb.close()
