#ifndef __SDCARD_H
#define __SDCARD_H

#include <generated/csr.h>

#define SD_OK         0
#define SD_CRCERROR   1
#define SD_TIMEOUT    2
#define SD_WRITEERROR 3

#define SD_SWITCH_CHECK  0
#define SD_SWITCH_SWITCH 1

#define SD_SPEED_SDR12  0
#define SD_SPEED_SDR25  1
#define SD_SPEED_SDR50  2
#define SD_SPEED_SDR104 3
#define SD_SPEED_DDR50  4

#define SD_DRIVER_STRENGTH_B 0
#define SD_DRIVER_STRENGTH_A 1
#define SD_DRIVER_STRENGTH_C 2
#define SD_DRIVER_STRENGTH_D 3

#define SD_GROUP_ACCESSMODE     0
#define SD_GROUP_COMMANDSYSTEM  1
#define SD_GROUP_DRIVERSTRENGTH 2
#define SD_GROUP_POWERLIMIT     3

#define SDCARD_STREAM_CMD  0
#define SDCARD_STREAM_DATA 1

#define SDCARD_STREAM_READ  0
#define SDCARD_STREAM_WRITE 1

#define SDCARD_STREAM_XFER 0

#define SDCARD_STREAM_STATUS_OK           0b000
#define SDCARD_STREAM_STATUS_TIMEOUT      0b001
#define SDCARD_STREAM_STATUS_DATAACCEPTED 0b010
#define SDCARD_STREAM_STATUS_CRCERROR     0b101
#define SDCARD_STREAM_STATUS_WRITEERROR   0b110

#define SDCARD_CTRL_DATA_TRANSFER_NONE  0
#define SDCARD_CTRL_DATA_TRANSFER_READ  1
#define SDCARD_CTRL_DATA_TRANSFER_WRITE 2

#define SDCARD_CTRL_RESPONSE_NONE  0
#define SDCARD_CTRL_RESPONSE_SHORT 1
#define SDCARD_CTRL_RESPONSE_LONG  2


void sdcrg_set_clk(unsigned int freq);

int sdcard_wait_cmd_done(void);
int sdcard_wait_data_done(void);
int sdcard_wait_response(int length);

void sdcard_go_idle(void);
int sdcard_send_ext_csd(void);
int sdcard_app_cmd(int rca);
int sdcard_app_send_op_cond(int hcc, int s18r);

int sdcard_init(void);

#endif /* __SDCARD_H */
