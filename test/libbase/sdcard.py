from litesdcard.common import *

# clocking

def sdclks7_mmcm_write(wb, adr, data):
    wb.regs.sdclk_mmcm_adr.write(adr)
    wb.regs.sdclk_mmcm_dat_w.write(data)
    wb.regs.sdclk_mmcm_write.write(1)
    while((wb.regs.sdclk_mmcm_drdy.read() & 0x1) == 0):
        pass

# FIXME: add vco frequency check
def sdclks7_get_config(freq):
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

def sdclks7_set_config(wb, freq):
    clock_m, clock_d = sdclk_get_config(freq//1000)
    # clkfbout_mult = clock_m
    if(clock_m%2):
        sdclk_mmcm_write(wb, 0x14, 0x1000 | ((clock_m//2)<<6) | (clock_m//2 + 1))
    else:
        sdclk_mmcm_write(wb, 0x14, 0x1000 | ((clock_m//2)<<6) | clock_m//2)
    # divclk_divide = clock_d
    if (clock_d == 1):
        sdclk_mmcm_write(wb, 0x16, 0x1000)
    elif(clock_d%2):
        sdclk_mmcm_write(wb, 0x16, ((clock_d//2)<<6) | (clock_d//2 + 1))
    else:
        sdclk_mmcm_write(wb, 0x16, ((clock_d//2)<<6) | clock_d//2)
    # clkout0_divide = 10
    sdclk_mmcm_write(wb, 0x8, 0x1000 | (5<<6) | 5)


CLKGEN_STATUS_BUSY = 0x1
CLKGEN_STATUS_PROGDONE = 0x2
CLKGEN_STATUS_LOCKED = 0x4

def sdclks6_dcm_write(wb, cmd, data):
    word = (data << 2) | cmd
    wb.regs.sdclk_cmd_data.write(word)
    wb.regs.sdclk_send_cmd_data.write(1)
    while(wb.regs.sdclk_status.read() & CLKGEN_STATUS_BUSY):
        pass

# FIXME: add vco frequency check
def sdclks6_get_config(freq):
    ideal_m = freq
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

def sdclks6_set_config(wb, freq):
    clock_m, clock_d = sdclks6_get_config(freq//10000)
    sdclks6_dcm_write(wb, 0x1, clock_d-1)
    sdclks6_dcm_write(wb, 0x3, clock_m-1)
    wb.regs.sdclk_send_go.write(1)
    while( not (wb.regs.sdclk_status.read() & CLKGEN_STATUS_PROGDONE)):
        pass
    while(not (wb.regs.sdclk_status.read() & CLKGEN_STATUS_LOCKED)):
        pass


def sdclk_set_config(wb, freq):
    if hasattr(wb.regs, "sdclk_cmd_data"):
        sdclks6_set_config(wb, freq)
    else:
        sdclks7_set_config(wb, freq)

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

def sdcard_bist_checker_start(wb, blkcnt):
    wb.regs.bist_checker_reset.write(1)
    wb.regs.bist_checker_count.write(blkcnt)
    wb.regs.bist_checker_start.write(1)

def sdcard_bist_checker_wait(wb):
    while((wb.regs.bist_checker_done.read() & 0x1) == 0):
        pass

# user

def settimeout(wb, clkfreq, timeout):
    clktimeout = int(timeout * clkfreq)
    wb.regs.sdcore_cmdtimeout.write(clktimeout)
    wb.regs.sdcore_datatimeout.write(clktimeout)


# register decoding

def extract(x, start, size):
    return (x >> start) & (2**size - 1)


def decode_rca(r6):
    rca = int.from_bytes(r6[2:4], 'little')
    print("RCA: {:04x}".format(rca))
    return rca


class CID:
    def __init__(self, cid):
        self.cid = cid

        self.mid = extract(cid, 120-8, 8)
        self.oid = extract(cid, 104-8, 16)
        self.pnm = extract(cid, 64-8, 40)
        self.prv = extract(cid, 56-8, 8)
        self.psn = extract(cid, 24-8, 32)
        self.mdt = extract(cid, 8-8, 12)

    def __str__(self):
        r = """
    CID Register: 0x{:016x}
    Manufacturer ID: 0x{:x}
    Application ID: 0x{:x}
    Product name: {:s}
    Product revision: 0x{:x}
    Product serial number: 0x{:x}
""".format(
    self.cid,
    self.mid,
    self.oid,
    str(self.pnm.to_bytes(5, "big")),
    self.prv,
    self.psn,
    self.mdt
)
        return r

def decode_cid(comm):
    data = comm.read(comm.regs.sdcore_response.addr, 4)
    ba = bytearray()
    for d in data:
        ba += bytearray(d.to_bytes(4, 'big'))
    cid = CID(int(ba.hex(), 16))
    print(cid)
    return cid


class CSD:
    def __init__(self, csd):
        self.csd = csd

        self.csd_structure = extract(csd, 126-8, 2)

        if self.csd_structure == 0:
            self.tran_speed = extract(csd, 96-8, 8)
            self.read_bl_len = extract(csd, 80-8, 4)
            self.device_size = extract(csd, 62-8, 12)
        elif self.csd_structure == 1:
            self.tran_speed = extract(csd, 96-8, 8)
            self.read_bl_len = extract(csd, 80-8, 4)
            self.device_size = extract(csd, 48-8, 22)
        else:
            raise NotImplementedError

    def __str__(self):
        r = """
    CSD Register: 0x{:016x}
    CSD Structure: {}
    Max data transfer rate: {} MB/s
    Max read block length: {} bytes
    Device size: {} GB
""".format(
    self.csd,
    {0: "CSD version 1.0",
     1: "CSD version 2.0",
     2: "CSD version reserved",
     3: "CSD version reserved"}[self.csd_structure],
    self.tran_speed,
    2**self.read_bl_len,
    ((self.device_size + 1)*512)/(1024*1024)
)
        return r

def decode_csd(comm):
    data = comm.read(comm.regs.sdcore_response.addr, 4)
    ba = bytearray()
    for d in data:
        ba += bytearray(d.to_bytes(4, 'big'))
    csd = CSD(int(ba.hex(), 16))
    print(csd)
    return csd


class SCR:
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
