#!/usr/bin/env python3

import sys
import time

from litex.soc.tools.remote import RemoteClient

from libbase.sdcard import *


def main(wb):
    # set low speed clock
    clkfreq = 10e6
    sdclk_set_config(wb, clkfreq)
    settimeout(wb, clkfreq, 0.1)

    # reset card
    sdcard_go_idle_state(wb)

    sdcard_send_ext_csd(wb)

    # wait for card ready
    s18r = False
    s18a = False
    while True:
        sdcard_app_cmd(wb)
        r3, status = sdcard_app_send_op_cond(wb, hcs=True, s18r=s18r)
        if r3[3] & 0x80:
            print("SDCard ready | ", end="")
            s18a = r3[3] & 0x01
            if s18a:
                print("1.8V switch supported")
            else:
                print("1.8V switch not supported/needed")
            break

    # send identification
    sdcard_all_send_cid(wb)

    # set relative card address
    r6, status = sdcard_set_relative_address(wb)
    rca = decode_rca(r6)

    # send cid
    cid = sdcard_send_cid(wb, rca)
    decode_cid(wb)

    # send csd
    sdcard_send_csd(wb, rca)
    decode_csd(wb)

    # select card
    sdcard_select_card(wb, rca)

    # set bus width (4 bits wide)
    sdcard_app_cmd(wb, rca)
    sdcard_app_set_bus_width(wb)

    # send scr
    sdcard_app_cmd(wb, rca)
    sdcard_app_send_scr(wb)

    clkfreq = 100e6
    sdclk_set_config(wb, clkfreq)
    settimeout(wb, clkfreq, 0.1)

    # set blocklen
    sdcard_set_blocklen(wb, 512)

    # single block test
    for i in range(2):
        # write
        sdcard_bist_generator_start(wb, 1)
        sdcard_write_single_block(wb, i)
        sdcard_bist_generator_wait(wb)

        # read
        sdcard_bist_checker_start(wb, 1)
        sdcard_read_single_block(wb, i)
        sdcard_bist_checker_wait(wb)

        print("bist errors: {:d}".format(wb.regs.bist_checker_errors.read()))

    #  multiple blocks test
    length = 16*1024*1024
    blocks = length//512

    # write
    sdcard_set_block_count(wb, blocks)
    sdcard_bist_generator_start(wb, blocks)
    sdcard_write_multiple_block(wb, 0, blocks)
    sdcard_bist_generator_wait(wb)
    sdcard_stop_transmission(wb)

    # read
    sdcard_set_block_count(wb, blocks)
    sdcard_bist_checker_start(wb, blocks)
    sdcard_read_multiple_block(wb, 0, blocks)
    sdcard_bist_checker_wait(wb)

    print("bist errors: {:d}".format(wb.regs.bist_checker_errors.read()))

if __name__ == '__main__':
    wb = RemoteClient(port=1234, debug=False)
    wb.open()
    main(wb)
    wb.close()
