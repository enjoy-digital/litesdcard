#
# This file is part of LiteSDCard.
#
# Copyright (c) 2017-2020 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

SD_OK                             = 0
SD_CRCERROR                       = 1
SD_TIMEOUT                        = 2
SD_WRITEERROR                     = 3

SD_SWITCH_CHECK                   = 0
SD_SWITCH_SWITCH                  = 1

SD_SPEED_SDR12                    = 0
SD_SPEED_SDR25                    = 1
SD_SPEED_SDR50                    = 2
SD_SPEED_SDR104                   = 3
SD_SPEED_DDR50                    = 4

SD_DRIVER_STRENGTH_B              = 0
SD_DRIVER_STRENGTH_A              = 1
SD_DRIVER_STRENGTH_C              = 2
SD_DRIVER_STRENGTH_D              = 3

SD_GROUP_ACCESSMODE               = 0
SD_GROUP_COMMANDSYSTEM            = 1
SD_GROUP_DRIVERSTRENGTH           = 2
SD_GROUP_POWERLIMIT               = 3

SDCARD_STREAM_STATUS_OK           = 0b000
SDCARD_STREAM_STATUS_TIMEOUT      = 0b001
SDCARD_STREAM_STATUS_DATAACCEPTED = 0b010
SDCARD_STREAM_STATUS_CRCERROR     = 0b101
SDCARD_STREAM_STATUS_WRITEERROR   = 0b110

SDCARD_CTRL_DATA_TRANSFER_NONE    = 0
SDCARD_CTRL_DATA_TRANSFER_READ    = 1
SDCARD_CTRL_DATA_TRANSFER_WRITE   = 2

SDCARD_CTRL_RESPONSE_NONE         = 0
SDCARD_CTRL_RESPONSE_SHORT        = 1
SDCARD_CTRL_RESPONSE_LONG         = 2

SDCARD_TUNING_BLOCK = [
    0xff0fff00, 0xffccc3cc, 0xc33cccff, 0xfefffeef,
    0xffdfffdd, 0xfffbfffb, 0xbfff7fff, 0x77f7bdef,
    0xfff0fff0, 0x0ffccc3c, 0xcc33cccf, 0xffefffee,
    0xfffdfffd, 0xdfffbfff, 0xbbfff7ff, 0xf77f7bde,
]