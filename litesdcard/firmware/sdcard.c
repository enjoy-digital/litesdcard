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

int sdcard_init(void) {
	unsigned short rca;

	/* low speed clock */
	sdcrg_set_clk(10);

	/* reset card */
	sdcard_go_idle();
	sdcard_send_ext_csd();
	busy_wait(1);

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

	/* set relative card address */
	sdcard_set_relative_address();
	rca = (sdcard_response[3] >> 16) & 0xffff;

	/* set cid */
	/* FIXME: add cid decoding (optional) */
	sdcard_send_cid(rca);

	/* set csd */
	/* FIXME: add csd decoding (optional) */
	sdcard_send_csd(rca);

	/* select card */
	sdcard_select_card(rca);

	/* set bus width */
	sdcard_app_cmd(rca);
	sdcard_app_set_bus_width();

	/* switch speed */
	/* FIXME */

	/* switch driver strength */
	/* FIXME */

	/* send scr */
	/* FIXME */

	/* set block length */
	/* FIXME */

	return 0;
}
