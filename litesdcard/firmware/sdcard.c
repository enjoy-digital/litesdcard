#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <generated/csr.h>
#include <generated/mem.h>
#include <hw/flags.h>
#include <system.h>

#include "sdcard.h"

/* clocking */

static void sdcrg_mmcm_write(unsigned int adr, unsigned int data) {
	sdcrg_mmcm_adr_write(adr);
	sdcrg_mmcm_dat_w_write(data);
	sdcrg_mmcm_write_write(1);
	while(!sdcrg_mmcm_drdy_read());
}


static void sdcrg_set_config(unsigned int m, unsigned int d) {
	/* clkfbout_mult = m */
	if(m%2)
		sdcrg_mmcm_write(0x14, 0x1000 | ((m/2)<<6) | (m/2 + 1));
	else
		sdcrg_mmcm_write(0x14, 0x1000 | ((m/2)<<6) | m/2);
	/* divclk_divide = d */
	if (d == 1)
		sdcrg_mmcm_write(0x16, 0x1000);
	else if(d%2)
		sdcrg_mmcm_write(0x16, ((d/2)<<6) | (d/2 + 1));
	else
		sdcrg_mmcm_write(0x16, ((d/2)<<6) | d/2);
	/* clkout0_divide = 10 */
	sdcrg_mmcm_write(0x8, 0x1000 | (5<<6) | 5);
	/* clkout1_divide = 2 */
	sdcrg_mmcm_write(0xa, 0x1000 | (1<<6) | 1);
}

/* FIXME: add vco frequency check */
static void sdcrg_get_config(unsigned int freq, unsigned int *best_m, unsigned int *best_d) {
	unsigned int ideal_m, ideal_d;
	unsigned int bm, bd;
	unsigned int m, d;
	unsigned int diff_current;
	unsigned int diff_tested;

	ideal_m = freq;
	ideal_d = 10000;

	bm = 1;
	bd = 0;
	for(d=1;d<=128;d++)
		for(m=2;m<=128;m++) {
			/* common denominator is d*bd*ideal_d */
			diff_current = abs(d*ideal_d*bm - d*bd*ideal_m);
			diff_tested = abs(bd*ideal_d*m - d*bd*ideal_m);
			if(diff_tested < diff_current) {
				bm = m;
				bd = d;
			}
		}
	*best_m = bm;
	*best_d = bd;
}

void sdcrg_set_clk(unsigned int freq) {
	unsigned int clk_m, clk_d;

	sdcrg_get_config(1000*freq, &clk_m, &clk_d);
	sdcrg_set_config(clk_m, clk_d);
}

/* command utils */

unsigned int sdcard_response[4];

int sdcard_wait_cmd_done(void) {
	unsigned int cmdevt;
	while (1) {
		cmdevt = sdcore_cmdevt_read();
		printf("cmdevt: %08x\n", cmdevt);
		if (cmdevt & 0x1) {
			if (cmdevt & 0x4) {
				printf("cmdevt: SD_TIMEOUT\n");
				return SD_TIMEOUT;
			}
			else if (cmdevt & 0x8) {
				printf("cmdevt: SD_CRCERROR\n");
				return SD_CRCERROR;
			}
			return SD_OK;
		}
	}
}

int sdcard_wait_data_done(void) {
	unsigned int dataevt;
	while (1) {
		dataevt = sdcore_dataevt_read();
		printf("dataevt: %08x\n", dataevt);
		if (dataevt & 0x1) {
			if (dataevt & 0x4)
				return SD_TIMEOUT;
			else if (dataevt & 0x8)
				return SD_CRCERROR;
			return SD_OK;
		}
	}
}

int sdcard_wait_response(void) {
	int i;
	int status;
	volatile unsigned int *buffer = (unsigned int *)CSR_SDCORE_RESPONSE_ADDR;

	status = sdcard_wait_cmd_done();

	for(i=0; i<4; i++) {
		printf("%08x\n", buffer[i]);
		sdcard_response[i] = buffer[i];
	}

	return status;
}

/* commands */

void sdcard_go_idle(void) {
	printf("CMD0: GO_IDLE\n");
	sdcore_argument_write(0x00000000);
	sdcore_command_write((0 << 8) | SDCARD_CTRL_RESPONSE_NONE);
}

int sdcard_send_ext_csd(void) {
	printf("CMD8: SEND_EXT_CSD\n");
	sdcore_argument_write(0x000001aa);
	sdcore_command_write((8 << 8) | SDCARD_CTRL_RESPONSE_NONE);
	return sdcard_wait_response();
}

int sdcard_app_cmd(int rca) {
	printf("CMD55: APP_CMD\n");
	sdcore_argument_write(rca << 16);
	sdcore_command_write((55 << 8) | SDCARD_CTRL_RESPONSE_SHORT);
	return sdcard_wait_response();
}

