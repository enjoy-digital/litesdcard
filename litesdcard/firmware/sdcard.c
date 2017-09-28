#include <stdio.h>
#include <stdlib.h>

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

int sdcard_wait_response(int length) {
	unsigned int status;
	volatile unsigned int *response = (unsigned int *)CSR_SDCORE_RESPONSE_ADDR;

	status = sdcard_wait_cmd_done();

	if (length == SDCARD_CTRL_RESPONSE_SHORT) {
		printf("0x%08x\n", response[0]);
		printf("0x%08x\n", response[1]);
		printf("0x%08x\n", response[2]);
		printf("0x%08x\n", response[3]);
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
	return sdcard_wait_response(SDCARD_CTRL_RESPONSE_SHORT);
}

int sdcard_app_cmd(int rca) {
	printf("CMD55: APP_CMD\n");
	sdcore_argument_write(rca << 16);
	sdcore_command_write((55 << 8) | SDCARD_CTRL_RESPONSE_SHORT);
	return sdcard_wait_response(SDCARD_CTRL_RESPONSE_SHORT);
}

int sdcard_app_send_op_cond(int hcs, int s18r) {
	unsigned int arg;

	printf("CMD41: APP_SEND_OP_COND\n");
	arg = 0x10ff8000;
	if (hcs)
		arg |= 0x60000000;
	if (s18r)
		arg |= 0x01000000;
	sdcore_argument_write(arg);
	sdcore_command_write((41 << 8) | SDCARD_CTRL_RESPONSE_SHORT);

	return sdcard_wait_response(SDCARD_CTRL_RESPONSE_SHORT);
}

/* user */

int sdcard_init(void) {
	/* reset card */
	sdcard_go_idle();
	sdcard_send_ext_csd();

	/* wait for card to be ready */
	/* FIXME */
	sdcard_app_cmd(0);
	sdcard_app_send_op_cond(1, 0);

	/* send identification */
	/* FIXME */

	/* set relative card address */
	/* FIXME */

	/* set cid */
	/* FIXME */

	/* set csd */
	/* FIXME */

	/* select card */
	/* FIXME */

	/* set bus width */
	/* FIXME */

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
