#!/usr/bin/env python2
#
# SD Card Information
#
# By John Lane 2012-08-03
#
# References:
#
#   1: https://www.sdcard.org/downloads/pls/simplified_specs/Part_1_Physical_Layer_Simplified_Specification_Ver_3.01_Final_100518.pdf
#   2: http://www.kernel.org/doc/Documentation/mmc/mmc-dev-attrs.txt

import sys

def unstuff(x, start, size):
    return (x >> start) & (2**size - 1)

def unstuffs(x,start,size):
    s = ""
    while (size > 0):
        size-=8
        s+=chr(unstuff(x,start+size,8))
    return s

def yesno (n):
    return "yes" if n else "no"

def main(name, args):
    if len(args) != 1:
        print "Syntax: %s <card>" % (name, )
        print "Example: %s mmcblk0" % (name, )
        return 100

    card = args[0]
    dev = "/sys/class/block/%s/device" % (card, )

# CID : Card Identification

    print "------------------------------------------------------------"
    cid = int(file(dev+"/cid").read(), 16)
    print "CID : Card Identification : %x" % cid
    print

    # Bits 120-127 contain the MID. This identifies the card manufacturer
    #              The codes are allocated by SD-3C, LLC (http://www.sd-3c.com)
    #              and would not appear to be publicly available.
    mid = unstuff(cid,120,8)
    print "MID : Manufacturer ID : %d" % mid
    print

    # Bits 104-119 contain the OID. This identifies the card OEM.
    #              The codes are allocated by SD-3C, LLC (http://www.sd-3c.com)
    #              and would not appear to be publicly available.
    oid = unstuffs(cid,104,16)
    print "OID : OEM/Application ID : %s : 0x%x" % (oid,unstuff(cid,104,16))
    print

    # Bits 64-103  contain the product name, a 5 character ASCII string
    pnm = unstuffs(cid,64,40)
    print "PNM : Product Name : %s" % pnm
    print

    # Bits 56-63  contain the product revision, 4 bits major and 4 bits minor.
    prv_major = unstuff(cid,60,4)
    prv_minor = unstuff(cid,56,4)
    print "PRV : Product Revision : %d.%d" % (prv_major,prv_minor)
    print

    # Bits 24-55  contain the product serial number, a 32 bit binary number.
    psn = unstuff(cid,24,32)
    print "PSN : Product Serial Number : %x" % psn
    print

    # Bits 20-23  are reserved

    # Bits 8-19   contain the manufacturing date, 4 bits for month and
    #             8 bits for year, with 0 meaning year 2000.
    mdt_y = unstuff(cid,12,8)+2000
    mdt_m = unstuff(cid,8,4)
    print "MDT : Maunfacturing Date : %d.%d" % (mdt_y,mdt_m)
    print

    # Bits 1-7   contain the CRC checksum
    cid_crc = unstuff(cid,1,7)
    print "CRC : CRC : %d" % cid_crc

    # Bit 0 is unused

