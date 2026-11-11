# Copyright (c) 2017 Micah Elizabeth Scott
# Copyright (c) 2020 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import os

from migen import *

# Helpers ------------------------------------------------------------------------------------------

_BLOCK_SIZE  = 512
_C_SIZE_UNIT = 512*1024 # SDHC/SDXC (CSD 2.0) capacity unit: (C_SIZE + 1) * 512KB.

def _sdemulator_store(size, image):
    """Return (nblocks, init, csd_c_size) of the emulator block store."""
    # Default: Single 512-byte block buffer shared by all block addresses.
    if size is None and image is None:
        return 1, [i for i in range(_BLOCK_SIZE//4)], None

    # Block-addressed store, optionally initialized from a raw disk image.
    data = b""
    if image is not None:
        with open(image, "rb") as f:
            data = f.read()
    if size is None:
        size = max(_C_SIZE_UNIT, (len(data) + _C_SIZE_UNIT - 1)//_C_SIZE_UNIT*_C_SIZE_UNIT)
    if (size <= 0) or (size % _C_SIZE_UNIT):
        raise ValueError(f"SDEmulator size must be a multiple of {_C_SIZE_UNIT} bytes ({size}).")
    if len(data) > size:
        raise ValueError(f"SDEmulator image ({len(data)} bytes) larger than size ({size} bytes).")
    data = data + bytes(size - len(data))
    init = [int.from_bytes(data[i:i+4], "big") for i in range(0, size, 4)] # Card sends MSB first.
    return size//_BLOCK_SIZE, init, size//_C_SIZE_UNIT - 1

# SDEmulator ---------------------------------------------------------------------------------------


def _sdemulator_pads():
    pads = Record([
        ("clk",   1),
        ("cmd_i", 1),
        ("cmd_o", 1),
        ("cmd_t", 1),
        ("dat_i", 4),
        ("dat_o", 4),
        ("dat_t", 4),
    ])
    return pads


class SDEmulator(Module):
    """This is a Migen wrapper around the lower-level parts of the SD card emulator
       from Google Project Vault's Open Reference Platform. This core still does all
       SD card command processing in hardware.

       Block store:
       - Default (size=None, image=None): a single 512-bytes block buffer shared by all block
         addresses (small footprint, card capacity reported as 125MB).
       - size (bytes, multiple of 512KB) and/or image (raw disk image file): a block-addressed
         store, initialized from image (zeros when not provided/after its end), with the card
         capacity reported from size (default: image size rounded up to 512KB).
       """
    def  __init__(self, platform, size=None, image=None):
        self.pads = pads = _sdemulator_pads()

        # The external SD clock drives a separate clock domain
        self.clock_domains.cd_sd_ll = ClockDomain(reset_less=True)
        self.comb += self.cd_sd_ll.clk.eq(pads.clk)

        # Block Store.
        nblocks, init, csd_c_size = _sdemulator_store(size, image)
        self.nblocks = nblocks
        self.specials.buffer = Memory(32, nblocks*_BLOCK_SIZE//4, init=init)
        self.specials.internal_rd_port = self.buffer.get_port(clock_domain="sd_ll")
        self.specials.internal_wr_port = self.buffer.get_port(write_capable=True, clock_domain="sd_ll")
        bram_rd_sd_addr = Signal(7) # Word address in the 512-bytes block.
        bram_wr_sd_addr = Signal(7) # Word address in the 512-bytes block.

        # Communication between PHY and Link layers
        self.card_state       = Signal(4)
        self.mode_4bit        = Signal()
        self.mode_spi         = Signal()
        self.mode_crc_disable = Signal()
        self.spi_sel          = Signal()
        self.cmd_in           = Signal(48)
        self.cmd_in_last      = Signal(6)
        self.cmd_in_crc_good  = Signal()
        self.cmd_in_act       = Signal()
        self.data_in_act      = Signal()
        self.data_in_busy     = Signal()
        self.data_in_another  = Signal()
        self.data_in_stop     = Signal()
        self.data_in_done     = Signal()
        self.data_in_crc_good = Signal()
        self.resp_out         = Signal(136)
        self.resp_type        = Signal(4)
        self.resp_busy        = Signal()
        self.resp_act         = Signal()
        self.resp_done        = Signal()
        self.data_out_reg     = Signal(512)
        self.data_out_src     = Signal()
        self.data_out_len     = Signal(10)
        self.data_out_busy    = Signal()
        self.data_out_act     = Signal()
        self.data_out_stop    = Signal()
        self.data_out_done    = Signal()

        # Status outputs
        self.info_card_desel   = Signal()
        self.err_op_out_range  = Signal()
        self.err_unhandled_cmd = Signal()
        self.err_cmd_crc       = Signal()
        self.host_hc_support   = Signal()

        # Debug signals
        self.cmd_in_cmd  = Signal(6)
        self.card_status = Signal(32)
        self.phy_idc     = Signal(11)
        self.phy_odc     = Signal(11)
        self.phy_istate  = Signal(7)
        self.phy_ostate  = Signal(7)
        self.phy_spi_cnt = Signal(8)
        self.link_state  = Signal(7)
        self.link_ddc    = Signal(16)
        self.link_dc     = Signal(16)

        # I/O request outputs
        self.block_read_act       = Signal()
        self.block_read_addr      = Signal(32)
        self.block_read_byteaddr  = Signal(32)
        self.block_read_num       = Signal(32)
        self.block_read_stop      = Signal()
        self.block_write_act      = Signal()
        self.block_write_addr     = Signal(32)
        self.block_write_byteaddr = Signal(32)
        self.block_write_num      = Signal(32)
        self.block_preerase_num   = Signal(23)
        self.block_erase_start    = Signal(32)
        self.block_erase_end      = Signal(32)

        # I/O completion inputs
        self.block_read_go    = Signal()
        self.block_write_done = Signal()

        # Block Store addressing: Word address in block from the PHY, block from the Link (stable
        # during the block transfer).
        if nblocks > 1:
            block_bits = bits_for(nblocks - 1)
            self.comb += [
                self.internal_rd_port.adr.eq(Cat(bram_rd_sd_addr, self.block_read_addr[:block_bits])),
                self.internal_wr_port.adr.eq(Cat(bram_wr_sd_addr, self.block_write_addr[:block_bits])),
            ]
        else:
            self.comb += [
                self.internal_rd_port.adr.eq(bram_rd_sd_addr),
                self.internal_wr_port.adr.eq(bram_wr_sd_addr),
            ]

        self.specials += Instance("sd_phy",
            i_clk_50           = ClockSignal(),
            i_reset_n          = ~ResetSignal(),
            i_sd_clk           = ClockSignal("sd_ll"),
            i_sd_cmd_i         = pads.cmd_i,
            o_sd_cmd_o         = pads.cmd_o,
            o_sd_cmd_t         = pads.cmd_t,
            i_sd_dat_i         = pads.dat_i,
            o_sd_dat_o         = pads.dat_o,
            o_sd_dat_t         = pads.dat_t,
            i_card_state       = self.card_state,
            o_cmd_in           = self.cmd_in,
            o_cmd_in_crc_good  = self.cmd_in_crc_good,
            o_cmd_in_act       = self.cmd_in_act,
            i_data_in_act      = self.data_in_act,
            o_data_in_busy     = self.data_in_busy,
            i_data_in_another  = self.data_in_another,
            i_data_in_stop     = self.data_in_stop,
            o_data_in_done     = self.data_in_done,
            o_data_in_crc_good = self.data_in_crc_good,
            i_resp_out         = self.resp_out,
            i_resp_type        = self.resp_type,
            i_resp_busy        = self.resp_busy,
            i_resp_act         = self.resp_act,
            o_resp_done        = self.resp_done,
            i_mode_4bit        = self.mode_4bit,
            i_mode_spi         = self.mode_spi,
            i_mode_crc_disable = self.mode_crc_disable,
            o_spi_sel          = self.spi_sel,
            i_data_out_reg     = self.data_out_reg,
            i_data_out_src     = self.data_out_src,
            i_data_out_len     = self.data_out_len,
            o_data_out_busy    = self.data_out_busy,
            i_data_out_act     = self.data_out_act,
            i_data_out_stop    = self.data_out_stop,
            o_data_out_done    = self.data_out_done,
            o_bram_rd_sd_addr  = bram_rd_sd_addr,
            i_bram_rd_sd_q     = self.internal_rd_port.dat_r,
            o_bram_wr_sd_addr  = bram_wr_sd_addr,
            o_bram_wr_sd_wren  = self.internal_wr_port.we,
            o_bram_wr_sd_data  = self.internal_wr_port.dat_w,
            i_bram_wr_sd_q     = self.internal_wr_port.dat_r,
            o_idc              = self.phy_idc,
            o_odc              = self.phy_odc,
            o_istate           = self.phy_istate,
            o_ostate           = self.phy_ostate,
            o_spi_cnt          = self.phy_spi_cnt
        )

        sd_link_params = {}
        if csd_c_size is not None:
            sd_link_params["p_CSD_C_SIZE"] = csd_c_size # Card capacity: (C_SIZE + 1) * 512KB.
        self.specials += Instance("sd_link", **sd_link_params,
            i_clk_50               = ClockSignal(),
            i_reset_n              = ~ResetSignal(),
            o_link_card_state      = self.card_state,
            i_phy_cmd_in           = self.cmd_in,
            i_phy_cmd_in_crc_good  = self.cmd_in_crc_good,
            i_phy_cmd_in_act       = self.cmd_in_act,
            i_phy_spi_sel          = self.spi_sel,
            o_phy_data_in_act      = self.data_in_act,
            i_phy_data_in_busy     = self.data_in_busy,
            o_phy_data_in_stop     = self.data_in_stop,
            o_phy_data_in_another  = self.data_in_another,
            i_phy_data_in_done     = self.data_in_done,
            i_phy_data_in_crc_good = self.data_in_crc_good,
            o_phy_resp_out         = self.resp_out,
            o_phy_resp_type        = self.resp_type,
            o_phy_resp_busy        = self.resp_busy,
            o_phy_resp_act         = self.resp_act,
            i_phy_resp_done        = self.resp_done,
            o_phy_mode_4bit        = self.mode_4bit,
            o_phy_mode_spi         = self.mode_spi,
            o_phy_mode_crc_disable = self.mode_crc_disable,
            o_phy_data_out_reg     = self.data_out_reg,
            o_phy_data_out_src     = self.data_out_src,
            o_phy_data_out_len     = self.data_out_len,
            i_phy_data_out_busy    = self.data_out_busy,
            o_phy_data_out_act     = self.data_out_act,
            o_phy_data_out_stop    = self.data_out_stop,
            i_phy_data_out_done    = self.data_out_done,
            o_block_read_act       = self.block_read_act,
            i_block_read_go        = self.block_read_go,
            o_block_read_addr      = self.block_read_addr,
            o_block_read_byteaddr  = self.block_read_byteaddr,
            o_block_read_num       = self.block_read_num,
            o_block_read_stop      = self.block_read_stop,
            o_block_write_act      = self.block_write_act,
            i_block_write_done     = self.block_write_done,
            o_block_write_addr     = self.block_write_addr,
            o_block_write_byteaddr = self.block_write_byteaddr,
            o_block_write_num      = self.block_write_num,
            o_block_preerase_num   = self.block_preerase_num,
            o_block_erase_start    = self.block_erase_start,
            o_block_erase_end      = self.block_erase_end,
            i_opt_enable_hs        = 1,
            o_cmd_in_last          = self.cmd_in_last,
            o_info_card_desel      = self.info_card_desel,
            o_err_unhandled_cmd    = self.err_unhandled_cmd,
            o_err_cmd_crc          = self.err_cmd_crc,
            o_cmd_in_cmd           = self.cmd_in_cmd,
            o_host_hc_support      = self.host_hc_support,
            o_card_status          = self.card_status,
            o_state                = self.link_state,
            o_dc                   = self.link_dc,
            o_ddc                  = self.link_ddc
        )

        # Send block data when receiving read_act.
        self.comb += self.block_read_go.eq(self.block_read_act)

        # Ack block write when receiving write_act.
        self.comb += self.block_write_done.eq(self.block_write_act)

        # Verilog sources from ProjectVault ORP
        vdir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "verilog")
        platform.add_verilog_include_path(vdir)
        platform.add_sources(vdir, "sd_common.v", "sd_link.v", "sd_phy.v")
