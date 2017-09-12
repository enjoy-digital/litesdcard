/*
   Copyright 2015, Google Inc.

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.

   This version has been modified with SPI mode support. Changes are:
   Copyright 2017, Micah Elizabeth Scott, licensed under identical terms.
*/

module sd_link (
   input  wire         clk_50,
   input  wire         reset_n,

   output wire [3:0]   link_card_state,

   input  wire [47:0]  phy_cmd_in,
   input  wire         phy_cmd_in_crc_good,
   input  wire         phy_cmd_in_act,
   input  wire         phy_spi_sel,
   output reg          phy_data_in_act,
   input  wire         phy_data_in_busy,
   output reg          phy_data_in_stop,
   output reg          phy_data_in_another,
   input  wire         phy_data_in_done,
   input  wire         phy_data_in_crc_good,

   output reg  [135:0] phy_resp_out,
   output reg  [3:0]   phy_resp_type,
   output reg          phy_resp_busy,
   output reg          phy_resp_act,
   input  wire         phy_resp_done,
   output reg          phy_mode_4bit,
   output reg          phy_mode_spi,
   output reg          phy_mode_crc_disable,
   output reg  [511:0] phy_data_out_reg,
   output reg          phy_data_out_src,
   output reg  [9:0]   phy_data_out_len,
   input  wire         phy_data_out_busy,
   output reg          phy_data_out_act,
   output reg          phy_data_out_stop,
   input  wire         phy_data_out_done,

   output reg          block_read_act,
   input  wire         block_read_go,
   output reg  [31:0]  block_read_addr,
   output reg  [31:0]  block_read_byteaddr,
   output reg  [31:0]  block_read_num,
   output reg          block_read_stop,

   output reg          block_write_act,
   input  wire         block_write_done,
   output reg  [31:0]  block_write_addr,
   output reg  [31:0]  block_write_byteaddr,
   output reg  [31:0]  block_write_num,
   output reg  [22:0]  block_preerase_num,

   output reg  [31:0]  block_erase_start,
   output reg  [31:0]  block_erase_end,

   input  wire         opt_enable_hs,

   output reg  [5:0]   cmd_in_last,
   output reg          info_card_desel,
   output reg          err_op_out_range,
   output reg          err_unhandled_cmd,
   output reg          err_cmd_crc,

   // Debug/status outputs
   output reg          host_hc_support,
   output wire [5:0]   cmd_in_cmd,
   output reg  [31:0]  card_status,
   output reg  [15:0]  dc,
   output reg  [15:0]  ddc,
   output reg  [6:0]   state
);

`include "sd_params.vh"
`include "sd_const.vh"

reg  [47:0]  cmd_in_latch;
//    wire   [5:0]   cmd_in_cmd = cmd_in_latch[45:40] /* synthesis noprune */;
assign cmd_in_cmd = cmd_in_latch[45:40];
wire [31:0]  cmd_in_arg = cmd_in_latch[39:8] /* synthesis noprune */;
wire [6:0]   cmd_in_crc = cmd_in_latch[7:1];

