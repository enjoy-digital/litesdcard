`timescale 1ns/10ps
module tb_spi_mode;

reg sys_clk = 1'b0;
reg sys_rst = 1'b0;
reg sdemu_sd_clk = 1'b0;

reg flipsyfat_sdemu_cmd_t_i = 1'b1;
reg [3:0] flipsyfat_sdemu_sd_dat_i = 4'b1111;

initial forever #2 sys_clk = ~sys_clk;

reg [31:0] n;

initial begin

    $dumpfile("tb_spi_mode.vcd");
    $dumpvars;
    #10    sys_rst = 1'b1;
    #100   sys_rst = 1'b0;

    #1000
    for (n=0; n<10; n++)
       spi_byte(8'hFF);

    #1000
    spi_cs(1'b0);
    spi_byte(8'hff);
    spi_byte(8'hff);

    spi_byte(8'h40);
    spi_byte(8'h00);
    spi_byte(8'h00);
    spi_byte(8'h00);
    spi_byte(8'h00);
    spi_byte(8'h95);
    for (n=0; n<4; n++)
       spi_byte(8'hFF);

    spi_byte(8'h48);
    spi_byte(8'h00);
    spi_byte(8'h00);
    spi_byte(8'h02);
    spi_byte(8'haa);
    spi_byte(8'h87);
    for (n=0; n<8; n++)
       spi_byte(8'hFF);

    spi_byte(8'h77);
    spi_byte(8'h00);
    spi_byte(8'h00);
    spi_byte(8'h00);
    spi_byte(8'h00);
    for (n=0; n<5; n++)
       spi_byte(8'hFF);

    spi_byte(8'h69);
    spi_byte(8'h40);
    spi_byte(8'h00);
    spi_byte(8'h00);
    spi_byte(8'h00);
    for (n=0; n<5; n++)
       spi_byte(8'hFF);

    spi_byte(8'h7a);
    spi_byte(8'h40);
    spi_byte(8'h00);
    spi_byte(8'h00);
    spi_byte(8'h00);
    for (n=0; n<7; n++)
       spi_byte(8'hFF);

    spi_cs(1'b1);
    spi_byte(8'hFF);
    #1000;
    for (n=0; n<10; n++)
       spi_byte(8'hFF);
    spi_cs(1'b0);
    for (n=0; n<2; n++)
       spi_byte(8'hFF);

    spi_byte(8'h40);
    spi_byte(8'h00);
    spi_byte(8'h00);
    spi_byte(8'h00);
    spi_byte(8'h00);
    spi_byte(8'h95);
    for (n=0; n<4; n++)
       spi_byte(8'hFF);

    spi_byte(8'h48);
    spi_byte(8'h00);
    spi_byte(8'h00);
    spi_byte(8'h02);
    spi_byte(8'haa);
    spi_byte(8'h87);
    for (n=0; n<8; n++)
       spi_byte(8'hFF);

    spi_byte(8'h77);
    spi_byte(8'h00);
    spi_byte(8'h00);
    spi_byte(8'h00);
    spi_byte(8'h00);
    for (n=0; n<5; n++)
       spi_byte(8'hFF);

    spi_byte(8'h69);
    spi_byte(8'h40);
    spi_byte(8'h00);
    spi_byte(8'h00);
    spi_byte(8'h00);
    for (n=0; n<5; n++)
       spi_byte(8'hFF);

    spi_byte(8'h77);
    spi_byte(8'h00);
    spi_byte(8'h00);
    spi_byte(8'h00);
    spi_byte(8'h00);
    for (n=0; n<5; n++)
       spi_byte(8'hFF);

    spi_byte(8'h69);
    spi_byte(8'h40);
    spi_byte(8'h00);
    spi_byte(8'h00);
    spi_byte(8'h00);
    for (n=0; n<5; n++)
       spi_byte(8'hFF);

    spi_byte(8'h50);
    spi_byte(8'h00);
    spi_byte(8'h00);
    spi_byte(8'h02);
    spi_byte(8'h00);
    for (n=0; n<3; n++)
       spi_byte(8'hFF);

    spi_cs(1'b1);
    spi_byte(8'hFF);
    #1000;
    spi_cs(1'b0);
    for (n=0; n<2; n++)
       spi_byte(8'hFF);

    spi_byte(8'h51);
    spi_byte(8'h00);
    spi_byte(8'h00);
    spi_byte(8'h00);
    spi_byte(8'h00);

    for (n=0; n<20; n++)
       spi_byte(8'hFF);

    #1000  $finish;
end


task spi_cs;
    input state;
    begin
        flipsyfat_sdemu_sd_dat_i[3] = state;
    end
endtask

task spi_byte;
    input [7:0] mosibyte;
    reg [7:0] misobyte;
    reg [7:0] misobyte_next;
    reg [7:0] i;
    begin
        misobyte_next = 0;
        for (i = 0; i < 8; i++) begin
            flipsyfat_sdemu_cmd_t_i = mosibyte[7-i];
            #12 sdemu_sd_clk = 1;
            #12 sdemu_sd_clk = 0;
            misobyte_next[7-i] = flipsyfat_sdemu_sd_dat_o[0];
        end
        #100
        misobyte = misobyte_next;
        $display("SPI %x -> %x", mosibyte, misobyte);
    end
endtask


wire flipsyfat_sdemu_cmd_t_o;
wire flipsyfat_sdemu_cmd_t_oe;
wire flipsyfat_sdemu_sd_cmd_t;
wire [3:0] flipsyfat_sdemu_sd_dat_o;
wire [3:0] flipsyfat_sdemu_sd_dat_t;

wire [6:0] flipsyfat_sdemu_internal_rd_port_adr;
wire [31:0] flipsyfat_sdemu_internal_rd_port_dat_r;
wire [6:0] flipsyfat_sdemu_internal_wr_port_adr;
wire [31:0] flipsyfat_sdemu_internal_wr_port_dat_r;
wire flipsyfat_sdemu_internal_wr_port_we;
wire [31:0] flipsyfat_sdemu_internal_wr_port_dat_w;
wire [3:0] flipsyfat_sdemu_card_state;
wire flipsyfat_sdemu_mode_4bit;
wire flipsyfat_sdemu_mode_spi;
wire flipsyfat_sdemu_mode_crc_disable;
wire flipsyfat_sdemu_spi_sel;
wire [47:0] flipsyfat_sdemu_cmd_in;
wire [5:0] flipsyfat_sdemu_cmd_in_last;
wire flipsyfat_sdemu_cmd_in_crc_good;
wire flipsyfat_sdemu_cmd_in_act;
wire flipsyfat_sdemu_data_in_act;
wire flipsyfat_sdemu_data_in_busy;
wire flipsyfat_sdemu_data_in_another;
wire flipsyfat_sdemu_data_in_stop;
wire flipsyfat_sdemu_data_in_done;
wire flipsyfat_sdemu_data_in_crc_good;
wire [135:0] flipsyfat_sdemu_resp_out;
wire [3:0] flipsyfat_sdemu_resp_type;
wire flipsyfat_sdemu_resp_busy;
wire flipsyfat_sdemu_resp_act;
wire flipsyfat_sdemu_resp_done;
wire [511:0] flipsyfat_sdemu_data_out_reg;
wire flipsyfat_sdemu_data_out_src;
wire [9:0] flipsyfat_sdemu_data_out_len;
wire flipsyfat_sdemu_data_out_busy;
wire flipsyfat_sdemu_data_out_act;
wire flipsyfat_sdemu_data_out_stop;
wire flipsyfat_sdemu_data_out_done;
wire [5:0] flipsyfat_sdemu_cmd_in_cmd;
wire flipsyfat_sdemu_info_card_desel;
reg flipsyfat_sdemu_err_op_out_range = 1'd0;
wire flipsyfat_sdemu_err_unhandled_cmd;
wire flipsyfat_sdemu_err_cmd_crc;
wire [10:0] flipsyfat_sdemu_phy_idc;
wire [10:0] flipsyfat_sdemu_phy_odc;
wire [6:0] flipsyfat_sdemu_phy_istate;
wire [6:0] flipsyfat_sdemu_phy_ostate;
wire [7:0] flipsyfat_sdemu_phy_spi_cnt;
wire [6:0] flipsyfat_sdemu_link_state;
wire [15:0] flipsyfat_sdemu_link_ddc;
wire [15:0] flipsyfat_sdemu_link_dc;
wire flipsyfat_sdemu_block_read_act;
wire [31:0] flipsyfat_sdemu_block_read_addr;
wire [31:0] flipsyfat_sdemu_block_read_num;
wire flipsyfat_sdemu_block_read_stop;
wire flipsyfat_sdemu_block_write_act;
wire [31:0] flipsyfat_sdemu_block_write_addr;
wire [31:0] flipsyfat_sdemu_block_write_num;
wire [22:0] flipsyfat_sdemu_block_preerase_num;
wire [31:0] flipsyfat_sdemu_block_erase_start;
wire [31:0] flipsyfat_sdemu_block_erase_end;

reg flipsyfat_sdemu_block_read_go = 1'b0;
reg flipsyfat_sdemu_block_write_done = 1'b0;

reg [31:0] rd_buffer[0:127];
reg [6:0] memadr_5;
always @(posedge sdemu_sd_clk) begin
    memadr_5 <= flipsyfat_sdemu_internal_rd_port_adr;
end
assign flipsyfat_sdemu_internal_rd_port_dat_r = rd_buffer[memadr_5];

reg [31:0] wr_buffer[0:127];
reg [6:0] memadr_7;
always @(posedge sdemu_sd_clk) begin
    if (flipsyfat_sdemu_internal_wr_port_we)
        wr_buffer[flipsyfat_sdemu_internal_wr_port_adr] <= flipsyfat_sdemu_internal_wr_port_dat_w;
    memadr_7 <= flipsyfat_sdemu_internal_wr_port_adr;
end
assign flipsyfat_sdemu_internal_wr_port_dat_r = wr_buffer[memadr_7];

sd_phy sd_phy(
    .bram_rd_sd_q(flipsyfat_sdemu_internal_rd_port_dat_r),
    .bram_wr_sd_q(flipsyfat_sdemu_internal_wr_port_dat_r),
    .card_state(flipsyfat_sdemu_card_state),
    .clk_50(sys_clk),
    .data_in_act(flipsyfat_sdemu_data_in_act),
    .data_in_another(flipsyfat_sdemu_data_in_another),
    .data_in_stop(flipsyfat_sdemu_data_in_stop),
    .data_out_act(flipsyfat_sdemu_data_out_act),
    .data_out_len(flipsyfat_sdemu_data_out_len),
    .data_out_reg(flipsyfat_sdemu_data_out_reg),
    .data_out_src(flipsyfat_sdemu_data_out_src),
    .data_out_stop(flipsyfat_sdemu_data_out_stop),
    .mode_4bit(flipsyfat_sdemu_mode_4bit),
    .mode_crc_disable(flipsyfat_sdemu_mode_crc_disable),
    .mode_spi(flipsyfat_sdemu_mode_spi),
    .reset_n((~sys_rst)),
    .resp_act(flipsyfat_sdemu_resp_act),
    .resp_busy(flipsyfat_sdemu_resp_busy),
    .resp_out(flipsyfat_sdemu_resp_out),
    .resp_type(flipsyfat_sdemu_resp_type),
    .sd_clk(sdemu_sd_clk),
    .sd_cmd_i(flipsyfat_sdemu_cmd_t_i),
    .sd_dat_i(flipsyfat_sdemu_sd_dat_i),
    .bram_rd_sd_addr(flipsyfat_sdemu_internal_rd_port_adr),
    .bram_wr_sd_addr(flipsyfat_sdemu_internal_wr_port_adr),
    .bram_wr_sd_data(flipsyfat_sdemu_internal_wr_port_dat_w),
    .bram_wr_sd_wren(flipsyfat_sdemu_internal_wr_port_we),
    .cmd_in(flipsyfat_sdemu_cmd_in),
    .cmd_in_act(flipsyfat_sdemu_cmd_in_act),
    .cmd_in_crc_good(flipsyfat_sdemu_cmd_in_crc_good),
    .data_in_busy(flipsyfat_sdemu_data_in_busy),
    .data_in_crc_good(flipsyfat_sdemu_data_in_crc_good),
    .data_in_done(flipsyfat_sdemu_data_in_done),
    .data_out_busy(flipsyfat_sdemu_data_out_busy),
    .data_out_done(flipsyfat_sdemu_data_out_done),
    .idc(flipsyfat_sdemu_phy_idc),
    .istate(flipsyfat_sdemu_phy_istate),
    .odc(flipsyfat_sdemu_phy_odc),
    .ostate(flipsyfat_sdemu_phy_ostate),
    .resp_done(flipsyfat_sdemu_resp_done),
    .sd_cmd_o(flipsyfat_sdemu_cmd_t_o),
    .sd_cmd_t(flipsyfat_sdemu_sd_cmd_t),
    .sd_dat_o(flipsyfat_sdemu_sd_dat_o),
    .sd_dat_t(flipsyfat_sdemu_sd_dat_t),
    .spi_cnt(flipsyfat_sdemu_phy_spi_cnt),
    .spi_sel(flipsyfat_sdemu_spi_sel)
);

sd_link sd_link(
    .block_read_go(flipsyfat_sdemu_block_read_go),
    .block_write_done(flipsyfat_sdemu_block_write_done),
    .clk_50(sys_clk),
    .opt_enable_hs(1'd1),
    .phy_cmd_in(flipsyfat_sdemu_cmd_in),
    .phy_cmd_in_act(flipsyfat_sdemu_cmd_in_act),
    .phy_cmd_in_crc_good(flipsyfat_sdemu_cmd_in_crc_good),
    .phy_data_in_busy(flipsyfat_sdemu_data_in_busy),
    .phy_data_in_crc_good(flipsyfat_sdemu_data_in_crc_good),
    .phy_data_in_done(flipsyfat_sdemu_data_in_done),
    .phy_data_out_busy(flipsyfat_sdemu_data_out_busy),
    .phy_data_out_done(flipsyfat_sdemu_data_out_done),
    .phy_resp_done(flipsyfat_sdemu_resp_done),
    .phy_spi_sel(flipsyfat_sdemu_spi_sel),
    .reset_n((~sys_rst)),
    .block_erase_end(flipsyfat_sdemu_block_erase_end),
    .block_erase_start(flipsyfat_sdemu_block_erase_start),
    .block_preerase_num(flipsyfat_sdemu_block_preerase_num),
    .block_read_act(flipsyfat_sdemu_block_read_act),
    .block_read_addr(flipsyfat_sdemu_block_read_addr),
    .block_read_num(flipsyfat_sdemu_block_read_num),
    .block_read_stop(flipsyfat_sdemu_block_read_stop),
    .block_write_act(flipsyfat_sdemu_block_write_act),
    .block_write_addr(flipsyfat_sdemu_block_write_addr),
    .block_write_num(flipsyfat_sdemu_block_write_num),
    .cmd_in_cmd(flipsyfat_sdemu_cmd_in_cmd),
    .cmd_in_last(flipsyfat_sdemu_cmd_in_last),
    .dc(flipsyfat_sdemu_link_dc),
    .ddc(flipsyfat_sdemu_link_ddc),
    .err_cmd_crc(flipsyfat_sdemu_err_cmd_crc),
    .err_unhandled_cmd(flipsyfat_sdemu_err_unhandled_cmd),
    .info_card_desel(flipsyfat_sdemu_info_card_desel),
    .link_card_state(flipsyfat_sdemu_card_state),
    .phy_data_in_act(flipsyfat_sdemu_data_in_act),
    .phy_data_in_another(flipsyfat_sdemu_data_in_another),
    .phy_data_in_stop(flipsyfat_sdemu_data_in_stop),
    .phy_data_out_act(flipsyfat_sdemu_data_out_act),
    .phy_data_out_len(flipsyfat_sdemu_data_out_len),
    .phy_data_out_reg(flipsyfat_sdemu_data_out_reg),
    .phy_data_out_src(flipsyfat_sdemu_data_out_src),
    .phy_data_out_stop(flipsyfat_sdemu_data_out_stop),
    .phy_mode_4bit(flipsyfat_sdemu_mode_4bit),
    .phy_mode_crc_disable(flipsyfat_sdemu_mode_crc_disable),
    .phy_mode_spi(flipsyfat_sdemu_mode_spi),
    .phy_resp_act(flipsyfat_sdemu_resp_act),
    .phy_resp_busy(flipsyfat_sdemu_resp_busy),
    .phy_resp_out(flipsyfat_sdemu_resp_out),
    .phy_resp_type(flipsyfat_sdemu_resp_type),
    .state(flipsyfat_sdemu_link_state)
);

// Trivial sd-mgr layer
initial for (n = 0; n < 128; n++) rd_buffer[n] = 32'hABCD4567;

always @(posedge flipsyfat_sdemu_block_read_act) begin
    $display("Block Read");
    #2000
    flipsyfat_sdemu_block_read_go = 1;
    #40
    flipsyfat_sdemu_block_read_go = 0;
end

always @(posedge flipsyfat_sdemu_block_write_act) begin
    $display("Block Write");
    #2000
    flipsyfat_sdemu_block_write_done = 1;
    #40
    flipsyfat_sdemu_block_write_done = 0;
end

endmodule
