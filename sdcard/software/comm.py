#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import time
from litex.soc.tools.remote.comm_uart import CommUART
from litex.soc.tools.remote.comm_udp import CommUDP

litesdcard_path = "../../"
sys.path.append(litesdcard_path) # XXX

from sdcard.phy.sdphy import *
from libsdcard import *
from generated import csr

SD_OK = 0
SD_CRCERROR = 1
SD_TIMEOUT = 2
SD_WRITEERROR = 3

SD_SWITCH_CHECK = 0
SD_SWITCH_SWITCH = 1

SD_SPEED_SDR12 = 0
SD_SPEED_SDR25 = 1
SD_SPEED_SDR50 = 2
SD_SPEED_SDR104 = 3
SD_SPEED_DDR50 = 4

SD_GROUP_ACCESSMODE = 0
SD_GROUP_COMMANDSYSTEM = 1
SD_GROUP_DRIVERSTRENGTH = 2
SD_GROUP_POWERLIMIT = 3

def debug(comm):
    print(hex(comm.read(csr.CSR_SDCTRL_DEBUG_ADDR)))

def wait_cmd_done(comm):
    while True:
        cmdevt = comm.read(csr.CSR_SDCTRL_CMDEVT_ADDR)
        if cmdevt & 0x1:
            print('cmdevt: {:08x}{}{}'.format(
                cmdevt,
                ' (CRC Error)' if cmdevt & 0x8 else '',
                ' (Timeout)' if cmdevt & 0x4 else '',
            ))
            if cmdevt & 0x4:
                return SD_TIMEOUT
            elif cmdevt & 0x8:
                return SD_CRCERROR
            return SD_OK

def wait_data_done(comm):
    while True:
        dataevt = comm.read(csr.CSR_SDCTRL_DATAEVT_ADDR)
        if dataevt & 0x1:
            print('dataevt: {:08x}{}{}{}'.format(
                dataevt,
                ' (CRC Error)' if dataevt & 0x8 else '',
                ' (Timeout)' if dataevt & 0x4 else '',
                ' (Write Error)' if dataevt & 0x2 else '',
            ))
            debug(comm)
            if dataevt & 0x4:
                return SD_TIMEOUT
            elif dataevt & 0x2:
                return SD_WRITEERROR
            elif dataevt & 0x8:
                return SD_CRCERROR
            return SD_OK

def response(comm, length, nocrccheck=False):
    status = wait_cmd_done(comm)
    response = comm.read(csr.CSR_SDCTRL_RESPONSE_ADDR, 4)
    if length == SDCARD_CTRL_RESPONSE_SHORT:
        s = "{:08x}".format(response[3])
        ba = bytearray(response[3].to_bytes(4, 'little'))
    elif length == SDCARD_CTRL_RESPONSE_LONG:
        ba = bytearray()
        s = "{:08x} {:08x} {:08x} {:08x}".format(*response)
        for r in reversed(response):
            ba += bytearray(r.to_bytes(4, 'little'))
    print(s)
    return ba, status

def cmd0(comm):
    print("0: MMC_CMD_GO_IDLE_STATE")
    comm.write(csr.CSR_SDCTRL_ARGUMENT_ADDR, 0x00000000)
    comm.write(csr.CSR_SDCTRL_COMMAND_ADDR, (0 << 8) | SDCARD_CTRL_RESPONSE_NONE)

def cmd2(comm):
    print("2: MMC_CMD_ALL_SEND_CID")
    comm.write(csr.CSR_SDCTRL_ARGUMENT_ADDR, 0x00000000)
    comm.write(csr.CSR_SDCTRL_COMMAND_ADDR, (2 << 8) | SDCARD_CTRL_RESPONSE_LONG)
    return response(comm, SDCARD_CTRL_RESPONSE_LONG)