// High capacity mode uses blocks natively, legacy mode byte offsets are converted here
wire [31:0]  cmd_in_arg_blockaddr = host_hc_support ? cmd_in_arg : { 9'b0, cmd_in_arg[31:9] };
wire [31:0]  cmd_in_arg_byteaddr = host_hc_support ? { cmd_in_arg[22:0], 9'b0 } : cmd_in_arg;

reg  [3:0]   card_state;
assign       link_card_state = card_state;
reg  [3:0]   card_state_next;
reg  [2:0]   card_erase_state;
reg          card_appcmd;
reg  [127:0] card_sd_status;
reg  [127:0] card_csd;
reg  [127:0] card_cid;
reg  [31:0]  card_ocr;
reg  [15:0]  card_rca;
reg  [63:0]  card_scr;
reg  [111:0] card_function_caps;
reg  [23:0]  card_function;
reg  [23:0]  card_function_check;
reg  [31:0]  card_blocks_written;
reg  [127:0] resp_arg; // for 32 or 128bit
reg  [3:0]   resp_type;

parameter [6:0] ST_RESET      = 'd0,
                ST_IDLE       = 'd4,
                ST_CMD_ACT    = 'd8,
                ST_CMD_RESP_0 = 'd9,
                ST_CMD_RESP_1 = 'd10,
                ST_CMD_RESP_2 = 'd11,
                ST_LAST       = 'd127;

reg  [6:0]   data_state;
parameter [6:0] DST_RESET      = 'd0,
                DST_IDLE       = 'd1,
                DST_IDLE_1     = 'd2,
                DST_DATA_OUT_0 = 'd10,
                DST_DATA_OUT_1 = 'd11,
                DST_DATA_OUT_2 = 'd12,
                DST_DATA_OUT_3 = 'd13,
                DST_DATA_OUT_4 = 'd14,
                DST_DATA_OUT_5 = 'd15,
                DST_DATA_IN_0  = 'd20,
                DST_DATA_IN_1  = 'd21,
                DST_DATA_IN_2  = 'd22,
                DST_DATA_IN_3  = 'd23,
                DST_DATA_IN_4  = 'd24,
                DST_DATA_IN_5  = 'd25,
                DST_LAST       = 'd127;

wire [15:0] spi_status_word = {
   // R1
   1'b0,
   card_status[STAT_ADDRESS_ERROR] | card_status[STAT_BLOCK_LEN_ERROR] | card_status[STAT_ERASE_PARAM],
   card_status[STAT_ADDRESS_ERROR],
   card_status[STAT_ERASE_SEQ_ERROR],
   card_status[STAT_COM_CRC_ERROR],
   card_status[STAT_ILLEGAL_COMMAND],
   card_status[STAT_ERASE_RESET],
   card_state == CARD_IDLE,
   // R2
   card_status[STAT_OUT_OF_RANGE] | card_status[STAT_CSD_OVERWRITE],
   card_status[STAT_ERASE_PARAM],
   card_status[STAT_WP_VIOLATION],
   card_status[STAT_CARD_ECC_FAILED],
   card_status[STAT_CC_ERROR],
   card_status[STAT_ERROR],
   card_status[STAT_WP_ERASE_SKIP] | card_status[STAT_LOCK_UNLOCK_FAILED],
   card_status[STAT_CARD_IS_LOCKED]
};

reg data_op_send_scr;
reg data_op_send_cid;
reg data_op_send_csd;
reg data_op_send_sdstatus;
reg data_op_send_function;
reg data_op_send_written;
reg data_op_send_block;
reg data_op_send_block_queue;

reg data_op_recv_block;

// synchronizers
wire        reset_s;
wire [47:0] cmd_in_s;
wire        cmd_in_crc_good_s;
wire        cmd_in_act_s, cmd_in_act_r;
wire        spi_sel_s;
wire        data_in_busy_s;
wire        data_in_done_s, data_in_done_r;
wire        data_in_crc_good_s;
wire        resp_done_s, resp_done_r;
wire        data_out_busy_s;
wire        data_out_done_s, data_out_done_r;
synch_3       a(reset_n, reset_s, clk_50);
synch_3 #(48) b(phy_cmd_in, cmd_in_s, clk_50);
synch_3       c(phy_cmd_in_crc_good, cmd_in_crc_good_s, clk_50);
synch_3r      d(phy_cmd_in_act, cmd_in_act_s, clk_50, cmd_in_act_r);
synch_3       e(phy_data_in_busy, data_in_busy_s, clk_50);
synch_3r      f(phy_data_in_done, data_in_done_s, clk_50, data_in_done_r);
synch_3       g(phy_data_in_crc_good, data_in_crc_good_s, clk_50);
synch_3r      h(phy_resp_done, resp_done_s, clk_50, resp_done_r);
synch_3       i(phy_data_out_busy, data_out_busy_s, clk_50);
synch_3r      j(phy_data_out_done, data_out_done_s, clk_50, data_out_done_r);
synch_3       k(phy_spi_sel, spi_sel_s, clk_50);


always @(posedge clk_50) begin

   // free running counter
   dc <= dc + 1'b1;

   case(state)
   ST_RESET: begin
      dc <= 0;
      info_card_desel <= 0;
      err_op_out_range <= 0;
      err_unhandled_cmd <= 0;
      err_cmd_crc <= 0;
      card_erase_state <= 0;
      card_blocks_written <= 0;
      card_appcmd <= 0;
      card_rca <= 16'h0;
      card_status <= 0;
      card_status[STAT_READY_FOR_DATA] <= 1'b1;
      card_state <= CARD_IDLE;
      card_ocr <= {8'b01000000, OCR_VOLTAGE_WINDOW}; // high capacity, not powered up
      card_cid <= {CID_FIELD_MID, CID_FIELD_OID, CID_FIELD_PNM, CID_FIELD_PRV, CID_FIELD_PSN,
               4'b0, CID_FIELD_MDT, 8'hFF};
      card_csd <= {CSD_CSD_STRUCTURE, 6'h0, CSD_TAAC, CSD_NSAC, CSD_TRAN_SPEED_25, CSD_CCC, CSD_READ_BL_LEN,
               CSD_READ_BL_PARTIAL, CSD_WRITE_BLK_MISALIGN, CSD_READ_BLK_MISALIGN, CSD_DSR_IMPL, 6'h0,
               CSD_C_SIZE, 1'b0, CSD_ERASE_BLK_EN, CSD_SECTOR_SIZE, CSD_WP_GRP_SIZE, CSD_WP_GRP_ENABLE,
               2'b00, CSD_R2W_FACTOR, CSD_WRITE_BL_LEN, CSD_WRITE_BL_PARTIAL, 5'h0, CSD_FILE_FORMAT_GRP,
               CSD_COPY, CSD_PERM_WRITE_PROTECT, CSD_TMP_WRITE_PROTECT, CSD_FILE_FORMAT, 2'h0, 8'hFF};
      card_scr <= {SCR_SCR_STRUCTURE, SCR_SD_SPEC, SCR_DATA_STATE_ERASE, SCR_SD_SECURITY, SCR_SD_BUS_WIDTHS,
               SCR_SD_SPEC3, 13'h0, 2'h0, 32'h0};
      card_sd_status <= {   STAT_DAT_BUS_WIDTH_1, STAT_SECURED_MODE, 7'h0, 6'h0, STAT_SD_CARD_TYPE,
                     STAT_SIZE_OF_PROT_AREA, STAT_SPEED_CLASS, STAT_PERFORMANCE_MOVE, STAT_AU_SIZE,
                     4'h0, STAT_ERASE_SIZE, STAT_ERASE_TIMEOUT, STAT_ERASE_OFFSET, 15'h0};
      // set high speed capability bit
      card_function_caps <= 112'h0032800180018001800180018001 | opt_enable_hs ? 2'b10 : 2'b00;
      card_function <= 24'h0;
      card_function_check <= 24'h0;

      data_op_send_scr <= 0;
      data_op_send_cid <= 0;
      data_op_send_csd <= 0;
      data_op_send_sdstatus <= 0;
      data_op_send_function <= 0;
      data_op_send_written <= 0;
      data_op_send_block <= 0;
      data_op_send_block_queue <= 0;

      data_op_recv_block <= 0;

      phy_data_in_act <= 0;
      phy_data_in_stop <= 0;
      phy_resp_act <= 0;
      phy_data_out_act <= 0;
      phy_data_out_stop <= 0;
      phy_mode_4bit <= 0;
      phy_mode_crc_disable <= phy_mode_spi;

      block_read_act <= 0;
      block_read_num <= 0;
      block_read_stop <= 0;
      block_write_act <= 0;
      block_write_num <= 0;
      block_preerase_num <= 0;

      // By default the host doesn't support high capacity mode
      host_hc_support <= 0;

      // In SPI mode, reset gets an R1 response
      state <= phy_mode_spi ? ST_CMD_RESP_0 : ST_IDLE;
   end
   ST_IDLE: begin
      // rising edge + crc is good
      if(cmd_in_act_r) begin
         phy_resp_act <= 0;
         if(cmd_in_crc_good_s) begin
            // new command
            cmd_in_latch <= phy_cmd_in;
            card_status[STAT_COM_CRC_ERROR] <= 0;
            card_status[STAT_ILLEGAL_COMMAND] <= 0;
            state <= ST_CMD_ACT;
            cmd_in_last <= cmd_in_cmd;
         end else begin
            // bad crc
            err_cmd_crc <= 1;
            card_status[STAT_COM_CRC_ERROR] <= 1;
         end
      end
   end
   ST_CMD_ACT: begin
      // parse the command
      state <= ST_CMD_RESP_0;
      // unless otherwise, stay in the same SD state
      card_state_next <= card_state;
      // unless set below, assume it's illegal
      resp_type <= RESP_BAD;

      if(~card_appcmd) begin
         // CMD
         case(cmd_in_cmd)
         CMD0_GO_IDLE: begin
            if(card_state != CARD_INA) begin
               // reset to default, optionally enter SPI mode.
               state <= ST_RESET;
               data_state <= DST_RESET;
               if (phy_mode_spi | spi_sel_s) begin
                  phy_mode_spi <= 1'b1;
                  resp_type <= RESP_R1;
               end
               else begin
                  resp_type <= RESP_NONE;
               end
            end
         end
         CMD1_SEND_OP_COND: begin
            if (card_state == CARD_IDLE || phy_mode_spi) begin
               resp_type <= RESP_R1;
               host_hc_support <= cmd_in_arg[30];
            end
         end
         CMD2_ALL_SEND_CID: begin
            if (card_state == CARD_READY || phy_mode_spi) begin
               resp_type <= RESP_R2;
               card_state_next <= CARD_IDENT;
            end
         end
         CMD3_SEND_REL_ADDR : case(card_state)
            CARD_IDENT, CARD_STBY: begin
            card_rca <= card_rca + 16'h1337;
            resp_type <= RESP_R6;
            card_state_next <= CARD_STBY;
            end
         endcase
         //CMD4_SET_DSR: begin
         //end
         CMD6_SWITCH_FUNC: begin
            case(card_state)
            CARD_TRAN: begin
            case(cmd_in_arg[23:20])
            4'h0, 4'hF: card_function_check[23:20] <= 4'h0; // valid
            default: card_function_check[23:20] <= 4'hF; // invalid
            endcase
            case(cmd_in_arg[19:16])
            4'h0, 4'hF: card_function_check[19:16] <= 4'h0; // valid
            default: card_function_check[19:16] <= 4'hF; // invalid
            endcase
            case(cmd_in_arg[15:12])
            4'h0, 4'hF: card_function_check[15:12] <= 4'h0; // valid
            default: card_function_check[15:12] <= 4'hF; // invalid
            endcase
            case(cmd_in_arg[11:8])
            4'h0, 4'hF: card_function_check[11:8] <= 4'h0; // valid
            default: card_function_check[11:8] <= 4'hF; // invalid
            endcase
            case(cmd_in_arg[7:4])
            4'h0, 4'hF: card_function_check[7:4] <= 4'h0; // valid
            default: card_function_check[7:4] <= 4'hF; // invalid
            endcase
            case(cmd_in_arg[3:0])
            4'h0: card_function_check[3:0] <= 4'h0;
            4'hF: card_function_check[3:0] <= card_function[3:0];
            4'h1: begin
               card_function_check[3:0] <= 4'h1;      // high speed enable
               if(cmd_in_arg[31]) card_function[3:0] <= 4'h1;
            end
            default: card_function_check[3:0] <= 4'hF; // invalid
            endcase
            resp_type <= RESP_R1;
            card_state_next <= CARD_DATA;
            data_op_send_function <= 1;
            end
         endcase
         end
         CMD7_SEL_CARD: begin
            if(cmd_in_arg[31:16] == card_rca) begin
               // select
               resp_type <= RESP_R1B;
               case(card_state)
               CARD_STBY: card_state_next <= CARD_TRAN;
               //CARD_DIS: card_state_next <= CARD_PRG;
               CARD_DIS: card_state_next <= CARD_TRAN;
               default: resp_type <= RESP_BAD;
               endcase
            end else begin
               // deselected
               case(card_state)
               CARD_STBY: card_state_next <= CARD_STBY;
               CARD_TRAN: card_state_next <= CARD_STBY;
               CARD_DATA: card_state_next <= CARD_STBY;
               CARD_PRG: card_state_next <= CARD_DIS;
               //default: resp_type <= RESP_BAD;
               endcase
               info_card_desel <= 1;
               resp_type <= RESP_NONE;
            end
         end
         CMD8_SEND_IF_COND: begin
            if ( ((card_state == CARD_IDLE) & (cmd_in_arg[11:8] == 4'b0001))
                 | phy_mode_spi ) begin
               resp_type <= RESP_R7;
               resp_arg <= {20'h0, 4'b0001, cmd_in_arg[7:0]};
            end else resp_type <= RESP_NONE;
         end
         CMD9_SEND_CSD: begin
            if(cmd_in_arg[31:16] == card_rca) begin
               case(card_state)
               CARD_STBY: begin
                  resp_type <= RESP_R2;
               end
               endcase
            end else resp_type <= RESP_NONE;
            if(phy_mode_spi) begin
               resp_type <= RESP_R1;
               data_op_send_csd <= 1;
            end
         end
         CMD10_SEND_CID: begin
            if(cmd_in_arg[31:16] == card_rca) begin
               case(card_state)
               CARD_STBY: begin
                  resp_type <= RESP_R2;
               end
               endcase
            end else resp_type <= RESP_NONE;
            if(phy_mode_spi) begin
               resp_type <= RESP_R1;
               data_op_send_cid <= 1;
            end
         end
         CMD12_STOP: case(card_state)
            // N.B. should not be allowed in PRG state, but readers do anyway
            CARD_DATA, CARD_RCV, CARD_PRG: begin
            resp_type <= RESP_R1B;
            if(card_state == CARD_DATA) card_state_next <= CARD_TRAN;
            // PRG > TRAN transition is handled by the data states below
            if(card_state == CARD_RCV) card_state_next <= CARD_TRAN;
            if(card_state == CARD_PRG) card_state_next <= CARD_TRAN;
            phy_data_in_stop <= 1;
            phy_data_out_stop <= 1;
            end
         endcase
         CMD13_SEND_STATUS: begin
            if(cmd_in_arg[31:16] == card_rca) begin
               case(card_state)
               CARD_STBY, CARD_TRAN, CARD_DATA, CARD_RCV, CARD_PRG, CARD_DIS: begin
                  resp_type <= RESP_R1;
               end
               endcase
            end else resp_type <= RESP_NONE;
            if(phy_mode_spi) begin
               resp_type <= RESP_R2;
            end
         end
         CMD15_GO_INACTIVE: begin
            if(cmd_in_arg[31:16] == card_rca) begin
               case(card_state)
               CARD_STBY, CARD_TRAN, CARD_DATA, CARD_RCV, CARD_PRG, CARD_DIS: begin
                  card_state_next <= CARD_INA;
                  resp_type <= RESP_NONE;
               end
               endcase
            end else resp_type <= RESP_NONE;
         end
         CMD16_SET_BLOCKLEN: begin
            if (card_state == CARD_TRAN || phy_mode_spi) begin
               resp_type <= RESP_R1;
               if(cmd_in_arg > 512) card_status[STAT_BLOCK_LEN_ERROR] <= 1;
            end
         end
         CMD17_READ_SINGLE: begin
            if (card_state == CARD_TRAN || phy_mode_spi) begin
               if(cmd_in_arg_blockaddr >= SD_TOTAL_BLOCKS) begin
                  card_status[STAT_OUT_OF_RANGE] <= 1'b1; err_op_out_range <= 1;
               end else begin
                  resp_type <= RESP_R1;
                  block_read_addr <= cmd_in_arg_blockaddr;
                  block_read_byteaddr <= cmd_in_arg_byteaddr;
                  block_read_num <= 1;
                  data_op_send_block_queue <= 1;
                  card_state_next <= CARD_DATA;
               end
            end
         end
         CMD18_READ_MULTIPLE: begin
            if (card_state == CARD_TRAN || phy_mode_spi) begin
               if(cmd_in_arg_blockaddr >= SD_TOTAL_BLOCKS) begin
                  card_status[STAT_OUT_OF_RANGE] <= 1'b1; err_op_out_range <= 1;
               end else begin
                  resp_type <= RESP_R1;
                  block_read_addr <= cmd_in_arg_blockaddr;
                  block_read_byteaddr <= cmd_in_arg_byteaddr;
                  block_read_num <= 32'hFFFFFFFF;
                  data_op_send_block_queue <= 1;
                  card_state_next <= CARD_DATA;
               end
            end
         end
         CMD24_WRITE_SINGLE: begin
            if (card_state == CARD_TRAN || phy_mode_spi) begin
               if(cmd_in_arg_blockaddr >= SD_TOTAL_BLOCKS) begin
                  card_status[STAT_OUT_OF_RANGE] <= 1'b1; err_op_out_range <= 1;
               end else begin
                  resp_type <= RESP_R1;
                  block_write_addr <= cmd_in_arg_blockaddr;
                  block_write_byteaddr <= cmd_in_arg_byteaddr;
                  block_write_num <= 1;
                  card_blocks_written <= 0;
                  data_op_recv_block <= 1;
                  card_state_next <= CARD_RCV;
               end
            end
         end
         CMD25_WRITE_MULTIPLE: begin
            if (card_state == CARD_TRAN || phy_mode_spi) begin
               if(cmd_in_arg_blockaddr >= SD_TOTAL_BLOCKS) begin
                  card_status[STAT_OUT_OF_RANGE] <= 1'b1; err_op_out_range <= 1;
               end else begin
                  resp_type <= RESP_R1;
                  block_write_addr <= cmd_in_arg_blockaddr;
                  block_write_byteaddr <= cmd_in_arg_byteaddr;
                  block_write_num <= 32'hFFFFFFFF;
                  card_blocks_written <= 0;
                  data_op_recv_block <= 1;
                  card_state_next <= CARD_RCV;
               end
            end
         end
         //CMD27_PROGRAM_CSD: begin
         //end
         CMD32_ERASE_START: begin
            if (card_state == CARD_TRAN || phy_mode_spi) begin
               resp_type <= RESP_R1;
               card_erase_state <= 0;
               if(card_erase_state == 0) begin
                  block_erase_start <= cmd_in_arg_blockaddr;
                  card_erase_state <= 1;
               end else card_status[STAT_ERASE_SEQ_ERROR] <= 1'b1;
            end
         end
         CMD33_ERASE_END: begin
            if (card_state == CARD_TRAN || phy_mode_spi) begin
               resp_type <= RESP_R1;
               card_erase_state <= 0;
               if(card_erase_state == 1) begin
                  block_erase_end <= cmd_in_arg_blockaddr;
                  card_erase_state <= 2;
               end else card_status[STAT_ERASE_SEQ_ERROR] <= 1'b1;
            end
         end
         CMD38_ERASE: begin
            if (card_state == CARD_TRAN || phy_mode_spi) begin
               resp_type <= RESP_R1B;
               card_erase_state <= 0;
               if(card_erase_state == 2) begin
                  // process erase

               end else card_status[STAT_ERASE_SEQ_ERROR] <= 1'b1;
               // since erase are unimpl they happen immediately
               //card_state_next <= CARD_PRG;
            end
         end
         //CMD42_LOCK_UNLOCK: begin
         //end
         CMD55_APP_CMD: begin
            if(cmd_in_arg[31:16] == card_rca) begin
               case(card_state)
               CARD_IDLE, CARD_STBY, CARD_TRAN, CARD_DATA, CARD_RCV, CARD_PRG, CARD_DIS: begin
                  resp_type <= RESP_R1;
                  card_appcmd <= 1;
                  card_status[STAT_APP_CMD] <= 1;
               end
               endcase
            end else resp_type <= RESP_NONE;
            if(phy_mode_spi) begin
               resp_type <= RESP_R1;
               card_appcmd <= 1;
               card_status[STAT_APP_CMD] <= 1;
            end
         end
         //CMD56_GEN_CMD: begin
         //end
         CMD58_READ_OCR: begin
            resp_type <= RESP_R3;
         end
         CMD59_CRC_ON_OFF: begin
            phy_mode_crc_disable <= ~cmd_in_arg[0];
            resp_type <= RESP_R1;
         end
         default: begin
            err_unhandled_cmd <= 1;
            if(cmd_in_cmd == 6'd1) err_unhandled_cmd <= 0; // CMD1 for SPI cards
            if(cmd_in_cmd == 6'd5) err_unhandled_cmd <= 0; // CMD5 for SDIO combo cards
         end
         endcase
         // check for illegal commands during an expected erase sequence
         if(card_erase_state > 0) begin
            if(   cmd_in_cmd != CMD13_SEND_STATUS &&
               cmd_in_cmd != CMD33_ERASE_END &&
               cmd_in_cmd != CMD38_ERASE) begin
               card_erase_state <= 0;
               card_status[STAT_ERASE_RESET] <= 1;
            end
         end
      end else begin
         // ACMD
         case(cmd_in_cmd)
         ACMD6_SET_BUS_WIDTH: begin
            if (card_state == CARD_TRAN || phy_mode_spi) begin
               resp_type <= RESP_R1;
               phy_mode_4bit <= cmd_in_arg[1];
            end
         end
         ACMD13_SD_STATUS: begin
            if (card_state == CARD_TRAN || phy_mode_spi) begin
               resp_type <= RESP_R1;
               // send SD status
               data_op_send_sdstatus <= 1;
               card_state_next <= CARD_DATA;
            end
         end
         ACMD22_NUM_WR_BLK: begin
            if (card_state == CARD_TRAN || phy_mode_spi) begin
               resp_type <= RESP_R1;
               // send number blocks written
               data_op_send_written <= 1;
               card_state_next <= CARD_DATA;
            end
         end
         ACMD23_SET_WR_BLK: begin
            if (card_state == CARD_TRAN || phy_mode_spi) begin
               resp_type <= RESP_R1;
               block_preerase_num[22:0] <= cmd_in_arg[22:0];
            end
         end
         ACMD41_SEND_OP_COND: begin
            if (card_state == CARD_IDLE || phy_mode_spi) begin
               resp_type <= RESP_R3;
               card_ocr[OCR_POWERED_UP] <= 1;
               card_state_next <= CARD_READY;
               host_hc_support <= cmd_in_arg[30];
            end
         end
         ACMD42_SET_CARD_DET: begin
            if (card_state == CARD_TRAN || phy_mode_spi) begin
               resp_type <= RESP_R1;
            end
         end
         ACMD51_SEND_SCR: begin
            if (card_state == CARD_TRAN || phy_mode_spi) begin
               resp_type <= RESP_R1;
               // send SCR
               data_op_send_scr <= 1;
               card_state_next <= CARD_DATA;
            end
         end
         default: begin
            // retry this as a regular CMD (retry this state with APPCMD=0)
            state <= ST_CMD_ACT;
            card_appcmd <= 0;
            //err_unhandled_cmd <= 1;

         end
         endcase
      end
   end
   ST_CMD_RESP_0: begin
      // update status register and such
      card_status[12:9] <= card_state;

      state <= ST_CMD_RESP_1;
   end
   ST_CMD_RESP_1: begin
      // send response
      state <= ST_CMD_RESP_2;
      phy_resp_type <= resp_type;
      phy_resp_busy <= 0;
      case(resp_type)
      RESP_NONE: begin
         // don't send a response
         card_state <= card_state_next;
         state <= ST_IDLE;
      end
      RESP_BAD: begin
         card_status[STAT_ILLEGAL_COMMAND] <= 1;
         if (phy_mode_spi) begin
            // SPI mode; R1 response with 'illegal command' bit already set
            phy_resp_out <= {spi_status_word[15:11], 1'b1, spi_status_word[9:8], 128'h0};
         end
         else begin
            // SD mode
            state <= ST_IDLE;
         end
      end
      RESP_R1, RESP_R1B: begin
         phy_resp_out <= phy_mode_spi ?
            {spi_status_word[15:8], 128'h0} :
            {2'b00, cmd_in_cmd, card_status, 8'h1, 88'h0};
      end
      RESP_R2: begin
         phy_resp_out <= phy_mode_spi ?
            {spi_status_word[15:0], 120'h0} :
            {2'b00, 6'b111111, cmd_in_cmd == CMD9_SEND_CSD ? card_csd[127:1] : card_cid[127:1], 1'b1};
      end
      RESP_R3: begin
         phy_resp_out <= phy_mode_spi ?
            {spi_status_word[15:8], card_ocr, 96'h0 } :
            {2'b00, 6'b111111, card_ocr, 8'hFF, 88'h0};
      end
      RESP_R6: begin
         phy_resp_out <= {2'b00, 6'b000011, card_rca, {card_status[23:22], card_status[19], card_status[12:0]}, 8'h1, 88'h0};
      end
      RESP_R7: begin
         phy_resp_out <= phy_mode_spi ?
            {spi_status_word[15:8], resp_arg[31:0], 96'h0} :
            {2'b00, 6'b001000, resp_arg[31:0], 8'h1, 88'h0};
      end
      endcase
   end
   ST_CMD_RESP_2: begin
      phy_resp_act <= 1;

      if(resp_done_r) begin
         // rising edge, phy is done sending response
         phy_resp_act <= 0;

         // clear APP_CMD after ACMD response sent
         if(card_appcmd && (cmd_in_cmd != CMD55_APP_CMD)) begin
            card_appcmd <= 0;
            card_status[STAT_APP_CMD] <= 0; // not spec? but cards do it
         end
         case(cmd_in_cmd)
         CMD13_SEND_STATUS: begin
            // clear all bits that are Clear-On-Read
            card_status[STAT_OUT_OF_RANGE] <= 0;
            card_status[STAT_ADDRESS_ERROR] <= 0;
            card_status[STAT_BLOCK_LEN_ERROR] <= 0;
            card_status[STAT_ERASE_SEQ_ERROR] <= 0;
            card_status[STAT_ERASE_PARAM] <= 0;
            card_status[STAT_WP_VIOLATION] <= 0;
            card_status[STAT_LOCK_UNLOCK_FAILED] <= 0;
            card_status[STAT_CARD_ECC_FAILED] <= 0;
            card_status[STAT_CC_ERROR] <= 0;
            card_status[STAT_CSD_OVERWRITE] <= 0;
            card_status[STAT_WP_ERASE_SKIP] <= 0;
            card_status[STAT_ERASE_RESET] <= 0;
            card_status[STAT_APP_CMD] <= 0;
            card_status[STAT_AKE_SEQ_ERROR] <= 0;
         end
         endcase
         card_state <= card_state_next;
         state <= ST_IDLE;

         // Clear bits for SPI status responses
         if (phy_mode_spi) begin
            // R1
            card_status[STAT_BLOCK_LEN_ERROR] <= 0;
            card_status[STAT_ADDRESS_ERROR] <= 0;
            card_status[STAT_ERASE_SEQ_ERROR] <= 0;
            card_status[STAT_COM_CRC_ERROR] <= 0;
            card_status[STAT_ILLEGAL_COMMAND] <= 0;
            card_status[STAT_ERASE_RESET] <= 0;
            // R2
            if (phy_resp_type == RESP_R2) begin
               card_status[STAT_OUT_OF_RANGE] <= 0;
               card_status[STAT_CSD_OVERWRITE] <= 0;
               card_status[STAT_ERASE_PARAM] <= 0;
               card_status[STAT_WP_VIOLATION] <= 0;
               card_status[STAT_CARD_ECC_FAILED] <= 0;
               card_status[STAT_CC_ERROR] <= 0;
               card_status[STAT_ERROR] <= 0;
               card_status[STAT_WP_ERASE_SKIP] <= 0;
               card_status[STAT_LOCK_UNLOCK_FAILED] <= 0;
               card_status[STAT_CARD_IS_LOCKED] <= 0;
            end
         end
      end
   end
   endcase


   // data FSM
   // must be separate so that data packets can be transferred
   // and commands still sent/responsed
   //
   // free running counter
   ddc <= ddc + 1'b1;

   case(data_state)
   DST_RESET: begin
      phy_data_out_act <= 0;
      data_state <= DST_IDLE;
   end
   DST_IDLE: begin
      card_status[STAT_READY_FOR_DATA] <= 1'b1;

      if(data_op_recv_block) begin
         // for data receive ops
         data_state <= DST_DATA_IN_0;
      end else
      if(   data_op_send_scr | data_op_send_sdstatus | data_op_send_cid | data_op_send_csd |
         data_op_send_function | data_op_send_written | data_op_send_block_queue ) begin

         // move to next state once response is processing
         // to prevent false starts
         if(~resp_done_s) begin
            data_state <= DST_IDLE_1;
            // queue block read, so that it can be accepted after a much-delayed read cycle
            if(data_op_send_block_queue) begin
               //card_state <= CARD_DATA;
               data_op_send_block_queue <= 0;
               data_op_send_block <= 1;
            end
         end
      end
   end
   DST_IDLE_1: begin
      ddc <= 0;

      // process these data ops while response starts to send
      if(   data_op_send_scr | data_op_send_sdstatus | data_op_send_cid | data_op_send_csd |
         data_op_send_function | data_op_send_written | data_op_send_block ) begin

         phy_data_out_src <= 1; // default: send from register
         data_state <= DST_DATA_OUT_0;

         if(data_op_send_scr) begin
            data_op_send_scr <= 0;
            phy_data_out_len <= 8;
            phy_data_out_reg <= {card_scr, 448'h0};
         end else
         if(data_op_send_sdstatus) begin
            data_op_send_sdstatus <= 0;
            phy_data_out_len <= 64;
            phy_data_out_reg <= {card_sd_status, 384'h0};
         end else
         if(data_op_send_function) begin
            data_op_send_function <= 0;
            phy_data_out_len <= 64;
            phy_data_out_reg <= {card_function_caps, card_function_check, 376'h0};
         end else
         if(data_op_send_written) begin
            data_op_send_written <= 0;
            phy_data_out_len <= 4;
            phy_data_out_reg <= {card_blocks_written, 480'h0};
         end else
         if(data_op_send_block) begin
            phy_data_out_src <= 0; // send data from bram
            phy_data_out_len <= 512;
            data_state <= DST_DATA_OUT_5;
         end
         if(data_op_send_cid) begin
            data_op_send_cid <= 0;
            phy_data_out_len <= 16;
            phy_data_out_reg <= {card_cid, 384'h0};
         end
         if(data_op_send_csd) begin
            data_op_send_csd <= 0;
            phy_data_out_len <= 16;
            phy_data_out_reg <= {card_csd, 384'h0};
         end
      end
   end
   DST_DATA_OUT_5: begin
      // make sure MGR cleared from any previous ops
      if(~block_read_go) begin
         block_read_stop <= 0;
         data_state <= DST_DATA_OUT_3;
      end
   end
   DST_DATA_OUT_3: begin
      // external bram op:
      // wait for bram contents to be valid
      block_read_act <= 1;
      if(block_read_go) begin
         // ready
         block_read_act <= 0;
         data_state <= DST_DATA_OUT_0;
      end
   end
   DST_DATA_OUT_0: begin
      // wait to send data until response was sent
      if(resp_done_s) begin
         phy_data_out_act <= 1;
         data_state <= DST_DATA_OUT_1;
      end
   end
   DST_DATA_OUT_1: begin
      if(data_out_done_r) begin
         // rising edge, phy is done sending data
         phy_data_out_act <= 0;

         // did link detect a stop command?
         if(phy_data_out_stop) begin
            phy_data_in_stop <= 0;
            phy_data_out_stop <= 0;
            data_op_send_block <= 0;
         end

         // tell upper level we're done
         block_read_stop <= 1;
         data_state <= DST_DATA_OUT_4;
      end
   end
   DST_DATA_OUT_4: begin
      // wait for SD_MGR to finish
      if(~block_read_go) data_state <= DST_DATA_OUT_2;

      // link detected stop while we're waiting
      if(phy_data_out_stop) begin
         phy_data_in_stop <= 0;
         phy_data_out_stop <= 0;
         data_op_send_block <= 0;
         block_read_stop <= 1;
         data_state <= DST_DATA_OUT_2;
      end
   end
   DST_DATA_OUT_2: begin
      // wait until phy de-asserts busy so that it can detect another rising edge
      // due to clocking differences
      if(~data_out_busy_s) begin
         //block_read_stop <= 0;
         // fall back to TRAN state
         card_state <= CARD_TRAN;
         data_state <= DST_IDLE;
         // don't wait around for a response to be sent if more blocks are to be done
         if(data_op_send_block) begin
            if(block_read_num == 1) begin
               data_op_send_block <= 0;
            end else begin
               // stay in current state
               // advance block count
               card_state <= card_state;
               block_read_addr <= block_read_addr + 1'b1;
               block_read_num <= block_read_num - 1'b1;
               block_read_byteaddr <= block_read_byteaddr + 512;
               if(block_read_addr >= SD_TOTAL_BLOCKS) begin
                  card_status[STAT_OUT_OF_RANGE] <= 1'b1;
                  err_op_out_range <= 1;
               end
               data_state <= DST_IDLE_1;
            end
         end
      end
   end

   DST_DATA_IN_0: begin
      // signal to PHY that we are expecting a data packet
      phy_data_in_act <= 1;
      if(data_in_done_r) begin
         card_status[STAT_READY_FOR_DATA] <= 1'b0;
         data_state <= DST_DATA_IN_1;
      end
      if(phy_data_in_stop) begin
         phy_data_in_act <= 0;
         card_state <= CARD_TRAN;
         data_state <= DST_DATA_IN_2;
      end
   end
   DST_DATA_IN_1: begin
      if(~data_in_crc_good_s) begin
         // bad CRC, don't commit
         // expect host to re-send entire CMD24/25 sequence
         phy_data_in_act <= 0;
         data_op_recv_block <= 0;
         card_state <= CARD_TRAN;
         data_state <= DST_IDLE;
      end else begin
         // tell mgr/ext there is data to be written
         block_write_act <= 1;
         card_state <= CARD_PRG;
         // mgr/ext has finished
         if(block_write_done) begin
            // tell PHY to let go of the busy signal on DAT0
            card_state <= CARD_RCV;
            phy_data_in_act <= 0;
            block_write_act <= 0;
            data_state <= DST_DATA_IN_2;
         end
      end
   end
   DST_DATA_IN_2: begin
      // wait until PHY is able to detect new ACT
      // or if it's a burst write, just go ahead anyway
      if(~data_in_busy_s | (phy_data_in_another & ~phy_data_in_stop)) begin
         data_state <= DST_DATA_IN_3;
      end
      phy_data_in_another <= block_write_num > 1;
      //phy_data_in_stop <= 1;
   end
   DST_DATA_IN_3: begin
      card_blocks_written <= card_blocks_written + 1'b1;
      if(block_write_num == 1 || phy_data_in_stop) begin
         // last block, or it was CMD12'd
         card_state <= CARD_TRAN;
         phy_data_in_stop <= 0;
         phy_data_out_stop <= 0;
         phy_data_in_another <= 0;
         data_op_recv_block <= 0;
         data_state <= DST_IDLE;
      end else begin
         // more blocks to go
         card_state <= CARD_RCV;
         card_status[STAT_READY_FOR_DATA] <= 1'b1;
         block_write_addr <= block_write_addr + 1'b1;
         block_write_num <= block_write_num - 1'b1;
         block_write_byteaddr <= block_write_byteaddr + 512;
         if(block_write_addr >= SD_TOTAL_BLOCKS) begin
            card_status[STAT_OUT_OF_RANGE] <= 1'b1;
            err_op_out_range <= 1;
         end
         data_state <= DST_DATA_IN_0;
      end
   end
   endcase

   if(~reset_s) begin
      state <= ST_RESET;
      data_state <= DST_RESET;
      phy_mode_spi <= 0;
      phy_mode_crc_disable <= 0;
   end
end


endmodule