int sdcard_app_send_op_cond(int hcs, int s18r) {
	unsigned int arg;
	printf("ACMD41: APP_SEND_OP_COND\n");
	arg = 0x10ff8000;
	if (hcs)
		arg |= 0x60000000;
	if (s18r)
		arg |= 0x01000000;
	sdcore_argument_write(arg);
	sdcore_command_write((41 << 8) | SDCARD_CTRL_RESPONSE_SHORT);
	return sdcard_wait_response();
}

int sdcard_all_send_cid(void) {
	printf("CMD2: ALL_SEND_CID\n");
	sdcore_argument_write(0x00000000);
	sdcore_command_write((2 << 8) | SDCARD_CTRL_RESPONSE_LONG);
	return sdcard_wait_response();
}

int sdcard_set_relative_address(void) {
	printf("CMD3: SET_RELATIVE_ADDRESS\n");
	sdcore_argument_write(0x00000000);
	sdcore_command_write((3 << 8) | SDCARD_CTRL_RESPONSE_SHORT);
	return sdcard_wait_response();
}

int sdcard_send_cid(unsigned int rca) {
	printf("CMD10: SEND_CID\n");
	sdcore_argument_write(rca << 16);
	sdcore_command_write((10 << 8) | SDCARD_CTRL_RESPONSE_LONG);
	return sdcard_wait_response();
}

int sdcard_send_csd(unsigned int rca) {
	printf("CMD9: SEND_CSD\n");
	sdcore_argument_write(rca << 16);
	sdcore_command_write((9 << 8) | SDCARD_CTRL_RESPONSE_LONG);
	return sdcard_wait_response();
}

int sdcard_select_card(unsigned int rca) {
	printf("CMD7: SELECT_CARD\n");
	sdcore_argument_write(rca << 16);
	sdcore_command_write((7 << 8) | SDCARD_CTRL_RESPONSE_SHORT);
	return sdcard_wait_response();
}

int sdcard_app_set_bus_width(void) {
	printf("ACMD6: SET_BUS_WIDTH\n");
	sdcore_argument_write(0x00000002);
	sdcore_command_write((6 << 8) | SDCARD_CTRL_RESPONSE_SHORT);
	return sdcard_wait_response();
}

int sdcard_switch(unsigned int mode, unsigned int group, unsigned int value, unsigned int dstaddr) {
	unsigned int arg;

	printf("CMD6: SWITCH_FUNC\n");
	arg = (mode << 31) | 0xffffff;
	arg &= ~(0xf << (group * 4));
	arg |= value << (group * 4);
	printf("0x%8x\n", arg);

	sdcore_argument_write(arg);
	sdcore_blocksize_write(64);
	sdcore_blockcount_write(1);
	ramwriter_address_write(dstaddr/4);
	sdcore_command_write((6 << 8) | SDCARD_CTRL_RESPONSE_SHORT |
						 (SDCARD_CTRL_DATA_TRANSFER_READ << 5));
	sdcard_wait_response();
	return sdcard_wait_data_done();
}

int sdcard_app_send_scr(unsigned int dstaddr) {
	printf("CMD51: APP_SEND_SCR\n");
	sdcore_argument_write(0x00000000);
	sdcore_blocksize_write(8);
	sdcore_blockcount_write(1);
	ramwriter_address_write(dstaddr/4);
	sdcore_command_write((51 << 8) | SDCARD_CTRL_RESPONSE_SHORT |
						 (SDCARD_CTRL_DATA_TRANSFER_READ << 5));
	sdcard_wait_response();
	return sdcard_wait_data_done();
}


int sdcard_app_set_blocklen(unsigned int blocklen) {
	printf("CMD16: SET_BLOCKLEN\n");
	sdcore_argument_write(blocklen);
	sdcore_command_write((16 << 8) | SDCARD_CTRL_RESPONSE_SHORT);
	return sdcard_wait_response();
}

int sdcard_write_single_block(unsigned int blockaddr, unsigned int srcaddr) {
	printf("CMD24: WRITE_SINGLE_BLOCK\n");
	sdcore_argument_write(blockaddr);
	sdcore_blocksize_write(512);
	sdcore_blockcount_write(1);
	sdcore_command_write((24 << 8) | SDCARD_CTRL_RESPONSE_SHORT |
						 (SDCARD_CTRL_DATA_TRANSFER_WRITE << 5));
	sdcard_wait_response();

	ramreader_address_write(srcaddr/4);
	ramreader_length_write(512);
	while ((ramreader_done_read() & 0x01) == 0);

	return 0;
}

int sdcard_read_single_block(unsigned int blockaddr, unsigned int dstaddr) {
	printf("CMD17: READ_SINGLE_BLOCK\n");
	sdcore_argument_write(blockaddr);
	sdcore_blocksize_write(512);
	sdcore_blockcount_write(1);
	ramwriter_address_write(dstaddr/4);
	sdcore_command_write((17 << 8) | SDCARD_CTRL_RESPONSE_SHORT |
						 (SDCARD_CTRL_DATA_TRANSFER_READ << 5));
	sdcard_wait_response();
	return sdcard_wait_data_done();
}

