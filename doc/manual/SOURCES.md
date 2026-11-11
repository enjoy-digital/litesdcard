# Sources of the manual's facts

Every number and name in the manual is taken from the repository at the documented revision. This
file records where each chapter's facts come from, so that a reviewer can re-check them and a
maintainer knows what to update when the code changes.

| Chapter / section | Sources |
|---|---|
| 00 Front matter | `doc/manual/manual.yaml`, `README.md` |
| 01 Introduction | `README.md`, `setup.py`, `litesdcard/{phy,core,crc,common,gen}.py`, `litesdcard/frontend/{dma,bist}.py`, `litesdcard/emulator/`, `CONTRIBUTORS`; LiteX `soc/integration/soc.py` (`add_sdcard`, `add_spi_sdcard`), `liblitesdcard/sdcard.c`, `bios/cmds/cmd_litesdcard.c`, `tools/litex_json2dts_{linux,zephyr}.py`; LiteX-Boards targets and platforms |
| 02 SD primer | `litesdcard/{phy,core,common,crc}.py`, `MEMO`; LiteX `liblitesdcard/sdcard.c`; LiteX-Boards `extensions/pmod.py` |
| 03 Architecture | `litesdcard/{phy,core,crc,common}.py`, `litesdcard/frontend/dma.py`; LiteX `soc/integration/soc.py`, `liblitesdcard/sdcard.c` |
| 04 PHY | `litesdcard/phy.py`, `litesdcard/gen.py`, `test/test_phy.py`; LiteX `build/io.py`, `build/{xilinx,altera,lattice,gowin,efinix,colognechip}/common.py`, `liblitesdcard/sdcard.c`; LiteX-Boards `extensions/pmod.py` and platforms |
| 05 PHY engines | `litesdcard/{phy,crc,common,core}.py`, `test/test_phy.py`; LiteX `soc/integration/soc.py`, `liblitesdcard/sdcard.c` |
| 06 Core | `litesdcard/{core,crc,common,phy}.py`, `test/test_core.py`, `test/test_crc.py`; LiteX `liblitesdcard/sdcard.{c,h}` |
| 07 DMAs | `litesdcard/frontend/{dma,bist}.py`; LiteX `soc/cores/dma.py`, `soc/integration/soc.py`, `liblitesdcard/sdcard.c` |
| 08 Emulator | `litesdcard/emulator/`, `litesdcard/phy.py` (`SDPHYIOEmulator`); LiteX `tools/litex_sim.py` |
| 09 Getting started | LiteX `tools/litex_sim.py`, `bios/cmds/cmd_litesdcard.c`, `bios/boot.c`, `bios/helpers.c`; LiteX-Boards `targets/digilent_arty.py`, `extensions/pmod.py`; captures with `litex_sim --with-sdcard` |
| 10 Integration | LiteX `soc/integration/soc.py` (`add_sdcard`, `add_spi_sdcard`), `soc/cores/spi/spi_master.py`, `build/extension.py`; `litesdcard/{phy,core,gen}.py`; LiteX-Boards `extensions/pmod.py` and platforms |
| 11 Software | LiteX `liblitesdcard/sdcard.{c,h}`, `bios/cmds/cmd_litesdcard.c`, `bios/cmds/cmd_spiflash.c`, `bios/boot.c`, `bios/main.c`, `tools/litex_json2dts_{linux,zephyr}.py`; Linux-on-LiteX-VexRiscv `HOWTO.md`; Enjoy-Digital blog (TEL0025) |
| 12 Boards | LiteX-Boards `targets/*` (`add_sdcard` calls), `platforms/*`, `extensions/pmod.py`; LiteX `build/*/common.py`; `bench/*.py` |
| 13 Simulation and verification | `test/test_crc.py`, `test/test_phy.py`, `test/test_core.py`, `test/test_dma.py`, `test/test_emulator.py`, `.github/workflows/ci.yml`, `bench/sim.py`, `doc/manual/tools/csr_doc.py`; LiteX `litex/tools/litex_sim.py` (`--with-sdcard`, 1 MHz system clock), `litex/build/sim/verilator.py` (trace options), `soc/integration/soc.py` (`add_sdcard`, default emulator store); `litesdcard/emulator/core.py` (block store) |
| 14 Debugging | LiteX `litex/soc/software/liblitesdcard/sdcard.c` (debug trace, retries, divider cap, init flow, DMA waits, CCS), `bios/cmds/cmd_litesdcard.c`, `bios/boot.c` (boot messages), `bios/helpers.c`, `litex/tools/litex_client.py`, `litex/tools/litex_json2dts_linux.py`; `litesdcard/core.py` (events), `litesdcard/phy.py` (timeouts, card detect, busy, `SDPHYIOEmulator`), `litesdcard/frontend/dma.py`; `bench/arty.py`, `bench/genesys2.py`, `bench/trellisboard.py` (analyzer probes, `BenchPHY`), `bench/sim.py`, `test/test_crc.py`; LiteX `bios/cmds/cmd_spiflash.c`; Linux mainline `drivers/mmc/host/litex_mmc.c` (PHY offsets); trace verbatim from LiteX commit `bd7b951af` |
| A Register reference | Generated: `doc/manual/registers.py` (configurations, PHY descriptions, notes), `doc/manual/tools/csr_doc.py`, snapshots `doc/manual/csr/*.json`; `litesdcard/gen.py`, `litesdcard/phy.py`, `litesdcard/core.py`, `litesdcard/frontend/dma.py`; LiteX `litex/soc/cores/dma.py`, `litex/soc/integration/soc.py` (`add_sdcard`, events) |
| B Build options | `litesdcard/phy.py`, `core.py`, `frontend/dma.py`, `frontend/bist.py`, `emulator/core.py`, `gen.py`, `bench/*.py`; LiteX `litex/soc/integration/soc.py` (`add_sdcard`, `add_spi_sdcard`), `liblitesdcard/sdcard.c`, `spisdcard.c`, `bios/main.c` (boot priority); LiteX-Boards `targets/digilent_arty.py`, `targets/efinix_ti375_c529_dev_kit.py` |
| C Glossary | Chapters 02 to 11; `litesdcard/phy.py`, `core.py`; LiteX `liblitesdcard/sdcard.c` |
| D Performance and resources | Computed from `litesdcard/phy.py` (DATAR/DATAW states, clocker) and LiteX `sdcard.c` (divider rule, clocks); memories from `litesdcard_gen --vendor lattice` (`build/gateware/litesdcard_core.v`); records: LiteX commits `c07703124`, `df3428be0` (quoted), LiteSDCard commit `19c854f`, Enjoy-Digital blog "TriXium, part 2" |
| E Maintaining this manual, Z | Manual kit (unchanged) |
| README Documentation section, CI register check | `README.md`, `.github/workflows/ci.yml` (step from LiteSATA) |
