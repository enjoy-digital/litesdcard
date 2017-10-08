#!/usr/bin/env python3

import sys
import time

from litex.soc.tools.remote import RemoteClient

from litesdcard.common import *
from litesdcard.phy import *
from litesdcard.software.libsdcard import *

from litescope.software.driver.analyzer import LiteScopeAnalyzerDriver

# clocking

def sdclk_mmcm_write(adr, data):
    wb.regs.sdclk_mmcm_adr.write(adr)
    wb.regs.sdclk_mmcm_dat_w.write(data)
    wb.regs.sdclk_mmcm_write.write(1)
    while((wb.regs.sdclk_mmcm_drdy.read() & 0x1) == 0):
        pass

# FIXME: add vco frequency check
def sdclk_get_config(freq):
    ideal_m = freq
    ideal_d = 10000

    best_m = 1
    best_d = 0
    for d in range(1, 128):
        for m in range(2, 128):
            # common denominator is d*bd*ideal_d
            diff_current = abs(d*ideal_d*best_m - d*best_d*ideal_m)
            diff_tested = abs(best_d*ideal_d*m - d*best_d*ideal_m)
            if diff_tested < diff_current:
                best_m = m
                best_d = d
    return best_m, best_d

def sdclk_set_config(wb, freq):
    clock_m, clock_d = sdclk_get_config(freq//1000)
    # clkfbout_mult = clock_m
    if(clock_m%2):
        sdclk_mmcm_write(0x14, 0x1000 | ((clock_m//2)<<6) | (clock_m//2 + 1))
    else:
        sdclk_mmcm_write(0x14, 0x1000 | ((clock_m//2)<<6) | clock_m//2)
    # divclk_divide = clock_d
    if (clock_d == 1):
        sdclk_mmcm_write(0x16, 0x1000)
    elif(clock_d%2):
        sdclk_mmcm_write(0x16, ((clock_d//2)<<6) | (clock_d//2 + 1))
    else:
        sdclk_mmcm_write(0x16, ((clock_d//2)<<6) | clock_d//2)
    # clkout0_divide = 10
    sdclk_mmcm_write(0x8, 0x1000 | (5<<6) | 5)


# command utils

def sdcard_wait_cmd_done(wb):
    while True:
        cmdevt = wb.regs.sdcore_cmdevt.read()
        if cmdevt & 0x1:
            print('cmdevt: 0x{:08x}{}{}'.format(
                cmdevt,
                ' (CRC Error)' if cmdevt & 0x8 else '',
                ' (Timeout)' if cmdevt & 0x4 else '',
            ))
            if cmdevt & 0x4:
                return SD_TIMEOUT
            elif cmdevt & 0x8:
                return SD_CRCERROR
            return SD_OK

def sdcard_wait_data_done(wb):
    while True:
        dataevt = wb.regs.sdcore_dataevt.read()
        if dataevt & 0x1:
            print('dataevt: 0x{:08x}{}{}{}'.format(
                dataevt,
                ' (CRC Error)' if dataevt & 0x8 else '',
                ' (Timeout)' if dataevt & 0x4 else '',
                ' (Write Error)' if dataevt & 0x2 else '',
            ))
            if dataevt & 0x4:
                return SD_TIMEOUT
            elif dataevt & 0x2:
                return SD_WRITEERROR
            elif dataevt & 0x8:
                return SD_CRCERROR
            return SD_OK

def sdcard_wait_response(wb, length, nocrccheck=False):
    status = sdcard_wait_cmd_done(wb)
    response = wb.read(wb.regs.sdcore_response.addr, 4)
    if length == SDCARD_CTRL_RESPONSE_SHORT:
        s = "0x{:08x}".format(response[3])
        ba = bytearray(response[3].to_bytes(4, 'little'))
    elif length == SDCARD_CTRL_RESPONSE_LONG:
        ba = bytearray()
        s = "0x{:08x} 0x{:08x} 0x{:08x} 0x{:08x}".format(*response)
        for r in reversed(response):
            ba += bytearray(r.to_bytes(4, 'little'))
    print(s)
    return ba, status

# commands

def sdcard_go_idle_state(wb):
    print("CMD0: GO_IDLE_STATE")
    wb.regs.sdcore_argument.write(0x00000000)
    wb.regs.sdcore_command.write((0 << 8) | SDCARD_CTRL_RESPONSE_NONE)

def sdcard_all_send_cid(wb):
    print("CMD2: ALL_SEND_CID")
    wb.regs.sdcore_argument.write(0x00000000)
    wb.regs.sdcore_command.write((2 << 8) | SDCARD_CTRL_RESPONSE_LONG)
    return sdcard_wait_response(wb, SDCARD_CTRL_RESPONSE_LONG)

def sdcard_set_relative_address(wb):
    print("CMD3: SET_RELATIVE_ADDRESS")
    wb.regs.sdcore_argument.write(0x00000000)
    wb.regs.sdcore_command.write((3 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return sdcard_wait_response(wb, SDCARD_CTRL_RESPONSE_SHORT)

def sdcard_switch_func(wb, mode, group, value):
    print("CMD6: SWITCH_FUNC")
    arg = (mode << 31) | 0xffffff
    arg &= ~(0xf << (group * 4))
    arg |= value << (group * 4)
    print("{:8x}".format(arg))
    wb.regs.sdcore_argument.write(arg)
    wb.regs.sdcore_blocksize.write(64)
    wb.regs.sdcore_blockcount.write(1)
    wb.regs.sdcore_command.write((6 << 8) | SDCARD_CTRL_RESPONSE_SHORT |
                                 (SDCARD_CTRL_DATA_TRANSFER_READ << 5))
    r = sdcard_wait_response(wb, SDCARD_CTRL_RESPONSE_SHORT)
    sdcard_wait_data_done(wb)
    return r

def sdcard_select_card(wb, rca):
    print("CMD7: SELECT_CARD")
    wb.regs.sdcore_argument.write(rca << 16)
    wb.regs.sdcore_command.write((7 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return sdcard_wait_response(wb, SDCARD_CTRL_RESPONSE_SHORT)

def sdcard_send_ext_csd(wb):
    print("CMD8: SEND_EXT_CSD")
    wb.regs.sdcore_argument.write(0x000001aa)
    wb.regs.sdcore_command.write((8 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return sdcard_wait_response(wb, SDCARD_CTRL_RESPONSE_SHORT)

def sdcard_send_csd(wb, rca):
    print("CMD9: SEND_CSD")
    wb.regs.sdcore_argument.write(rca << 16)
    wb.regs.sdcore_command.write((9 << 8) | SDCARD_CTRL_RESPONSE_LONG)
    return sdcard_wait_response(wb, SDCARD_CTRL_RESPONSE_LONG)

def sdcard_send_cid(wb, rca):
    print("CMD10: SEND_CID")
    wb.regs.sdcore_argument.write(rca << 16)
    wb.regs.sdcore_command.write((10 << 8) | SDCARD_CTRL_RESPONSE_LONG)
    return sdcard_wait_response(wb, SDCARD_CTRL_RESPONSE_LONG)

def sdcard_voltage_switch(wb):
    print("CMD11: VOLTAGE_SWITCH")
    wb.regs.sdcore_argument.write(0x00000000)
    wb.regs.sdcore_command.write((11 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return sdcard_wait_response(wb, SDCARD_CTRL_RESPONSE_SHORT)

def sdcard_stop_transmission(wb):
    print("CMD12: STOP_TRANSMISSION")
    wb.regs.sdcore_argument.write(0x00000000)
    wb.regs.sdcore_command.write((12 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return sdcard_wait_response(wb, SDCARD_CTRL_RESPONSE_SHORT)

def sdcard_send_status(wb, rca):
    print("CMD13: SEND_STATUS")
    wb.regs.sdcore_argument.write(rca << 16)
    wb.regs.sdcore_command.write((13 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return sdcard_wait_response(wb, SDCARD_CTRL_RESPONSE_SHORT)

def sdcard_set_blocklen(wb, blocklen):
    print("CMD16: SET_BLOCKLEN")
    wb.regs.sdcore_argument.write(blocklen)
    wb.regs.sdcore_command.write((16 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return sdcard_wait_response(wb, SDCARD_CTRL_RESPONSE_SHORT)

def sdcard_read_single_block(wb, blkaddr):
    print("CMD17: READ_SINGLE_BLOCK")
    cmd_response = -1
    while cmd_response != SD_OK:
        wb.regs.sdcore_argument.write(blkaddr)
        wb.regs.sdcore_blocksize.write(512)
        wb.regs.sdcore_blockcount.write(1)
        wb.regs.sdcore_command.write((17 << 8) | SDCARD_CTRL_RESPONSE_SHORT | 
                                     (SDCARD_CTRL_DATA_TRANSFER_READ << 5))
        cmd_response = sdcard_wait_cmd_done(wb)
    return cmd_response

def sdcard_read_multiple_block(wb, blkaddr, blkcnt):
    print("CMD18: READ_MULTIPLE_BLOCK")
    cmd_response = -1
    while cmd_response != SD_OK:
        wb.regs.sdcore_argument.write(blkaddr)
        wb.regs.sdcore_blocksize.write(512)
        wb.regs.sdcore_blockcount.write(blkcnt)
        wb.regs.sdcore_command.write((18 << 8) | SDCARD_CTRL_RESPONSE_SHORT |
                                     (SDCARD_CTRL_DATA_TRANSFER_READ << 5))
        cmd_response = sdcard_wait_cmd_done(wb)
    return cmd_response

def sdcard_send_tuning_block(wb):
    print("CMD19: SEND_TUNING_BLOCK")
    wb.regs.sdcore_argument.write(0x00000000)
    wb.regs.sdcore_command.write((19 << 8) | SDCARD_CTRL_RESPONSE_SHORT |
                                 (SDCARD_CTRL_DATA_TRANSFER_READ << 5))
    r = sdcard_wait_response(wb, SDCARD_CTRL_RESPONSE_SHORT)
    sdcard_wait_data_done(wb)
    return r

def sdcard_set_block_count(wb, blkcnt):
    print("CMD23: SET_BLOCK_COUNT")
    wb.regs.sdcore_argument.write(blkcnt) # 1 means 1 block
    wb.regs.sdcore_command.write((23 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return sdcard_wait_response(wb, SDCARD_CTRL_RESPONSE_SHORT)

def sdcard_write_single_block(wb, blkaddr):
    print("CMD24: WRITE_SINGLE_BLOCK")
    cmd_response = -1
    while cmd_response != SD_OK:
        wb.regs.sdcore_argument.write(blkaddr)
        wb.regs.sdcore_blocksize.write(512)
        wb.regs.sdcore_blockcount.write(1)
        wb.regs.sdcore_command.write((24 << 8) | SDCARD_CTRL_RESPONSE_SHORT |
                                     (SDCARD_CTRL_DATA_TRANSFER_WRITE << 5))
        cmd_response =  sdcard_wait_cmd_done(wb)
    return cmd_response

def sdcard_write_multiple_block(wb, blkaddr, blkcnt):
    print("CMD25: WRITE_MULTIPLE_BLOCK")
    cmd_response = -1
    while cmd_response != SD_OK:
        wb.regs.sdcore_argument.write(blkaddr)
        wb.regs.sdcore_blocksize.write(512)
        wb.regs.sdcore_blockcount.write(blkcnt)
        wb.regs.sdcore_command.write((25 << 8) | SDCARD_CTRL_RESPONSE_SHORT |
                                     (SDCARD_CTRL_DATA_TRANSFER_WRITE << 5))
        cmd_response = sdcard_wait_cmd_done(wb)
    return cmd_response

def sdcard_app_cmd(wb, rca=0):
    print("CMD55: APP_CMD")
    wb.regs.sdcore_argument.write(rca << 16)
    wb.regs.sdcore_command.write((55 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return sdcard_wait_response(wb, SDCARD_CTRL_RESPONSE_SHORT)

def sdcard_app_set_bus_width(wb):
    print("CMD6: APP_SET_BUS_WIDTH")
    wb.regs.sdcore_argument.write(0x00000002)
    wb.regs.sdcore_command.write((6 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return sdcard_wait_response(wb, SDCARD_CTRL_RESPONSE_SHORT)

def sdcard_app_send_status(wb):
    print("CMD13: APP_SEND_STATUS")
    wb.regs.sdcore_argument.write(0x00000000)
    wb.regs.sdcore_blocksize.write(64)
    wb.regs.sdcore_blockcount.write(1)
    wb.regs.sdcore_command.write((13 << 8) | SDCARD_CTRL_RESPONSE_SHORT |
                                 (SDCARD_CTRL_DATA_TRANSFER_READ << 5))
    r = sdcard_wait_response(wb, SDCARD_CTRL_RESPONSE_SHORT)
    sdcard_wait_data_done(wb)
    return r

def sdcard_app_send_op_cond(wb, hcs=False, s18r=False):
    print("CMD41: APP_SEND_OP_COND")
    arg = 0x10ff8000
    if hcs:
        arg |= 0x60000000
    if s18r:
        arg |= 0x01000000
    wb.regs.sdcore_argument.write(arg)
    wb.regs.sdcore_command.write((41 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return sdcard_wait_response(wb, SDCARD_CTRL_RESPONSE_SHORT, nocrccheck=True)

def sdcard_app_send_scr(wb):
    print("CMD51: APP_SEND_SCR")
    wb.regs.sdcore_argument.write(0x00000000)
    wb.regs.sdcore_blocksize.write(8)
    wb.regs.sdcore_blockcount.write(1)
    wb.regs.sdcore_command.write((51 << 8) | SDCARD_CTRL_RESPONSE_SHORT |
                                 (SDCARD_CTRL_DATA_TRANSFER_READ << 5))
    r = sdcard_wait_response(wb, SDCARD_CTRL_RESPONSE_SHORT)
    sdcard_wait_data_done(wb)
    return r

def sdcard_app_send_num_wr_blocks(wb):
    print("CMD22: APP_SEND_NUM_WR_BLOCKS")
    wb.regs.sdcore_argument.write(0x00000000)
    wb.regs.sdcore_blocksize.write(4)
    wb.regs.sdcore_blockcount.write(1)
    wb.regs.sdcore_command.write((22 << 8) | SDCARD_CTRL_RESPONSE_SHORT |
                                 (SDCARD_CTRL_DATA_TRANSFER_READ << 5))
    r = sdcard_wait_response(wb, SDCARD_CTRL_RESPONSE_SHORT)
    sdcard_wait_data_done(wb)
    return r

# bist

def sdcard_bist_generator_start(wb, blkcnt):
    wb.regs.bist_generator_reset.write(1)
    wb.regs.bist_generator_count.write(blkcnt)
    wb.regs.bist_generator_start.write(1)

def sdcard_bist_generator_wait(wb):
    while((wb.regs.bist_generator_done.read() & 0x1) == 0):
        pass

def sdcard_bist_checker_start(wb):
    wb.regs.bist_checker_reset.write(1)
    wb.regs.bist_checker_start.write(1)

def sdcard_bist_checker_wait(wb):
    while((wb.regs.bist_checker_done.read() & 0x1) == 0):
        pass

# user

def settimeout(wb, clkfreq, timeout):
    clktimeout = int(timeout * clkfreq)
    wb.regs.sdcore_cmdtimeout.write(clktimeout)
    wb.regs.sdcore_datatimeout.write(clktimeout)

def main(wb):
    clkfreq = 10e6
    sdclk_set_config(wb, clkfreq)
    settimeout(wb, clkfreq, 0.1)

    # RESET CARD
    sdcard_go_idle_state(wb)

    sdcard_send_ext_csd(wb)

    # WAIT FOR CARD READY
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

    # SEND IDENTIFICATION
    sdcard_all_send_cid(wb)

    # SET RELATIVE CARD ADDRESS
    r6, status = sdcard_set_relative_address(wb)
    rca = decode_rca(r6)

    # SEND CID
    cid = sdcard_send_cid(wb, rca)
    decode_cid(wb)

    # SEND CSD
    sdcard_send_csd(wb, rca)
    decode_csd(wb)

    # SELECT CARD
    sdcard_select_card(wb, rca)

    # SET BUS WIDTH (WIDE)
    sdcard_app_cmd(wb, rca)
    sdcard_app_set_bus_width(wb)

    # SWITCH SPEED
    sdcard_switch_func(wb, SD_SWITCH_SWITCH, SD_GROUP_ACCESSMODE, SD_SPEED_SDR50)

    # SWITCH DRIVER STRENGH
    sdcard_switch_func(wb, SD_SWITCH_SWITCH, SD_GROUP_DRIVERSTRENGTH, SD_DRIVER_STRENGTH_D)

    # SEND SCR
    sdcard_app_cmd(wb, rca)
    sdcard_app_send_scr(wb)

    clkfreq = 10e6
    sdclk_set_config(wb, clkfreq)
    settimeout(wb, clkfreq, 0.1)

    # SET BLOCKLEN
    sdcard_set_blocklen(wb, 512)

    wb.regs.sdcore_datawcrcclear.write(1)
    wb.regs.sdcore_datawcrcclear.write(0)

    # SINGLE BLOCK TEST
    for i in range(2):
        # WRITE
        sdcard_bist_generator_start(wb, 1)
        sdcard_write_single_block(wb, i)
        sdcard_bist_generator_wait(wb)

        # READ
        sdcard_bist_checker_start(wb)
        sdcard_read_single_block(wb, i+32)
        sdcard_bist_checker_wait(wb)

    print("datawcrcvalids : {:d}".format(wb.regs.sdcore_datawcrcvalids.read()))
    print("datawcrcerrors : {:d}".format(wb.regs.sdcore_datawcrcerrors.read()))

    wb.regs.sdcore_datawcrcclear.write(1)
    wb.regs.sdcore_datawcrcclear.write(0)

    #  MULTIPLE BLOCK TEST

    blocks = 32

    # WRITE
    sdcard_set_block_count(wb, blocks)
    sdcard_bist_generator_start(wb, blocks)
    sdcard_write_multiple_block(wb, 0, blocks)
    sdcard_bist_generator_wait(wb)

    # READ
#    sdcard_set_block_count(wb, blocks);
#    sdcard_bist_checker_start(wb);
#    sdcard_read_multiple_block(wb, 0, blocks);
#    for i in range(blocks-1):
#        sdcard_bist_checker_wait(wb)
#        sdcard_bist_checker_start(wb)
#    sdcard_bist_checker_wait(wb);
#    sdcard_send_status(wb, rca);

    print("datawcrcvalids : {:d}".format(wb.regs.sdcore_datawcrcvalids.read()))
    print("datawcrcerrors : {:d}".format(wb.regs.sdcore_datawcrcerrors.read()))

if __name__ == '__main__':
    wb = RemoteClient(port=1234, debug=False)
    wb.open()
    main(wb)
    wb.close()