# CSD : Card-Specific Data

    print "------------------------------------------------------------"
    csd = int(file(dev+"/csd").read(), 16)
    print "CSD : Card-Specific Data : %x" % csd
    print

    # Bit 126-127 contain the CSD Structure version.
    #             This affects how some csd fields are interpreted.
    csd_structure = unstuff(csd,126,2)
    print "CSD_STRUCTURE: %d" % (csd_structure)
    csd_version = csd_structure + 1

    if csd_version > 2:
            print "Out of range CSD_STRUCTURE: %d" % csd_structure
            return 100

    print "CSD Version : %d" % csd_version
    print

    # Bits 120-125 are reserved

    # Bits 112-119 contain the data read access time.
    #              Bits 0-2 contain the time unit.
    #              Bits 3-6 contain the time value.
    #              Bit 7 is reserved,
    taac = unstuff(csd,112,6)
    taac_time_unit = 10**unstuff(taac,0,3)
    taac_time_value = {
                    0: 0,
                    1: 1.0,
                    2: 1.2,
                    3: 1.3,
                    4: 1.5,
                    5: 2.0,
                    6: 2.5,
                    7: 3.0,
                    8: 3.5,
                    9: 4.0,
                    10: 4.5,
                    11: 5.0,
                    12: 5.5,
                    13: 6.0,
                    14: 7.0,
                    15: 8.0
                    }[unstuff(taac,3,4)]
    print "TAAC: data read access time : %d : 0x%x" % (taac,taac)
    print "                       unit : %d" % taac_time_unit
    print "                      value : %d => %f" % (unstuff(taac,3,4),taac_time_value)
    print "                            : %f (nanoseconds)" % (taac_time_unit * taac_time_value)
    print

    # Bits 104-111 contain the data read access time in clock cycles
    # Unit multiplier is 100 clock cycles.
    nsac = unstuff(csd,104,8)
    print "NSAC: data read access time (in clock cycles) : %d" % (nsac*100)
    print

    # Bits 96-103  contain the maximum data transfer rate.
    #              Bits 0-2 contain the time unit.
    #              Bits 3-6 contain the time value.
    #              Bit 7 is reserved,
    tran_speed = unstuff(csd,96,8)
    tran_speed_unit = (10**unstuff(tran_speed,0,3)) / 10
    tran_speed_value = {
                    0: 0,
                    1: 1.0,
                    2: 1.2,
                    3: 1.3,
                    4: 1.5,
                    5: 2.0,
                    6: 2.5,
                    7: 3.0,
                    8: 3.5,
                    9: 4.0,
                    10: 4.5,
                    11: 5.0,
                    12: 5.5,
                    13: 6.0,
                    14: 7.0,
                    15: 8.0
                    }[unstuff(tran_speed,3,4)]
    print "TRAN_SPEED : max data transfer rate : %d" % tran_speed
    print "                               unit : %d" % tran_speed_unit
    print "                              value : %d => %f" % (unstuff(tran_speed,3,4),tran_speed_value)
    print "                                    : %f (Mbit/s) " % (tran_speed_unit * tran_speed_value)
    print

    # Bits 84-95  contain the card command classes.
    ccc = unstuff(csd,84,12)
    print "CCC : card command classes : %d" % ccc
    c=0
    while ccc > 2**c:
        if (ccc&(2**c)) != 0: print "                           : class %d" % c
        c+=1
    print

    # Bits 80-83 contain the maximum read data block length.
    #            actual value is 2 ^ stored value
    read_bl_len = unstuff(csd,80,4)
    len_bl_read = 2**read_bl_len
    print "READ_BL_LEN : max read data block length : %d" % read_bl_len
    print "LEN_BL_READ : max read block data length : %d bytes ( 2^%d)" % (len_bl_read,read_bl_len)
    print

    # Bit 79 is set if partial blocks for reads are allowed
    #        this is always allowed in an SD Memory Card. It means that smaller blocks
    #        can be used as well. The minimum block size will be one byte.
    read_bl_partial = unstuff(csd,79,1)
    print "READ_BL_PARTIAL : partial blocks for read allowed : %s (%d)" % (yesno(read_bl_partial),read_bl_partial)
    print

    # Bit 78 is set if write block misalignment is allowed. This defines if the data
    #        block to be written by one command can be spread over more than one
    #        physical block. The size of the memory block is defined by WRITE_BL_LEN.
    write_blk_misalign = unstuff(csd,78,1)
    print "WRITE_BLK_MISALIGN : write block misalignment : %s (%d)" % (yesno(write_blk_misalign),write_blk_misalign)
    print

    # Bit 77 is set if read block misalignment is allowed. This defines if the data
    #        block to be read by one command can be spread over more than one
    #        physical block. The size of the memory block is defined by READ_BL_LEN.
    read_blk_misalign = unstuff(csd,77,1)
    print "READ_BLK_MISALIGN : read block misalignment : %s (%d)" % (yesno(read_blk_misalign),read_blk_misalign)
    print

    # Bit 76 is set if DSR (Driver State Register) is implemented. This is true if
    #        the configurable driver stage is integrated on the card.
    dsr_imp = unstuff(csd,76,1)
    print "DSR_IMP : DSR implemented : %s (%d)" % (yesno(dsr_imp),dsr_imp)
    print

    # Bits 74-75 are reserved

    # Bits 47-73 are implemented differently for CSD version 1 and 2
    if csd_version == 1:

        # Bits 62-73 contain the C_SIZE used to compute the user's data card capacity.
        c_size = unstuff(csd,62,12)
        print "C_SIZE : device size : %d : 0x%x" % (c_size,c_size)
        print

        # Lookup for max current at min Vdd
        curr_min = {
                        0: 0.5,
                        1: 1,
                        2: 5,
                        3: 10,
                        4: 25,
                        5: 35,
                        6: 60,
                        7:100
                        }

        # Lookup for max current at max Vdd
        curr_max = {
                        0: 1,
                        1: 5,
                        2: 10,
                        3: 25,
                        4: 35,
                        5: 45,
                        6: 80,
                        7:200
                        }
        # Bits 59-61 contain the maximum read current at the minimum power supply Vdd
        vdd_r_curr_min = unstuff(csd,59,3)
        print "VDD_R_CURR_MIN : max read current @ VDD min : %d : %d mA" % (vdd_r_curr_min,curr_min[vdd_r_curr_min])
        print

        # Bits 56-58 contain the maximum read current at the maximum power supply Vdd
        vdd_r_curr_max = unstuff(csd,56,3)
        print "VDD_R_CURR_MAX : max read current @ VDD max : %d : %d mA" % (vdd_r_curr_max,curr_max[vdd_r_curr_max])
        print

        # Bits 53-55 contain the maximum write current at the minimum power supply Vdd
        vdd_w_curr_min = unstuff(csd,53,3)
        print "VDD_W_CURR_MIN : max write current @ VDD min : %d : %d mA" % (vdd_w_curr_min,curr_min[vdd_w_curr_min])
        print

        # Bits 50-52 contain the maximum write current at the maximum power supply Vdd
        vdd_w_curr_max = unstuff(csd,50,3)
        print "VDD_W_CURR_MAX : max write current @ VDD max : %d : %d mA" % (vdd_w_curr_max,curr_max[vdd_w_curr_max])
        print

        # Bits 47-49 contains a coding factor for computing the total device size
        c_size_mult = unstuff(csd,47,3)
        print "C_SIZE_MULT : device size multiplier : %d" % c_size_mult
        print

        # Card capacity is calculated from C_SIZE and C_SIZE_MULT
        mult = 2**(c_size_mult+2)
        blocknr = (c_size+1) * mult
        block_len = 2**read_bl_len
        memory_capacity = blocknr * block_len
        print "User's data card capacity : %d : 0x%x (B)" % (memory_capacity,memory_capacity)
        print "                          : %d : 0x%x (KiB)" % (memory_capacity/1024,memory_capacity/1024)
        print "                          : %d : 0x%x (MiB)" % (memory_capacity/1024/1024,memory_capacity/1024/1024)
        print


    if csd_version == 2:

        # Bits 70-73 are reserved

        # Bits 48-69 contain the C_SIZE used to compute the user's data card capacity.
        c_size = unstuff(csd,48,22)
        print "C_SIZE : device size : %d : 0x%x" % (c_size,c_size)
        print "         user data area capacity : %d KiB" % ((c_size+1) * 512)
        print "                                 : %d MiB" % ((c_size+1) * 512 / 1024)
        print "                                 : %d GiB" % ((c_size+1) * 512 / 1024**2)
        print

        # Bit 47 is reserved

    # Bit 46 defines the erase block length. This is the granularity of the unit size
    #        of the data to be erased:
    #               0 = granularity is SECTOR SIZE (i.e. can not erase single blocks)
    #               1 = granularity is 512 bytes   (i.e. can erase single blocks)
    erase_block_en = unstuff(csd,46,1)
    print "ERASE_BLOCK_EN : erase single block enable : %s (%d)" % (yesno(erase_block_en),erase_block_en)
    print

    # Bits 39-45 contain the size of an erasable sector as a number of write blocks
    # The actual value is value +1.
    sector_size = unstuff(csd,39,7)+1
    write_bl_len = unstuff(csd,22,4)   # captured out of sequence as needed for this calculation
    len_bl_write = 2**write_bl_len     # computed out of sequence as needed for this calculation
    print "SECTOR_SIZE : erase sector size : %d : 0x%x (write blocks)" % (sector_size,sector_size)
    print "                                : %d B" % (sector_size*len_bl_write)
    print "                                : %d KiB" % (sector_size*len_bl_write/1024)
    print

    # Bits 32-38 contain the write protect group size.
    # The actual value is value +1.
    wp_grp_size = unstuff(csd,32,7)+1
    print "WP_GRP_SIZE : write protect group size : %d" % wp_grp_size
    print "                                       : %d (KiB)" % (wp_grp_size*sector_size)
    print

    # Bit 31 defines if group write protection is available (0=no, 1=yes).
    wp_grp_enable = unstuff(csd,31,1)
    print "WP_GRP_ENABLE : write protect group enable : %s (%d)" % (yesno(wp_grp_enable),wp_grp_enable)
    print

    # Bits 29-30 are reserved

    # Bits 26-28 defines the typical write time as a multiple of the read time
    r2w_factor = 2**unstuff(csd,26,3)
    print "R2W_FACTOR : write speed factor : %d" % r2w_factor
    print "                                : writing is %d times slower than reading" % r2w_factor
    print

    # Bits 22-25 contain the write block length, captured above
    print "WRITE_BL_LEN : max write block data length : %d" % (write_bl_len)
    print "LEN_BL_WRITE : max write block data length : %d bytes ( 2^%d)" % (len_bl_write,write_bl_len)
    print

    # Bit 21 defines wtether partial block sizes can be used in block write commands
    write_bl_partial = unstuff(csd,21,1)
    print "WRITE_BL_PARTIAL : partial blocks for write allowed : %s (%d)" % (yesno(write_bl_partial),write_bl_partial)
    print

    # Bits 16-20 are reserved

    # Bit 15 indicates the selected group of file formats. This field is read only
    #        for ROM. Value is 0 or 1. 1 is reserved. 0: see file_format below.
    file_format_grp = unstuff(csd,15,1)
    print "FILE_FORMAT_GRP : file format group : %d" % file_format_grp
    print

    # Bit 14 is the copy flag and indicates whether the contents are original (0) or
    #        have been copied (1). It's a one time programmable bit (except ROM card).
    copy = unstuff(csd,14,1)
    print "COPY : copy flag : %d" % copy
    print

    # Bit 13 Permanently write protects the card. 0 = not permanently write protected
    perm_write_protect = unstuff(csd,13,1)
    print "PERM_WRITE_PROTECT : permanent write protection : %s (%d)" % (yesno(perm_write_protect),perm_write_protect)
    print

    # Bit 12 Tempoarily write protects the card. 0 = not write protected, 1 = write protecteed
    tmp_write_protect = unstuff(csd,12,1)
    print "TMP_WRITE_PROTECT : temporary write protection : %s (%d)" % (yesno(tmp_write_protect),tmp_write_protect)
    print

    # Bits 10-11 indicates the file format on the card
    file_format = unstuff(csd,10,2)
    file_format_value = "Reserved" if file_format_grp != 0 else {
                    0: "Hard disk-like file system with partition table",
                    1: "DOS FAT (floppy-like) with boot sector only (no partition table)",
                    2: "Universal File Format",
                    3: "Others/Unknown"
                    }[file_format]
    print "FILE_FORMAT : file format : %d : %s" % (file_format, file_format_value)
    print

    # Bits 8-9 are reserved

    # Bits 1-7 contain the CRC
    crc = unstuff(csd,1,7)
    print "CRC : CRC : %d" % crc
    print

    # Bit 0 is unused

