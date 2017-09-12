# Makefile just for test benches; needs iverilog

tb_spi_mode: tb_spi_mode.v *.v *.vh
	iverilog -o $@ -l sd_link.v -l sd_phy.v -l sd_common.v $<