void sdcard_decode_cid(void) {
	printf(
		"CID Register: 0x%08x%08x%08x%08x\n"
		"Manufacturer ID: 0x%x\n"
		"Application ID 0x%x\n"
		"Product name: %c%c%c%c%c\n",
			sdcard_response[0],
			sdcard_response[1],
			sdcard_response[2],
			sdcard_response[3],

			(sdcard_response[0] >> 16) & 0xffff,

			sdcard_response[0] & 0xffff,

			(sdcard_response[1] >> 24) & 0xff,
			(sdcard_response[1] >> 16) & 0xff,
			(sdcard_response[1] >>  8) & 0xff,
			(sdcard_response[1] >>  0) & 0xff,
			(sdcard_response[2] >> 24) & 0xff
		);
}

void sdcard_decode_csd(void) {
	/* FIXME: only support CSR structure version 2.0 */
	printf(
		"CSD Register: 0x%x%08x%08x%08x\n"
		"Max data transfer rate: %d MB/s\n"
		"Max read block length: %d bytes\n"
		"Device size: %d GB\n",
			sdcard_response[0],
			sdcard_response[1],
			sdcard_response[2],
			sdcard_response[3],

			(sdcard_response[1] >> 24) & 0xff,

			(1 << ((sdcard_response[1] >> 8) & 0xf)),

			((sdcard_response[2] >> 8) & 0x3fffff)*512/(1024*1024)
	);
}

static unsigned int seed_to_data(unsigned int seed, unsigned char random) {
	if (random)
		return (1664525*seed + 1013904223) & 0xffffffff;
	else
		return seed;
}

static void write_pattern(unsigned int baseaddr, unsigned int length, unsigned int offset) {
	unsigned int i;
	volatile unsigned int *buffer = (unsigned int *)baseaddr;

	for(i=offset; i<length+offset; i++) {
		buffer[i] = seed_to_data(i, 0);
	}
}

static unsigned int check_pattern(unsigned int baseaddr, unsigned int length, unsigned int offset) {
	unsigned int i;
	unsigned int errors;
	volatile unsigned int *buffer = (unsigned int *)baseaddr;

	for(i=offset; i<length+offset; i++) {
		if (buffer[i] != seed_to_data(i, 0))
			errors++;
	}

	return errors;
}


/* user */

static void busy_wait(unsigned int ds)
{
	timer0_en_write(0);
	timer0_reload_write(0);
	timer0_load_write(SYSTEM_CLOCK_FREQUENCY/10*ds);
	timer0_en_write(1);
	timer0_update_value_write(1);
	while(timer0_value_read()) timer0_update_value_write(1);
}

int sdcard_init(unsigned int freq) {
	unsigned short rca;

	/* low speed clock */
	sdcrg_set_clk(10);
	busy_wait(2);

	/* reset card */
	sdcard_go_idle();
	sdcard_send_ext_csd();
	busy_wait(2);

	/* wait for card to be ready */
	/* FIXME: 1.8v support */
	for(;;) {
		sdcard_app_cmd(0);
		sdcard_app_send_op_cond(1, 0);
		if (sdcard_response[3] & 0x80000000) {
			break;
		}
		busy_wait(1);
	}

	/* send identification */
	sdcard_all_send_cid();
	sdcard_decode_cid();

	/* set relative card address */
	sdcard_set_relative_address();
	rca = (sdcard_response[3] >> 16) & 0xffff;

	/* set cid */
	/* FIXME: add cid decoding (optional) */
	sdcard_send_cid(rca);

	/* set csd */
	sdcard_send_csd(rca);
	sdcard_decode_csd();

	/* select card */
	sdcard_select_card(rca);

	/* set bus width */
	sdcard_app_cmd(rca);
	sdcard_app_set_bus_width();

	/* switch speed */
	sdcard_switch(SD_SWITCH_SWITCH, SD_GROUP_ACCESSMODE, SD_SPEED_SDR50, SRAM_BASE);

	/* switch driver strength */
	sdcard_switch(SD_SWITCH_SWITCH, SD_GROUP_DRIVERSTRENGTH, SD_DRIVER_STRENGTH_D, SRAM_BASE);

	/* full speed clock */
	sdcrg_set_clk(freq);
	busy_wait(2);

	/* send scr */
	/* FIXME: add scr decoding (optional) */
	sdcard_app_cmd(rca);
	sdcard_app_send_scr(SRAM_BASE);

	/* set block length */
	sdcard_app_set_blocklen(512);

	return 0;
}

int sdcard_test(void) {
	unsigned int i;
	unsigned int errors;

	errors = 0;

	for(i=0; i<8; i++) {
		/* write */
		write_pattern(SDSRAM_BASE, 512/4, 0);
		sdcard_write_single_block(0, SDSRAM_BASE);

		/* read */
		sdcard_read_single_block(0, SDSRAM_BASE);
		errors += check_pattern(SDSRAM_BASE, 512/4, 0);
	}

	printf("errors : %d\n", errors);

	return 0;
}