def cmd3(comm):
    print("3: MMC_CMD_SET_RELATIVE_CSR")
    comm.write(csr.CSR_SDCTRL_ARGUMENT_ADDR, 0x00000000)
    comm.write(csr.CSR_SDCTRL_COMMAND_ADDR, (3 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return response(comm, SDCARD_CTRL_RESPONSE_SHORT)

def cmd6(comm, mode, group, value, destaddr):
    print("6: SD_CMD_SWITCH_FUNC")
    arg = (mode << 31) | 0xffffff
    arg &= ~(0xf << (group * 4))
    arg |= value << (group * 4)
    comm.write(csr.CSR_SDCTRL_ARGUMENT_ADDR, arg)
    comm.write(csr.CSR_SDCTRL_BLOCKSIZE_ADDR, 64-1)
    comm.write(csr.CSR_SDCTRL_BLOCKCOUNT_ADDR, 0)
    comm.write(csr.CSR_RAMWRADDR_ADDRESS_ADDR, destaddr//4)
    comm.write(csr.CSR_SDCTRL_COMMAND_ADDR, (6 << 8) | SDCARD_CTRL_RESPONSE_SHORT | (SDCARD_CTRL_DATA_TRANSFER_READ << 5))
    r = response(comm, SDCARD_CTRL_RESPONSE_SHORT)
    wait_data_done(comm)
    return r

def cmd7(comm, rca):
    print("7: MMC_CMD_SELECT_CARD")
    comm.write(csr.CSR_SDCTRL_ARGUMENT_ADDR, rca << 16)
    comm.write(csr.CSR_SDCTRL_COMMAND_ADDR, (7 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return response(comm, SDCARD_CTRL_RESPONSE_SHORT)

def cmd8(comm):
    print("8: MMC_CMD_SEND_EXT_CSD")
    comm.write(csr.CSR_SDCTRL_ARGUMENT_ADDR, 0x000001aa)
    comm.write(csr.CSR_SDCTRL_COMMAND_ADDR, (8 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return response(comm, SDCARD_CTRL_RESPONSE_SHORT)

def cmd9(comm, rca):
    print("9: MMC_CMD_SEND_CSD")
    comm.write(csr.CSR_SDCTRL_ARGUMENT_ADDR, rca << 16)
    comm.write(csr.CSR_SDCTRL_COMMAND_ADDR, (9 << 8) | SDCARD_CTRL_RESPONSE_LONG)
    return response(comm, SDCARD_CTRL_RESPONSE_LONG)

def cmd11(comm):
    print("11: MMC_CMD_VOLTAGE_SWITCH")
    comm.write(csr.CSR_SDCTRL_ARGUMENT_ADDR, 0x00000000)
    comm.write(csr.CSR_SDCTRL_COMMAND_ADDR, (11 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return response(comm, SDCARD_CTRL_RESPONSE_SHORT)

def cmd12(comm):
    print("12: MMC_CMD_STOP_TRANSMISSION")
    comm.write(csr.CSR_SDCTRL_ARGUMENT_ADDR, 0x00000000)
    comm.write(csr.CSR_SDCTRL_COMMAND_ADDR, (12 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return response(comm, SDCARD_CTRL_RESPONSE_SHORT)

def cmd13(comm, rca):
    print("13: MMC_CMD_SEND_STATUS")
    comm.write(csr.CSR_SDCTRL_ARGUMENT_ADDR, rca << 16)
    comm.write(csr.CSR_SDCTRL_COMMAND_ADDR, (13 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return response(comm, SDCARD_CTRL_RESPONSE_SHORT)

def cmd16(comm, blocklen):
    print("16: MMC_CMD_SET_BLOCKLEN")
    comm.write(csr.CSR_SDCTRL_ARGUMENT_ADDR, blocklen)
    comm.write(csr.CSR_SDCTRL_COMMAND_ADDR, (16 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return response(comm, SDCARD_CTRL_RESPONSE_SHORT)

def cmd17(comm, blkaddr, destaddr):
    print("17: MMC_CMD_READ_SINGLE_BLOCK")
    comm.write(csr.CSR_SDCTRL_ARGUMENT_ADDR, blkaddr)
    comm.write(csr.CSR_SDCTRL_BLOCKSIZE_ADDR, 512-1)
    comm.write(csr.CSR_SDCTRL_BLOCKCOUNT_ADDR, 0)
    comm.write(csr.CSR_RAMWRADDR_ADDRESS_ADDR, destaddr//4)
    comm.write(csr.CSR_SDCTRL_COMMAND_ADDR, (17 << 8) | SDCARD_CTRL_RESPONSE_SHORT | (SDCARD_CTRL_DATA_TRANSFER_READ << 5))
    r = response(comm, SDCARD_CTRL_RESPONSE_SHORT)
    wait_data_done(comm)
    return r

def cmd18(comm, blkaddr, blkcnt, destaddr):
    print("18: MMC_CMD_READ_MULTIPLE_BLOCK")
    comm.write(csr.CSR_SDCTRL_ARGUMENT_ADDR, blkaddr)
    comm.write(csr.CSR_SDCTRL_BLOCKSIZE_ADDR, 512-1)
    comm.write(csr.CSR_SDCTRL_BLOCKCOUNT_ADDR, blkcnt-1)
    comm.write(csr.CSR_RAMWRADDR_ADDRESS_ADDR, destaddr//4)
    comm.write(csr.CSR_SDCTRL_COMMAND_ADDR, (18 << 8) | SDCARD_CTRL_RESPONSE_SHORT | (SDCARD_CTRL_DATA_TRANSFER_READ << 5))
    r = response(comm, SDCARD_CTRL_RESPONSE_SHORT)
    wait_data_done(comm)
    return r

def cmd23(comm, blkcnt):
    print("23: MMC_CMD_SET_BLOCK_COUNT")
    comm.write(csr.CSR_SDCTRL_ARGUMENT_ADDR, blkcnt) # 1 means 1 block
    comm.write(csr.CSR_SDCTRL_COMMAND_ADDR, (23 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return response(comm, SDCARD_CTRL_RESPONSE_SHORT)

def cmd24(comm):
    print("24: MMC_CMD_WRITE_SINGLE_BLOCK")
    comm.write(csr.CSR_SDCTRL_ARGUMENT_ADDR, 0x00000000)
    comm.write(csr.CSR_SDCTRL_BLOCKSIZE_ADDR, 512-1)
    comm.write(csr.CSR_SDCTRL_BLOCKCOUNT_ADDR, 0)
    comm.write(csr.CSR_SDCTRL_COMMAND_ADDR, (24 << 8) | SDCARD_CTRL_RESPONSE_SHORT | (SDCARD_CTRL_DATA_TRANSFER_WRITE << 5))
    return response(comm, SDCARD_CTRL_RESPONSE_SHORT)

def cmd25(comm, blkaddr, blkcnt):
    print("25: MMC_CMD_WRITE_MULTIPLE_BLOCK")
    comm.write(csr.CSR_SDCTRL_ARGUMENT_ADDR, blkaddr)
    comm.write(csr.CSR_SDCTRL_BLOCKSIZE_ADDR, 512-1)
    comm.write(csr.CSR_SDCTRL_BLOCKCOUNT_ADDR, blkcnt-1)
    comm.write(csr.CSR_SDCTRL_COMMAND_ADDR, (25 << 8) | SDCARD_CTRL_RESPONSE_SHORT | (SDCARD_CTRL_DATA_TRANSFER_WRITE << 5))
    return response(comm, SDCARD_CTRL_RESPONSE_SHORT)

def cmd55(comm, rca=0):
    print("55: MMC_CMD_APP_CMD")
    comm.write(csr.CSR_SDCTRL_ARGUMENT_ADDR, rca << 16)
    comm.write(csr.CSR_SDCTRL_COMMAND_ADDR, (55 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return response(comm, SDCARD_CTRL_RESPONSE_SHORT)

def acmd6(comm):
    print("6: SD_CMD_APP_SET_BUS_WIDTH")
    comm.write(csr.CSR_SDCTRL_ARGUMENT_ADDR, 0x00000002)
    comm.write(csr.CSR_SDCTRL_COMMAND_ADDR, (6 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return response(comm, SDCARD_CTRL_RESPONSE_SHORT)

def acmd13(comm, destaddr):
    print("13: SD_CMD_APP_SEND_STATUS")
    comm.write(csr.CSR_SDCTRL_ARGUMENT_ADDR, 0x00000000)
    comm.write(csr.CSR_SDCTRL_BLOCKSIZE_ADDR, 64-1)
    comm.write(csr.CSR_SDCTRL_BLOCKCOUNT_ADDR, 0)
    comm.write(csr.CSR_RAMWRADDR_ADDRESS_ADDR, destaddr//4)
    comm.write(csr.CSR_SDCTRL_COMMAND_ADDR, (13 << 8) | SDCARD_CTRL_RESPONSE_SHORT | (SDCARD_CTRL_DATA_TRANSFER_READ << 5))
    r = response(comm, SDCARD_CTRL_RESPONSE_SHORT)
    wait_data_done(comm)
    return r

def acmd41(comm, hcs=False, s18r=False):
    print("41: SD_CMD_APP_SEND_OP_COND")
    arg = 0x10ff8000
    if hcs:
        arg |= 0x60000000
    if s18r:
        arg |= 0x01000000
    comm.write(csr.CSR_SDCTRL_ARGUMENT_ADDR, arg)
    comm.write(csr.CSR_SDCTRL_COMMAND_ADDR, (41 << 8) | SDCARD_CTRL_RESPONSE_SHORT)
    return response(comm, SDCARD_CTRL_RESPONSE_SHORT, nocrccheck=True)

def acmd51(comm, destaddr):
    print("51: SD_CMD_APP_SEND_SCR")
    comm.write(csr.CSR_SDCTRL_ARGUMENT_ADDR, 0x00000000)
    comm.write(csr.CSR_SDCTRL_BLOCKSIZE_ADDR, 8-1)
    comm.write(csr.CSR_SDCTRL_BLOCKCOUNT_ADDR, 0)
    comm.write(csr.CSR_RAMWRADDR_ADDRESS_ADDR, destaddr//4)
    comm.write(csr.CSR_SDCTRL_COMMAND_ADDR, (51 << 8) | SDCARD_CTRL_RESPONSE_SHORT | (SDCARD_CTRL_DATA_TRANSFER_READ << 5))
    r = response(comm, SDCARD_CTRL_RESPONSE_SHORT)
    wait_data_done(comm)
    return r

def acmd22(comm, destaddr):
    print("22: SD_CMD_APP_SEND_NUM_WR_BLOCKS")
    comm.write(csr.CSR_SDCTRL_ARGUMENT_ADDR, 0x00000000)
    comm.write(csr.CSR_SDCTRL_BLOCKSIZE_ADDR, 4-1)
    comm.write(csr.CSR_SDCTRL_BLOCKCOUNT_ADDR, 0)
    comm.write(csr.CSR_RAMWRADDR_ADDRESS_ADDR, destaddr//4)
    comm.write(csr.CSR_SDCTRL_COMMAND_ADDR, (22 << 8) | SDCARD_CTRL_RESPONSE_SHORT | (SDCARD_CTRL_DATA_TRANSFER_READ << 5))
    r = response(comm, SDCARD_CTRL_RESPONSE_SHORT)
    wait_data_done(comm)
    return r

def settimeout(comm, clkfreq, timeout):
    clktimeout = int(timeout * clkfreq)
    comm.write(csr.CSR_SDCTRL_CMDTIMEOUT_ADDR, clktimeout)
    comm.write(csr.CSR_SDCTRL_DATATIMEOUT_ADDR, clktimeout)

def memset(comm, addr, value, length):
    for i in range(length//4):
        comm.write(addr + 4*i, value)

def wait_ramread_done(comm):
    while not comm.read(csr.CSR_RAMREADER_DONE_ADDR):
        pass

def ramread(comm, srcaddr):
    comm.write(csr.CSR_RAMREADER_ADDRESS_ADDR, srcaddr//4)
    comm.write(csr.CSR_RAMREADER_LENGTH_ADDR, 512)
    print("ramread")
    wait_ramread_done(comm)
    print("done")

def dumpall(comm, addr, length):
    for i in range(length//4):
        print('{:08x}: {:08x}'.format(addr + 4*i, comm.read(addr + 4*i)))

def incremental(comm, addr):
    for i in range(512//4):
        k = (4*i) & 0xff
        dw = k | ((k+1)<<8) | ((k+2)<<16) | ((k+3)<<24)
        comm.write(addr + 4*i, dw & 0xffffffff)

def main(comm, sim=False):
    clkfreq = 50000000
    settimeout(comm, clkfreq, 0.1)

    # RESET CARD
    cmd0(comm)
    cmd8(comm)

    # WAIT FOR CARD READY
    s18r = False
    while True:
        cmd55(comm)
        r3,status = acmd41(comm, hcs=True, s18r=s18r)
        if r3[3] & 0x80:
            print('ready')
            if s18r and (r3[3] & 0x01):
                print('1.8V ok')
            else:
                s18r = False
                print('1.8V NOT ok')
            break

    # VOLTAGE SWITCH
    if s18r:
        cmd11(comm)

    # SEND IDENTIFICATION
    cmd2(comm)

    # SET RELATIVE CARD CSRESS
    r6,status = cmd3(comm)
    rca = decode_rca(r6)

    # SEND CSD
    cmd9(comm, rca)
    # SELECT CARD
    cmd7(comm, rca)

    # SET BUS WIDTH (WIDE)
    cmd55(comm, rca)
    acmd6(comm)

    # SEND SCR
    cmd55(comm, rca)
    acmd51(comm, csr.SRAM_BASE) # SCR register (rouge): 02 35 80 03 00 00 00 00 (Phy Layer Version 3.0)
    dumpall(comm, csr.SRAM_BASE, 8)
    scr = decode_scr(comm, csr.SRAM_BASE)
    if not scr.cmd_support_sbc:
        print("Need CMD23 support")
        return

    # SEND STATUS
    # cmd55(comm, rca)
    # acmd13(comm, csr.SRAM_BASE)
    # dumpall(comm, csr.SRAM_BASE, 64)

    # SWITCH SPEED
    cmd6(comm, SD_SWITCH_CHECK, SD_GROUP_ACCESSMODE, SD_SPEED_SDR25, csr.SRAM_BASE)
    dumpall(comm, csr.SRAM_BASE, 64) # 00 c8 80 01 80 01 80 01 80 01 c0 01 80 03 00 00 01 00 00 00 00 00 00 00 ...
    # cmd6(comm, SD_SWITCH_SWITCH, SD_GROUP_ACCESSMODE, SD_SPEED_SDR25, csr.SRAM_BASE)
    # dumpall(comm, csr.SRAM_BASE, 64)

    # SET BLOCKLEN
    cmd16(comm, 512)

    # # READ ONE BLOCK
    # memset(comm, csr.SRAM_BASE, 0, 1024)
    # cmd17(comm, 0, csr.SRAM_BASE)
    # dumpall(comm, csr.SRAM_BASE, 512)

    # READ MULTIPLE BLOCKS
    memset(comm, csr.SRAM_BASE, 0, 1024)
    cmd23(comm, 2) # If supported in SCR
    cmd18(comm, 0, 2, csr.SRAM_BASE)
    cmd13(comm, rca)
    # dumpall(comm, csr.SRAM_BASE, 1024)

    # WRITE MULTIPLE BLOCKS
    # incremental(comm, csr.SRAM_BASE)
    # writemem(comm)
    memset(comm, csr.SRAM_BASE, 0x0f0f0f0f, 1024)
    blkcnt = 16
    while True:
        r,status = cmd23(comm, blkcnt) # If supported in SCR
        if not status:
            break
    cmd25(comm, 0, blkcnt)
    for i in range(blkcnt):
        ramread(comm, csr.SRAM_BASE)
    if not wait_data_done(comm) == SD_OK:
        cmd12(comm)
    cmd13(comm, rca)
    cmd55(comm, rca)
    acmd22(comm, csr.SRAM_BASE)
    dumpall(comm, csr.SRAM_BASE, 4)

    # READ MULTIPLE BLOCKS
    memset(comm, csr.SRAM_BASE, 0, 1024)
    cmd23(comm, 2) # If supported in SCR
    cmd18(comm, 0, 2, csr.SRAM_BASE)
    cmd13(comm, rca)
    dumpall(comm, csr.SRAM_BASE, 1024)

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('usage: comm.py (uart|udp)')
        sys.exit(1)

    if sys.argv[1] == 'uart':
        comm = CommUART('/dev/ttyUSB1', baudrate=115200, debug=False)
        sim = False
    else:
        comm = CommUDP(server="192.168.2.50", port=20000, csr_csv="build/csr.csv", csr_data_width=32)
        comm.open()
        sim = True

    main(comm, sim)

    comm.close()