# SCR : SD Card Configuration Register

    print "------------------------------------------------------------"
    scr = int(file(dev+"/scr").read(), 16)
    print "SCR : SD Card Configuration Register : %x" % scr
    print

    # Bits 60-63 contain the scr structure version
    scr_structure = unstuff(scr,60,4)
    scr_structure_version = "SCR version 1.0" if scr_structure == 0 else "reserved"
    print "SCR_STRUCTURE : SCR Structure Version : %d : %s" % (scr_structure, scr_structure_version)
    print

    # Bits 56 to 59 contain the SD Memory Card spec version
    sd_spec = unstuff(scr,56,4)
    sd_spec3 = unstuff(scr,47,1)
    print "SD_SPEC : SD Memory Card - Spec. Version : %d" % sd_spec
    print "SD_SPEC3 : Spec. Version 3.00 or higher : %d" % sd_spec3
    sd_spec_version = {
                    0 : "Version 1.0 and 1.01",
                    1 : "Version 1.10",
                    2 : "Version 2.00",
                    3 : "Version 3.0X"
                    }[sd_spec+sd_spec3]
    print "SD_SPEC: SD Memory Card - Spec. Version : %s" % sd_spec_version
    print

    # Bit 55 the data status after erase, either 0 or 1 (card vendor dependent)
    data_stat_after_erase = unstuff(scr,55,1)
    print "DATA_STAT_AFTER_ERASE : data status after erases : %d" % data_stat_after_erase
    print

    # Bits 52-54 indicates the CPRM Security Specification Version for each capacity card.
    sd_security = unstuff(scr,52,3)
    sd_security_version = {
                    0 : "None",
                    1 : "Not Used",
                    2 : "SDSC Card (Security Version 1.01)",
                    3 : "SDHC Card (Security Version 2.00)",
                    4 : "SDXC Card (Security Version 3.xx)"
                    }[sd_security]
    print "SD_SECURITY : CPRM Security Support : %d : %s" % (sd_security,sd_security_version)
    print

    # Bits 48 to 51 indicate the supported DAT bus widths
    sd_bus_widths = unstuff(scr,48,4)
    sd_bus_width_1bit = unstuff(scr,48,1)
    sd_bus_width_4bit = unstuff(scr,50,1)
    print "SD_BUS_WIDTHS : DAT Bus widths supported : %d" % sd_bus_widths
    if (sd_bus_width_1bit == 1): print "                                         : 1 bit (DAT0)"
    if (sd_bus_width_4bit == 1): print "                                         : 4 bit (DAT0-3)"
    print

    # Bit 47 read with SD_SPEC, above

    # Bits 43-46 indicates extended security
    ex_security = unstuff(scr,43,4)
    ex_security_supported = ("not supported","supported")[ex_security > 0]
    print "EX_SECURITY : Extended Security Support : %d (%s)" % (ex_security,ex_security_supported)
    print

    # Bits 34 to 42 are reserved

    # Bits 32-33 are command support bits
    cmd_support = unstuff(scr,32,2)
    cmd_support_scc = unstuff(scr,32,1)
    cmd_support_sbc = unstuff(scr,33,1)
    print "CMD_SUPPORT : Command Support bits : %d" % cmd_support
    if cmd_support_sbc == 1: print "                                   : Set Block Count (CMD23)"
    if cmd_support_scc == 1: print "                                   : Speed Class Control (CMD20)"
    print

    # Bits 0 to 31 are reserved

# Preferred Erase Size

    print "------------------------------------------------------------"
    pes = int(file(dev+"/preferred_erase_size").read())
    print "Preferred Erase Size : %d" % pes
    print "                     : %d MiB" % (pes >> 20)
    print

# Erase Size : the  minimum size, in bytes, of an erase operation.
#              512 if the card is block-addressed, 0 otherwise.

    print "------------------------------------------------------------"
    es = int(file(dev+"/erase_size").read())
    print "Erase Size : %d KiB" % es
    print

# Derived information follows

    print "------------------------------------------------------------"
    print "Derived Data"
    print

    print "LBA Sector Alignment"
    print "--------------------"
    print

    sector_alignment_grain = pes/512

    print "Align each partition with the preferred erase size"
    print "    %d / 512 = %d sectors" % (pes,sector_alignment_grain)

sys.exit(main(sys.argv[0], sys.argv[1:]))
