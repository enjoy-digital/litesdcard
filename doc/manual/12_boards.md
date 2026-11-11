# Boards and examples {#boards}

This chapter lists the boards on which LiteX builds LiteSDCard, family by family, with the
special cases: eMMC devices, level shifters, Pmod adapters, the emulator in an FPGA. It ends
with the hardware benches of the repository. How far each function is validated is in the
[status table](#intro-status).

## At a glance {#boards-glance}

Every board below is a LiteX-Boards target that calls `add_sdcard` when it is built with
`--with-sdcard` (or the option named in [Special cases](#boards-special)). The list comes from
the master branch of LiteX-Boards:

```sh
git grep -l "add_sdcard(" -- litex_boards/targets
```

| FPGA family | Targets | Lowering of the IO by LiteX |
|----------------------------------|-------------|-----------------------------------------------------|
| Xilinx 7-Series | 34 | IO registers and `IOBUF` |
| Xilinx UltraScale(+) | 4 | IO registers and `IOBUF` |
| Lattice ECP5 | 22 | `TRELLIS_IO` with Yosys and nextpnr; inferred with Diamond |
| Lattice Certus-NX | 1 | Inferred registers and tristate |
| Intel/Altera | 9 | Agilex 3 and 5 primitive; inferred on the others |
| Gowin | 5 | `IOBUF` on GW5A; inferred on GW1N and GW2A |
| Efinix Titanium | 3 | Efinix tristate |
| Cologne Chip GateMate | 3 | Cologne Chip tristate |

The lowering column says how LiteX turns the SDR registers and tristates of the PHY into the
primitives of the family; [PHY: clocking and IO](#phy) gives the classes.

The PHY itself is the same everywhere. Most targets have a 4-bit microSD slot at 3.3 V, many
with a card detect pin; their platforms define its pins and pull-ups as in [The platform
resource](#integ-pads).

## Targets by family {#boards-families}

**Xilinx 7-Series.** `alientek_davincipro`, `alinx_ax7035`, `antmicro_artix_dc_scm`,
`antmicro_datacenter_ddr4_test_board`, `antmicro_ddr5_test_board`, `antmicro_ddr5_tester`,
`antmicro_lpddr4_test_board`, `antmicro_sodimm_ddr5_tester`, `digilent_arty`, `digilent_basys3`,
`digilent_genesys2`, `digilent_netfpga_sume`, `digilent_nexys4`, `digilent_nexys4ddr`,
`digilent_nexys_video`, `embedfire_rise_pro`, `hseda_xc7a35t`, `isx_im1283`, `kosagi_netv2`,
`machdyne_mozart_mx1`, `machdyne_mozart_mx2`, `microphase_a7_lite`, `mnt_rkx7`,
`myir_myc_j7a100t`, `puzhi_pz_a7xxt_kfb`, `qmtech_artix7_fbg484`, `qmtech_artix7_fgg676`,
`qmtech_kintex7_devboard`, `qmtech_wukong`, `qmtech_xc7a35t`, `qmtech_xc7k325t`,
`sitlinv_stlv7325_v1`, `sitlinv_stlv7325_v2`, `ztex213`.

**Xilinx UltraScale(+).** `aliexpress_rk_xcku5p`, `alinx_axau15`, `mlk_cu07_ku15p`,
`xilinx_kcu105`.

**Lattice ECP5.** `colorlight_i5`, `fpc_iii`, `gsd_butterstick`, `icepi_zero`,
`lambdaconcept_ecpix5`, `litex_acorn_baseboard`, `logicbone`, `machdyne_konfekt`,
`machdyne_kopflos`, `machdyne_lakritz`, `machdyne_minze`, `machdyne_mozart_ml1`,
`machdyne_mozart_ml2`, `machdyne_noir`, `machdyne_schoko`, `machdyne_vanille`,
`machdyne_vivaldi_ml1`, `muselab_icesugar_pro`, `radiona_ulx3s`, `radiona_ulx4m_ld_v2`,
`radiona_ulx4m_ls_v2`, `trellisboard`.

**Lattice Certus-NX.** `trenz_tel0025`.

**Intel/Altera.** `altera_agilex5e_065b_premium_devkit`, `qmtech_10cl006`, `qmtech_5cefa2`,
`qmtech_5cefa5`, `qmtech_cyclone10_starterkit`, `qmtech_ep4cex5`, `qmtech_ep4cgx150`,
`terasic_atum_a3_nano`, `terasic_de2_115`.

**Gowin.** `sipeed_tang_console`, `sipeed_tang_mega_138k`, `sipeed_tang_nano_20k`,
`sipeed_tang_primer_20k`, `trenz_tec0117`.

**Efinix Titanium.** `efinix_ti375_c529_dev_kit`, `efinix_ti60_f225_dev_kit`,
`efinix_tz170_j484_dev_kit`.

**Cologne Chip GateMate.** `colognechip_gatemate_evb`, `intergalaktik_ulx5m_gs`,
`olimex_gatemate_a1_evb`.

A target is built as any LiteX-Boards target, with the option that adds the card:

```sh
python3 -m litex_boards.targets.radiona_ulx3s --with-sdcard --build --load
```

The photo below shows one of these boards: the Trenz TEL0025 module, with its microSD slot in
the middle of the board.

![Trenz TEL0025, a Lattice Certus-NX module with a microSD slot, target `trenz_tel0025`.
Photo from an Enjoy-Digital article.](boards_tel0025.jpg)

## Special cases {#boards-special}

A few targets differ from the 4-bit microSD slot. The table below lists them with the option
that enables the card.

| Target | Option | What differs |
|-------------------------------------------|--------------------------------------|-------------------|
| `efinix_ti375_c529_dev_kit` | `--with-emmc` | 8-bit eMMC at 1.8 V, resource `emmc` |
| `antmicro_artix_dc_scm` | `--with-emmc` | eMMC on 4 data lines, resource `sdcard` |
| `lambdaconcept_ecpix5` | `--with-sdcard` | Level shifter: `cmd_dir`, `dat0_dir`, `dat13_dir` |
| `efinix_tz170_j484_dev_kit` | `--with-sdcard-emulator` | Emulator in the FPGA, no card |
| `digilent_arty`, `digilent_basys3` | `--with-sdcard` | Pmod adapter (`PmodSDCard`) |

**eMMC on the Ti375 C529 Dev Kit.** The kit has a soldered eMMC on eight data lines at 1.8 V,
besides its microSD slot. `--with-emmc` calls `add_sdcard(sdcard_name="emmc")`: the module keeps
the name `sdcard`, so the BIOS commands and `sdcardboot` work unchanged. The Linux driver
`litex_mmc` supports SD cards only ([Linux](#sw-linux)), so Linux does not use the eMMC.

`--with-sdcard` and `--with-emmc` both create the `sdcard` module, so the target accepts only one
of them (with `--with-spi-sdcard`, the three options are mutually exclusive).

The PHY sees eight data lines and the BIOS driver takes its eMMC path, with the 8-bit bus and
high speed timing at 50 MHz ([Initialization](#sw-init)).

![The Efinix Ti375 C529 Dev Kit, whose target offers the microSD slot or the 8-bit eMMC.
Photo from an Enjoy-Digital article.](boards_ti375_c529.jpg)

**Pmod adapters.** The targets without a slot use the `PmodSDCard` extension of LiteX-Boards on
one of their Pmod connectors: `digilent_arty` and `digilent_basys3`, and also `colorlight_i5`,
`colognechip_gatemate_evb`, `olimex_gatemate_a1_evb`, `qmtech_wukong` and `trenz_tec0117`. The
Arty target accepts `--pmod pmodd=numato_sdcard` for the Numato adapter ([The platform
resource](#integ-pads)).

**SPI mode.** Most targets also offer `--with-spi-sdcard`, the SPI-mode alternative of LiteX
([SPI mode: add_spi_sdcard](#integ-spi)). Choose one of the two options for a given slot.

## Benches {#boards-benches}

The `bench/` directory of the repository holds test designs for three boards. Each builds a SoC
with LiteSDCard and the LiteX BIOS, so the BIOS commands of [Step 3: talk to the
card](#gs-commands) run on them; options add a logic analyzer or an external sampler.

| Bench | Board, card | System clock | Card wiring |
|----------------------------------------|-------------------------|-----------|------------------------|
| `bench/arty.py` | Arty A7, Digilent Pmod MicroSD | 100 MHz | `PmodSDCard` on `pmodd` |
| `bench/genesys2.py` | Genesys2, on-board slot | 100 MHz | Platform `sdcard` resource |
| `bench/trellisboard.py` | TrellisBoard, Pmod MicroSD on `pmoda` | 75 MHz | Own resource, `PULLMODE=UP` |

| Option | Benches | Effect |
|-----------------------------------|-----------------------|------------------------------------------|
| `--build`, `--load` | All | Build the bitstream, load it |
| `--bench soc` or `phy` | Arty, TrellisBoard | SoC with the BIOS, or the PHY alone sending a byte on a button |
| `--variant` | Arty, TrellisBoard | `standard` (default) or `minimal` CPU and RAM |
| `--with-analyzer` | All | LiteScope analyzer on the PHY, over Etherbone |
| `--with-sampler` | Arty, TrellisBoard | 8-bit external sampler on a Pmod, streamed over UDP |
| `--load-bios` | All | Load a new BIOS over Etherbone and reboot |

```sh
cd bench
python3 arty.py --build --load
```

The `phy` bench drives the CMD line with a fixed byte when a button is pressed, to check the
pad timing with an oscilloscope. The sampler records 8 external signals and sends them to the
host over UDP, through a DRAM FIFO on the Arty, for a logic view of the card lines from a second
Pmod.

On the TrellisBoard, `--bench phy` does not elaborate on the master branch: the script passes
the `--variant`, `--with-sampler` and `--with-analyzer` values to `BenchPHY`, which takes no
argument, and Python stops with a `TypeError` ([Known issues](#debug-known)). The Arty `phy`
bench accepts them.

## In the code {#boards-code}

| Item | Repository | Path |
|----------------|--------------------|----------------------------------------------------------------|
| Targets | LiteX-Boards | `litex_boards/targets/<board>.py` |
| `sdcard` resources | LiteX-Boards | `litex_boards/platforms/<board>.py` |
| Pmod adapters | LiteX-Boards | `litex_boards/extensions/pmod.py` |
| Benches | LiteSDCard | `bench/arty.py`, `bench/genesys2.py`, `bench/trellisboard.py` |
| Sampler | LiteSDCard | `bench/sampler.py` |

Where to go next: [Getting started](#getting-started) for a first board, [Adding LiteSDCard to a
SoC](#integration) to add a slot to your own platform, [Debugging](#debugging) when a card does
not answer.
