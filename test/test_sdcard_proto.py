#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import time

from litex.soc.tools.remote import RemoteClient

from litesdcard.common import *
from litesdcard.phy import *
from litesdcard.software.libsdcard import *

from litescope.software.driver.analyzer import LiteScopeAnalyzerDriver


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


def clkgen_write(wb, cmd, data):
    word = (data << 2) | cmd
    wb.regs.sdcrg_cmd_data.write(word)
    wb.regs.sdcrg_send_cmd_data.write(1)
    while(wb.regs.sdcrg_status.read() & CLKGEN_STATUS_BUSY):
        pass


def clkgen_set(wb, freq):
    clock_m, clock_d = get_clock_md(freq//10000)
    clkgen_write(wb, 0x1, clock_d-1)
    clkgen_write(wb, 0x3, clock_m-1)

    wb.regs.sdcrg_send_go.write(1)
    while( not (wb.regs.sdcrg_status.read() & CLKGEN_STATUS_PROGDONE)):
        pass
    while(not (wb.regs.sdcrg_status.read() & CLKGEN_STATUS_LOCKED)):
        pass


def wait_cmd_done(wb):
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

def wait_data_done(wb):
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

def response(wb, length, nocrccheck=False):
    status = wait_cmd_done(wb)
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

def cmd0(wb):
    print("0: MMC_CMD_GO_IDLE_STATE")
    wb.regs.sdcore_argument.write(0x00000000)
    wb.regs.sdcore_command.write((0 << 8) | SDCARD_CTRL_RESPONSE_NONE)

def cmd2(wb):
    print("2: MMC_CMD_ALL_SEND_CID")
    wb.regs.sdcore_argument.write(0x00000000)
    wb.regs.sdcore_command.write((2 << 8) | SDCARD_CTRL_RESPONSE_LONG)
    return response(wb, SDCARD_CTRL_RESPONSE_LONG)

def cmd3(wb):
    print("3: MMC_CMD_SET_RELATIVE_CSR")
    wb.regs.sdcore_argument.write(0x00000000)
    wb.regs.sdcore_command.write((3 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return response(wb, SDCARD_CTRL_RESPONSE_SHORT)

def cmd6(wb, mode, group, value, destaddr):
    print("6: SD_CMD_SWITCH_FUNC")
    arg = (mode << 31) | 0xffffff
    arg &= ~(0xf << (group * 4))
    arg |= value << (group * 4)
    print("{:8x}".format(arg))
    wb.regs.sdcore_argument.write(arg)
    wb.regs.sdcore_blocksize.write(64)
    wb.regs.sdcore_blockcount.write(1)
    wb.regs.ramwriter_address.write(destaddr//4)
    wb.regs.sdcore_command.write((6 << 8) | SDCARD_CTRL_RESPONSE_SHORT | (SDCARD_CTRL_DATA_TRANSFER_READ << 5))
    r = response(wb, SDCARD_CTRL_RESPONSE_SHORT)
    wait_data_done(wb)
    return r

def cmd7(wb, rca):
    print("7: MMC_CMD_SELECT_CARD")
    wb.regs.sdcore_argument.write(rca << 16)
    wb.regs.sdcore_command.write((7 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return response(wb, SDCARD_CTRL_RESPONSE_SHORT)

def cmd8(wb):
    print("8: MMC_CMD_SEND_EXT_CSD")
    wb.regs.sdcore_argument.write(0x000001aa)
    wb.regs.sdcore_command.write((8 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return response(wb, SDCARD_CTRL_RESPONSE_SHORT)

def cmd9(wb, rca):
    print("9: MMC_CMD_SEND_CSD")
    wb.regs.sdcore_argument.write(rca << 16)
    wb.regs.sdcore_command.write((9 << 8) | SDCARD_CTRL_RESPONSE_LONG)
    return response(wb, SDCARD_CTRL_RESPONSE_LONG)

def cmd10(wb, rca):
    print("10: MMC_CMD_SEND_CID")
    wb.regs.sdcore_argument.write(rca << 16)
    wb.regs.sdcore_command.write((10 << 8) | SDCARD_CTRL_RESPONSE_LONG)
    return response(wb, SDCARD_CTRL_RESPONSE_LONG)

def cmd11(wb):
    print("11: MMC_CMD_VOLTAGE_SWITCH")
    wb.regs.sdcore_argument.write(0x00000000)
    wb.regs.sdcore_command.write((11 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return response(wb, SDCARD_CTRL_RESPONSE_SHORT)

def cmd12(wb):
    print("12: MMC_CMD_STOP_TRANSMISSION")
    wb.regs.sdcore_argument.write(0x00000000)
    wb.regs.sdcore_command.write((12 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return response(wb, SDCARD_CTRL_RESPONSE_SHORT)

def cmd13(wb, rca):
    print("13: MMC_CMD_SEND_STATUS")
    wb.regs.sdcore_argument.write(rca << 16)
    wb.regs.sdcore_command.write((13 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return response(wb, SDCARD_CTRL_RESPONSE_SHORT)

def cmd16(wb, blocklen):
    print("16: MMC_CMD_SET_BLOCKLEN")
    wb.regs.sdcore_argument.write(blocklen)
    wb.regs.sdcore_command.write((16 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return response(wb, SDCARD_CTRL_RESPONSE_SHORT)

def cmd17(wb, blkaddr, destaddr):
    print("17: MMC_CMD_READ_SINGLE_BLOCK")
    wb.regs.sdcore_argument.write(blkaddr)
    wb.regs.sdcore_blocksize.write(512)
    wb.regs.sdcore_blockcount.write(1)
    wb.regs.ramwriter_address.write(destaddr//4)
    wb.regs.sdcore_command.write((17 << 8) | SDCARD_CTRL_RESPONSE_SHORT | (SDCARD_CTRL_DATA_TRANSFER_READ << 5))
    r = response(wb, SDCARD_CTRL_RESPONSE_SHORT)
    wait_data_done(wb)
    return r

def cmd18(wb, blkaddr, blkcnt, destaddr):
    print("18: MMC_CMD_READ_MULTIPLE_BLOCK")
    wb.regs.sdcore_argument.write(blkaddr)
    wb.regs.sdcore_blocksize.write(512)
    wb.regs.sdcore_blockcount.write(blkcnt)
    wb.regs.ramwriter_address.write(destaddr//4)
    wb.regs.sdcore_command.write((18 << 8) | SDCARD_CTRL_RESPONSE_SHORT | (SDCARD_CTRL_DATA_TRANSFER_READ << 5))
    r = response(wb, SDCARD_CTRL_RESPONSE_SHORT)
    wait_data_done(wb)
    return r

def cmd19(wb, destaddr):
    print("19: MMC_CMD_SEND_TUNING_BLOCK")
    wb.regs.sdcore_argument.write(0x00000000)
    wb.regs.ramwriter_address.write(destaddr//4)
    wb.regs.sdcore_command.write((19 << 8) | SDCARD_CTRL_RESPONSE_SHORT | (SDCARD_CTRL_DATA_TRANSFER_READ << 5))
    r = response(wb, SDCARD_CTRL_RESPONSE_SHORT)
    wait_data_done(wb)
    return r

def cmd23(wb, blkcnt):
    print("23: MMC_CMD_SET_BLOCK_COUNT")
    wb.regs.sdcore_argument.write(blkcnt) # 1 means 1 block
    wb.regs.sdcore_command.write((23 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return response(wb, SDCARD_CTRL_RESPONSE_SHORT)

def cmd24(wb):
    print("24: MMC_CMD_WRITE_SINGLE_BLOCK")
    wb.regs.sdcore_argument.write(0x00000000)
    wb.regs.sdcore_blocksize.write(512)
    wb.regs.sdcore_blockcount.write(1)
    wb.regs.sdcore_command.write((24 << 8) | SDCARD_CTRL_RESPONSE_SHORT | (SDCARD_CTRL_DATA_TRANSFER_WRITE << 5))
    return response(wb, SDCARD_CTRL_RESPONSE_SHORT)

def cmd25(wb, blkaddr, blkcnt):
    print("25: MMC_CMD_WRITE_MULTIPLE_BLOCK")
    wb.regs.sdcore_argument.write(blkaddr)
    wb.regs.sdcore_blocksize.write(512)
    wb.regs.sdcore_blockcount.write(blkcnt)
    wb.regs.sdcore_command.write((25 << 8) | SDCARD_CTRL_RESPONSE_SHORT | (SDCARD_CTRL_DATA_TRANSFER_WRITE << 5))
    return response(wb, SDCARD_CTRL_RESPONSE_SHORT)

def cmd55(wb, rca=0):
    print("55: MMC_CMD_APP_CMD")
    wb.regs.sdcore_argument.write(rca << 16)
    wb.regs.sdcore_command.write((55 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return response(wb, SDCARD_CTRL_RESPONSE_SHORT)

def acmd6(wb):
    print("6: SD_CMD_APP_SET_BUS_WIDTH")
    wb.regs.sdcore_argument.write(0x00000002)
    wb.regs.sdcore_command.write((6 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return response(wb, SDCARD_CTRL_RESPONSE_SHORT)

def acmd13(wb, destaddr):
    print("13: SD_CMD_APP_SEND_STATUS")
    wb.regs.sdcore_argument.write(0x00000000)
    wb.regs.sdcore_blocksize.write(64)
    wb.regs.sdcore_blockcount.write(1)
    wb.regs.ramwriter_address.write(destaddr//4)
    wb.regs.sdcore_command.write((13 << 8) | SDCARD_CTRL_RESPONSE_SHORT | (SDCARD_CTRL_DATA_TRANSFER_READ << 5))
    r = response(wb, SDCARD_CTRL_RESPONSE_SHORT)
    wait_data_done(wb)
    return r

def acmd41(wb, hcs=False, s18r=False):
    print("41: SD_CMD_APP_SEND_OP_COND")
    arg = 0x10ff8000
    if hcs:
        arg |= 0x60000000
    if s18r:
        arg |= 0x01000000
    wb.regs.sdcore_argument.write(arg)
    wb.regs.sdcore_command.write((41 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return response(wb, SDCARD_CTRL_RESPONSE_SHORT, nocrccheck=True)

def acmd51(wb, destaddr):
    print("51: SD_CMD_APP_SEND_SCR")
    wb.regs.sdcore_argument.write(0x00000000)
    wb.regs.sdcore_blocksize.write(8)
    wb.regs.sdcore_blockcount.write(1)
    wb.regs.ramwriter_address.write(destaddr//4)
    wb.regs.sdcore_command.write((51 << 8) | SDCARD_CTRL_RESPONSE_SHORT | (SDCARD_CTRL_DATA_TRANSFER_READ << 5))
    r = response(wb, SDCARD_CTRL_RESPONSE_SHORT)
    wait_data_done(wb)
    return r

def acmd22(wb, destaddr):
    print("22: SD_CMD_APP_SEND_NUM_WR_BLOCKS")
    wb.regs.sdcore_argument.write(0x00000000)
    wb.regs.sdcore_blocksize.write(4)
    wb.regs.sdcore_blockcount.write(1)
    wb.regs.ramwriter_address.write(destaddr//4)
    wb.regs.sdcore_command.write((22 << 8) | SDCARD_CTRL_RESPONSE_SHORT | (SDCARD_CTRL_DATA_TRANSFER_READ << 5))
    r = response(wb, SDCARD_CTRL_RESPONSE_SHORT)
    wait_data_done(wb)
    return r

def settimeout(wb, clkfreq, timeout):
    clktimeout = int(timeout * clkfreq)
    wb.regs.sdcore_cmdtimeout.write(clktimeout)
    wb.regs.sdcore_datatimeout.write(clktimeout)

def memset(wb, addr, value, length):
    for i in range(length//4):
        wb.write(addr + 4*i, value)

def wait_ramread_done(wb):
    while not wb.regs.ramreader_done.read():
        pass

def ramread(wb, srcaddr):
    wb.regs.ramreader_address.write(srcaddr//4)
    wb.regs.ramreader_length.write(512)
    wait_ramread_done(wb)

def dumpall(wb, addr, length):
    for i in range(length//4):
        print('0x{:08x}: 0x{:08x}'.format(addr + 4*i, wb.read(addr + 4*i)))

def incremental(wb, addr):
    for i in range(512//4):
        k = (4*i) & 0xff
        dw = k | ((k+1)<<8) | ((k+2)<<16) | ((k+3)<<24)
        wb.write(addr + 4*i, dw & 0xffffffff)

def main(wb):
    clkfreq = 10e6
    clkgen_set(wb, clkfreq)
    settimeout(wb, clkfreq, 0.1)
    time.sleep(1)

    # RESET CARD
    cmd0(wb)
    cmd8(wb)

    # WAIT FOR CARD READY
    s18r = hasattr(wb.regs, "sdphy_voltage_sel")
    s18a = False
    while True:
        cmd55(wb)
        r3,status = acmd41(wb, hcs=True, s18r=s18r)
        if r3[3] & 0x80:
            print("SDCard ready | ", end="")
            s18a = r3[3] & 0x01
            if s18a:
                print("1.8V switch supported")
            else:
                print("1.8V switch not supported/needed")
            break

    # VOLTAGE SWITCH
    if s18r and s18a:
        cmd11(wb)
        wb.regs.sdphy_voltage_sel.write(1)

    # SEND IDENTIFICATION
    cmd2(wb)

    # SET RELATIVE CARD ADDRESS
    r6,status = cmd3(wb)
    rca = decode_rca(r6)

    # SEND CID
    cid = cmd10(wb, rca)
    decode_cid(wb)

    # SEND CSD
    cmd9(wb, rca)
    decode_csd(wb)

    # SELECT CARD
    cmd7(wb, rca)

    # SET BUS WIDTH (WIDE)
    cmd55(wb, rca)
    acmd6(wb)

    # SWITCH SPEED
    cmd6(wb, SD_SWITCH_SWITCH, SD_GROUP_ACCESSMODE, SD_SPEED_SDR50, wb.mems.sram.base)

    # SWITCH DRIVER STRENGH
    cmd6(wb, SD_SWITCH_SWITCH, SD_GROUP_DRIVERSTRENGTH, SD_DRIVER_STRENGTH_D, wb.mems.sram.base)

    # SEND SCR
    cmd55(wb, rca)
    acmd51(wb, wb.mems.sram.base)
    dumpall(wb, wb.mems.sram.base, 8)
    scr = decode_scr(wb, wb.mems.sram.base)
    if not scr.cmd_support_sbc:
        print("Need CMD23 support")
        return

    clkfreq = 85e6
    clkgen_set(wb, clkfreq)
    settimeout(wb, clkfreq, 0.1)
    time.sleep(1)

    from litescope.software.driver.analyzer import LiteScopeAnalyzerDriver
    analyzer = LiteScopeAnalyzerDriver(wb.regs, "analyzer", debug=True)
    analyzer.configure_trigger(cond={"sdsoc_sdphy_sdpads_sdpads_clk" : 1})
    analyzer.run(offset=8, length=256)

    input()

    # SET BLOCKLEN
    cmd16(wb, 512)

    analyzer.wait_done()
#    analyzer.upload()
    analyzer.save("dump.vcd")

    # READ MULTIPLE BLOCKS
    memset(wb, wb.mems.sram.base, 0, 1024)
    cmd23(wb, 2) # if supported in SCR
    cmd18(wb, 0, 2, wb.mems.sram.base)
    cmd13(wb, rca)
    dumpall(wb, wb.mems.sram.base, 128)


if __name__ == '__main__':
    wb = RemoteClient(port=1234, debug=False)
    wb.open()
    main(wb)
    wb.close()
